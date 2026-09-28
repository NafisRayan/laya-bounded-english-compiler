"""RLS policy plans (Developer Spec.md §7.1 `rls`, §7.4 policy naming).

Each fragment id is per role-GROUP -- `rls_listings_owner` -- and carries
`ENABLE ROW LEVEL SECURITY` plus one DROP/CREATE policy pair per operation
in its group. Policy names follow §7.4: `{table}_{operation}_{fragment_id}`,
which makes collisions across fragments impossible by construction while
staying greppable.

Every RLS fragment requires `function_is_admin` so the role helper is
always ordered before the policies (and so a policy-only selection still
creates the `profiles` table plus `is_admin()`).

`users` is managed by Supabase Auth and gets no RLS here.
"""

from __future__ import annotations

from typing import Any

from compiler.generator.models import CompositionError, Fragment

__all__ = [
    "RLS_GROUPS",
    "build_rls_group",
    "parse_rls_id",
    "rls_for",
    "rls_group_fragments",
    "rls_group_ids",
]


#: Managed by Supabase Auth; excluded from the generated fragments.
MANAGED_ENTITY = "users"

#: Operations whose policy constrains new rows rather than visible rows.
WITH_CHECK_OPS = frozenset({"insert"})

#: entity -> group -> (operations, predicate). Columns verified against
#: `compiler/ontology/versions/v1/entities.yaml`.
RLS_GROUPS: dict[str, dict[str, tuple[tuple[str, ...], str]]] = {
    "profiles": {
        "auth": (("select", "insert"), "auth.uid() IS NOT NULL"),
        "owner": (("update", "delete"), "auth.uid() = id"),
    },
    "listings": {
        "owner": (("select", "update", "delete"), "auth.uid() = owner_id"),
        "insert": (("insert",), "auth.uid() IS NOT NULL"),
    },
    "bookings": {
        "participant": (
            ("select", "insert", "update", "delete"),
            "auth.uid() IN (renter_id, owner_id)",
        ),
    },
    "messages": {
        "participant": (
            ("select", "insert", "update", "delete"),
            "auth.uid() IN (sender_id, recipient_id)",
        ),
    },
    "payments": {
        "owner": (("select",), "auth.uid() = payer_id"),
        "insert": (("insert",), "auth.uid() IS NOT NULL"),
    },
    "reviews": {
        "author": (
            ("select", "insert", "update", "delete"),
            "auth.uid() IN (author_id, subject_id)",
        ),
    },
    "files": {
        "owner": (("select", "update", "delete"), "auth.uid() = owner_id"),
        "insert": (("insert",), "auth.uid() IS NOT NULL"),
    },
    "verification_documents": {
        "owner": (("select", "update", "delete"), "auth.uid() = user_id"),
        "insert": (("insert",), "auth.uid() IS NOT NULL"),
    },
    "favorites": {
        "owner": (("select", "insert", "delete"), "auth.uid() = user_id"),
    },
    "notifications": {
        "owner": (("select", "update", "delete"), "auth.uid() = user_id"),
    },
}

PREFIX = "rls_"

#: PostgreSQL truncates identifiers longer than 63 chars with only a NOTICE;
#: treat it as a composition error so a future rename fails loudly instead
#: of colliding silently.
_POLICY_NAME_MAX_LEN = 63


def _fragment_id(entity: str, group: str) -> str:
    return f"{PREFIX}{entity}_{group}"


def _policy_name(entity: str, operation: str, group: str) -> str:
    name = f"{entity}_{operation}_{_fragment_id(entity, group)}"
    if len(name) > _POLICY_NAME_MAX_LEN:
        raise CompositionError(
            f"policy name exceeds {_POLICY_NAME_MAX_LEN} chars: {name}"
        )
    return name


def _group_sql(entity: str, group: str, operations: tuple[str, ...], predicate: str) -> str:
    statements = [f"ALTER TABLE {entity} ENABLE ROW LEVEL SECURITY;"]
    for operation in operations:
        name = _policy_name(entity, operation, group)
        clause = (
            f"WITH CHECK ({predicate})"
            if operation in WITH_CHECK_OPS
            else f"USING ({predicate})"
        )
        statements.append("")
        statements.append(f"DROP POLICY IF EXISTS {name} ON {entity};")
        statements.append(f"CREATE POLICY {name} ON {entity}")
        statements.append(f"  FOR {operation.upper()} {clause};")
    return "\n".join(statements)


def build_rls_group(entity: str, group: str) -> Fragment:
    """Build the `rls_{entity}_{group}` fragment."""
    groups = RLS_GROUPS.get(entity)
    if groups is None or group not in groups:
        raise CompositionError(f"unknown rls group: {_fragment_id(entity, group)}")
    operations, predicate = groups[group]
    return Fragment(
        id=_fragment_id(entity, group),
        type="rls",
        requires=[f"table_{entity}", "function_is_admin"],
        provides=[f"rls.{entity}.{group}"],
        sql=_group_sql(entity, group, operations, predicate),
    )


def rls_for(entity: str, spec: Any = None, ontology: Any = None) -> list[Fragment]:
    """RLS fragments for one entity, in group-plan order.

    `spec` and `ontology` are accepted (Developer Spec.md §7.3:1082) but
    unused: the plan is static today and stays forward-compatible with
    `spec.rls_overrides`.
    """
    if entity == MANAGED_ENTITY:
        return []
    return [build_rls_group(entity, group) for group in RLS_GROUPS.get(entity, {})]


def rls_group_ids() -> list[str]:
    """Every generated RLS fragment id (sorted)."""
    return sorted(_fragment_id(entity, group) for entity, groups in RLS_GROUPS.items() for group in groups)


def rls_group_fragments() -> list[Fragment]:
    """Every generated RLS fragment (sorted by id)."""
    return [build_rls_group(entity, group) for entity, group in
            sorted((entity, group) for entity, groups in RLS_GROUPS.items() for group in groups)]


def parse_rls_id(fragment_id: str) -> tuple[str, str] | None:
    """Split `rls_{entity}_{group}` into `(entity, group)`, or None.

    Entity names may contain underscores (`verification_documents`), so the
    longest matching entity prefix wins.
    """
    if not fragment_id.startswith(PREFIX):
        return None
    for entity in sorted(RLS_GROUPS, key=len, reverse=True):
        if not fragment_id.startswith(f"{PREFIX}{entity}_"):
            continue
        group = fragment_id[len(PREFIX) + len(entity) + 1:]
        if group in RLS_GROUPS[entity]:
            return entity, group
    return None
