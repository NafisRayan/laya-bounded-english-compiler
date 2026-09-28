"""Table fragments generated from the ontology entity definitions.

Developer Spec.md §7.1 (`table` produces `CREATE TABLE` + indexes). A
`table_<entity>` fragment is *derived*, never hand-authored, so the SQL
always matches the ontology bundle.

The entity definitions are read from the versioned ontology bundle
(`compiler/ontology/versions/v1/entities.yaml`) instead of being passed
around as an `Ontology` instance: `load()` / `list_all_fragments()` must
answer for generated ids without the caller holding an ontology (the
spec's §18.18 fragment matrix calls them bare).

`users` is managed by Supabase Auth and is never generated; foreign keys
to it render as `auth.users` (a bare `users` only resolves when `auth` is
on `search_path`, which stock PostgreSQL 15 does not guarantee).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from compiler.generator.models import CompositionError, Fragment

__all__ = ["build_table", "table_entity_ids"]


#: Managed by Supabase Auth; excluded from the generated fragments.
MANAGED_ENTITY = "users"

#: Mirrors the ontology loader's layout convention: sections live under
#: `compiler/ontology/versions/v1/`.
ONTOLOGY_VERSIONS_DIR = Path(__file__).resolve().parents[1] / "ontology" / "versions" / "v1"
ENTITIES_FILE = ONTOLOGY_VERSIONS_DIR / "entities.yaml"


@lru_cache(maxsize=1)
def entity_definitions() -> dict[str, dict[str, Any]]:
    """`entities` section of the versioned ontology, keyed by entity name."""
    document = yaml.safe_load(ENTITIES_FILE.read_text(encoding="utf-8")) or {}
    return dict(document.get("entities") or {})


def table_entity_ids() -> list[str]:
    """Entity names that have a `table_<entity>` fragment (sorted)."""
    return sorted(name for name in entity_definitions() if name != MANAGED_ENTITY)


def _column_sql(name: str, spec: dict[str, Any], *, inline_pk: bool) -> str:
    """Render one column definition.

    `default` is emitted verbatim: the ontology already stores SQL
    (`now()`, `gen_random_uuid()`, `'user'`), so re-quoting it would break
    the value.
    """
    parts = [name, str(spec.get("type") or "text")]
    if not spec.get("nullable", False):
        parts.append("NOT NULL")
    if inline_pk:
        parts.append("PRIMARY KEY")
    if spec.get("unique", False):
        parts.append("UNIQUE")
    default = spec.get("default")
    if default is not None:
        parts.append(f"DEFAULT {default}")
    foreign_key = spec.get("fk")
    if foreign_key:
        target_table, _, target_column = str(foreign_key).partition(".")
        if target_table == MANAGED_ENTITY:
            target_table = "auth.users"
        clause = f"REFERENCES {target_table}({target_column or 'id'})"
        on_delete = spec.get("on_delete")
        if on_delete:
            clause += f" ON DELETE {on_delete}"
        parts.append(clause)
    return " ".join(parts)


def _index_name(entity: str, ordinal: int, columns: list[str]) -> str:
    """Deterministic index name so re-composition never renames an index."""
    return f"{entity}_{ordinal}_{'_'.join(columns)}_idx"


def build_table(entity: str) -> Fragment:
    """Build the `table_<entity>` fragment from the ontology definition."""
    entities = entity_definitions()
    if entity not in entities:
        raise CompositionError(f"unknown entity: {entity}")
    if entity == MANAGED_ENTITY:
        raise CompositionError(f"entity {entity} is managed by Supabase Auth")

    definition = entities[entity] or {}
    fields: dict[str, dict[str, Any]] = definition.get("fields") or {}

    pk_columns = [name for name, spec in fields.items() if spec.get("pk")]
    # A single-column primary key stays inline; two or more become a
    # trailing table constraint (`favorites` is the composite case).
    inline_pk = len(pk_columns) == 1

    columns: list[str] = []
    requires: list[str] = []
    for name, spec in fields.items():
        columns.append(f"  {_column_sql(name, spec, inline_pk=inline_pk and spec.get('pk', False))}")
        foreign_key = spec.get("fk")
        if not foreign_key:
            continue
        target = str(foreign_key).partition(".")[0]
        # `users` is Supabase-managed, so it is not a fragment dependency.
        if target != MANAGED_ENTITY and target in entities and f"table_{target}" not in requires:
            requires.append(f"table_{target}")

    body = list(columns)
    if len(pk_columns) > 1:
        body.append(f"  PRIMARY KEY ({', '.join(pk_columns)})")
    statements = [f"CREATE TABLE IF NOT EXISTS {entity} (", ",\n".join(body), ");"]

    for ordinal, index in enumerate(definition.get("indexes") or [], start=1):
        index_columns = list(index.get("columns") or [])
        if not index_columns:
            continue
        statements.append(
            f"CREATE INDEX IF NOT EXISTS {_index_name(entity, ordinal, index_columns)}"
            f" ON {entity}({', '.join(index_columns)});"
        )

    return Fragment(
        id=f"table_{entity}",
        type="table",
        requires=requires,
        provides=[f"entity.{entity}"],
        sql="\n".join(statements),
    )
