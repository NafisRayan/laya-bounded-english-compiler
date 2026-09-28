"""Composition algorithm (Developer Spec.md §7.3) and conflict detection
(§7.4), plus the fragment rendering pass.

`compose()` is a pure function of `(spec, ontology)`: it re-derives the
spec, selects fragments, orders them, checks them for conflicts and emits
one `Migration` per fragment. Re-composing an unchanged spec yields the
same filenames and the same SQL, which is what §7.5's idempotency rests on.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from compiler.generator.fragments import load
from compiler.generator.models import CompositionError, Fragment, Migration
from compiler.generator.ordering import topo_sort
from compiler.generator.rls import rls_for
from compiler.ontology.loader import Ontology
from compiler.spec.derive import TABLE_BACKED_REALTIME_CHANNELS, recompute_spec
from compiler.spec.models import BackendSpec

__all__ = ["compose", "detect_conflicts", "load", "render"]


BUCKET_PREFIX = "bucket_"
REALTIME_PREFIX = "realtime_"

#: Fallback for rendered bucket fragments: the plan's fixed defaults when
#: the bucket is not part of the spec being rendered. The spec's
#: `BucketSpec` is the source of truth whenever it mentions the bucket.
PUBLIC_BUCKETS = frozenset({"avatars", "listings"})
_DEFAULT_BUCKET_SIZE_BYTES = 10 * 1024 * 1024

# Developer Spec.md §7.4 conflict detection. Names are collected from the
# emitted SQL; `CREATE OR REPLACE` and `IF NOT EXISTS` are optional noise.
_OBJECT_NAME_RE = re.compile(
    r"CREATE\s+(?:OR\s+REPLACE\s+)?(?:TABLE|INDEX|FUNCTION|TRIGGER)\s+"
    r"(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE,
)
_POLICY_NAME_RE = re.compile(r"CREATE\s+POLICY\s+([A-Za-z_][A-Za-z0-9_]*)", re.IGNORECASE)
_TRIGGER_RE = re.compile(
    r"CREATE\s+TRIGGER\s+([A-Za-z_][A-Za-z0-9_]*)\s+[^;]*?\bON\s+([A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE,
)


def _bucket_values(spec: BackendSpec | None, name: str) -> tuple[bool, int]:
    """`(public, size bytes)` for a bucket name.

    `BucketSpec` wins when the spec mentions the bucket; otherwise the
    plan's fixed defaults apply (public buckets / 10 MiB).
    """
    for bucket in (spec.buckets if spec is not None else []):
        if bucket.name == name:
            return bucket.public, bucket.file_size_limit_mb * 1024 * 1024
    return name in PUBLIC_BUCKETS, _DEFAULT_BUCKET_SIZE_BYTES


def render(frag: Fragment, spec: BackendSpec | None = None, ontology: Ontology | None = None) -> str:
    """Substitute a fragment's placeholders; generated SQL passes through.

    Table / RLS / function / trigger SQL is final at build time. Bucket and
    realtime fragments carry `{name}` / `{channel}` / `{public}` / `{size}`
    placeholders; the bucket's `public` / `file_size_limit_mb` come from the
    spec's `BucketSpec` (via `render`'s `spec` argument) when present.

    Deliberately a literal `{placeholder}` pass rather than
    `string.Template`: the realtime body is a `DO $$ ... $$` block and
    `$$` is Template's escape for a single `$`, so templating would
    corrupt the block it is meant to fill in.
    """
    if frag.type == "bucket":
        name = frag.id[len(BUCKET_PREFIX):]
        public, size = _bucket_values(spec, name)
        return (
            frag.sql.replace("{name}", name)
            .replace("{public}", "true" if public else "false")
            .replace("{size}", str(size))
        )
    if frag.type == "realtime":
        return frag.sql.replace("{channel}", frag.id[len(REALTIME_PREFIX):])
    return frag.sql


class _Owners:
    """Object name -> the fragments that create it.

    Owners are counted per fragment occurrence, not per distinct id: two
    copies of the same fragment collide just as hard as two fragments that
    happen to share an object name.
    """

    def __init__(self) -> None:
        self._owners: dict[str, list[str]] = {}

    def claim(self, name: str, fragment_id: str) -> None:
        self._owners.setdefault(name, []).append(fragment_id)

    def conflicts(self, template: str) -> list[str]:
        return [
            template.format(name=name, owners=", ".join(sorted(set(owners))))
            for name, owners in sorted(self._owners.items())
            if len(owners) > 1
        ]


def detect_conflicts(ordered: Sequence[Fragment]) -> list[str]:
    """Return every Developer Spec.md §7.4 conflict among `ordered`."""
    issues: list[str] = []

    # 1. duplicate fragment id
    seen_ids: set[str] = set()
    duplicates: set[str] = set()
    for fragment in ordered:
        if fragment.id in seen_ids:
            duplicates.add(fragment.id)
        seen_ids.add(fragment.id)
    issues.extend(f"duplicate fragment id: {fragment_id}" for fragment_id in sorted(duplicates))

    # 2. duplicate object name
    object_owners = _Owners()
    for fragment in ordered:
        for name in _OBJECT_NAME_RE.findall(fragment.sql):
            object_owners.claim(name, fragment.id)
    issues.extend(object_owners.conflicts("duplicate object name: {name} (created by {owners})"))

    # 3. RLS policy name collision, 4. trigger collision on the same table,
    # 6. duplicate bucket name
    policy_owners = _Owners()
    trigger_owners = _Owners()
    bucket_owners = _Owners()
    for fragment in ordered:
        for name in _POLICY_NAME_RE.findall(fragment.sql):
            policy_owners.claim(name, fragment.id)
        for name, table in _TRIGGER_RE.findall(fragment.sql):
            trigger_owners.claim(f"{name} on {table.lower()}", fragment.id)
        if fragment.type == "bucket":
            bucket_owners.claim(fragment.id[len(BUCKET_PREFIX):], fragment.id)
    issues.extend(policy_owners.conflicts("RLS policy name collision: {name} (created by {owners})"))
    issues.extend(trigger_owners.conflicts("trigger collision: {name} (created by {owners})"))
    issues.extend(bucket_owners.conflicts("duplicate bucket name: {name} (created by {owners})"))

    # 5. FK cycle over table -> table edges
    fk_cycle = _fk_cycle(ordered)
    if fk_cycle is not None:
        issues.append(f"FK cycle: {' -> '.join(fk_cycle)}")

    # (defensive) ordering violation: a present requirement ordered after
    # its dependent. `topo_sort` already raises on this; the check keeps
    # `detect_conflicts` a complete validator on its own.
    positions = {fragment.id: index for index, fragment in enumerate(ordered)}
    for index, fragment in enumerate(ordered):
        for requirement in fragment.requires:
            if requirement in positions and positions[requirement] > index:
                issues.append(
                    f"ordering violation: {fragment.id} requires {requirement}, "
                    "which is ordered later"
                )

    return issues


def _fk_cycle(ordered: Sequence[Fragment]) -> list[str] | None:
    """DFS over table fragments' `requires`, restricted to table fragments."""
    tables = {fragment.id: fragment for fragment in ordered if fragment.type == "table"}
    edges = {
        fragment_id: {req for req in fragment.requires if req in tables} - {fragment_id}
        for fragment_id, fragment in tables.items()
    }
    visited: set[str] = set()
    on_stack: list[str] = []

    def visit(node: str) -> list[str] | None:
        visited.add(node)
        on_stack.append(node)
        for nxt in sorted(edges.get(node, ())):
            if nxt in on_stack:
                return on_stack[on_stack.index(nxt):] + [nxt]
            if nxt not in visited:
                found = visit(nxt)
                if found:
                    return found
        on_stack.pop()
        return None

    for node in sorted(edges):
        if node not in visited:
            found = visit(node)
            if found:
                return found
    return None


