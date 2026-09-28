"""Error taxonomy and remediation planning (Developer Spec.md §9.1, §9.3).

`classify_error` maps a failure message onto the §9.1 categories with
ordered substring rules; `remediation_options` turns a category into the
§9.3 MCQ options; `apply_remediation` folds an answer back into the spec.
SQL-side fixes (`IF NOT EXISTS`, drop-then-create) are already baked into
the generated fragments, so remediation only adjusts the spec, retries, or
escalates to a human.
"""

from __future__ import annotations

from typing import Any

from compiler.spec.models import BackendSpec, Decision

__all__ = [
    "RETRYABLE_CATEGORIES",
    "MigrationError",
    "apply_remediation",
    "classify_error",
    "remediation_options",
]


class MigrationError(Exception):
    """A `supabase db push` (or equivalent migration application) failed."""


#: §9.1 -- categories whose remediation loop retries on the same project.
#: Descriptive documentation of the taxonomy: the §9.2 loop itself
#: retries `transient` and MCQ-retries whichever categories have options.
RETRYABLE_CATEGORIES = frozenset({
    "transient",
    "duplicate_object",
    "rls_conflict",
    "fk_ordering",
    "extension_missing",
})

#: Ordered rules, first match wins (§9.1 Detection column). Each rule is a
#: list of phrase GROUPS: a category matches when every substring of some
#: group appears. `rls_conflict` needs the group ("policy", "already
#: exists") so `relation ... already exists` falls through to
#: duplicate_object; the single-phrase groups after it are alternatives
#: ("503" alone means transient). `transient` precedes `quota_exceeded` so
#: "timeout exceeded" retries instead of escalating.
_RULES: tuple[tuple[str, tuple[tuple[str, ...], ...]], ...] = (
    ("rls_conflict", (("policy", "already exists"),)),
    ("duplicate_object", (("already exists",),)),
    ("fk_ordering", (("foreign key constraint",),)),
    ("extension_missing", (("does not exist",),)),
    ("permission_denied", (("permission denied",),)),
    ("transient", (("timeout",), ("timed out",), ("http 5",), ("502",), ("503",), ("504",))),
    ("quota_exceeded", (("quota",), ("limit",), ("exceeded",))),
    ("sql_syntax", (("syntax error",),)),
)


def classify_error(message: str) -> str:
    lowered = str(message).lower()
    for category, groups in _RULES:
        if any(all(needle in lowered for needle in group) for group in groups):
            return category
    return "unknown"


def remediation_options(category: str, spec: BackendSpec, error: Any) -> list[dict[str, str]]:
    """§9.3 MCQ options for a category; empty means escalate (§9.1).

    `spec` and `error` are accepted for §9.3 signature parity; the options
    are category-determined today.
    """
    if category == "fk_ordering":
        return [
            {"label": "Reorder migrations", "value": "reorder"},
            {"label": "Combine into one migration", "value": "combine"},
            {"label": "Remove the relationship", "value": "remove_relationship"},
        ]
    if category == "quota_exceeded":
        return [
            {"label": "Upgrade plan", "value": "upgrade"},
            {"label": "Remove optional features", "value": "remove_features"},
            {"label": "Escalate to manual setup", "value": "manual"},
        ]
    if category == "extension_missing":
        return [
            {"label": "Enable the extension", "value": "enable_extension"},
            {"label": "Skip features needing it", "value": "skip"},
        ]
    if category in ("duplicate_object", "rls_conflict"):
        return [{"label": "Re-apply with idempotent SQL", "value": "reapply"}]
    # permission_denied / sql_syntax / unknown: flag for a human.
    return []


def apply_remediation(spec: BackendSpec, category: str, answer: str) -> BackendSpec:
    """Fold a remediation answer into the spec (§9.2).

    Only quota-driven feature removal changes behavior; every other answer
    is recorded as a decision so the attempt trail stays auditable.
    """
    features = dict(spec.features)
    if category == "quota_exceeded" and answer == "remove_features":
        for optional in ("favorites", "reviews"):
            features.pop(optional, None)

    decisions = list(spec.decisions) + [
        Decision(
            capability_id=f"deploy.remediation.{category}",
            value=answer,
            confidence=1.0,
            source="user",
            evidence=None,
        ),
    ]
    return spec.model_copy(update={"features": features, "decisions": decisions})