def compose(spec: BackendSpec, ontology: Ontology) -> list[Migration]:
    """Compose a backend spec into ordered, conflict-checked migrations."""
    spec = recompute_spec(spec, ontology)

    fragments: list[Fragment] = []
    if spec.features.get("authentication"):
        fragments.append(load("function_is_admin"))
        fragments.append(load("function_is_owner"))
    for entity in spec.entities:
        fragments.append(load(f"table_{entity}"))
        fragments.extend(rls_for(entity, spec, ontology))
    for bucket in spec.buckets:
        fragments.append(load(f"{BUCKET_PREFIX}{bucket.name}"))
    if spec.features.get("realtime"):
        for channel in spec.parameters.get("realtime.channels") or []:
            # Only table-backed channels have a fragment to emit.
            if channel in TABLE_BACKED_REALTIME_CHANNELS:
                fragments.append(load(f"{REALTIME_PREFIX}{channel}"))
    if spec.features.get("verification"):
        fragments.append(load("trigger_verification_status"))

    ordered = topo_sort(fragments, key="requires")
    conflicts = detect_conflicts(ordered)
    if conflicts:
        raise CompositionError(conflicts)

    return [
        Migration(
            filename=f"{index:04d}_{fragment.id}.sql",
            sql=render(fragment, spec=spec, ontology=ontology),
        )
        for index, fragment in enumerate(ordered)
    ]
