"""Fragment ids -> the smallest valid backend spec that emits them.

Developer Spec.md §18.18 drives a pairwise matrix off `list_all_fragments()`:
for every pair of fragments it needs a spec that `validate()` accepts and
whose `compose()` output covers those fragments *and applies* -- no
migration may reference a table the spec does not create.

The mapping is data, not control flow: an entity rule (reached through
`table_<entity>` or `rls_<entity>_<group>`) plus a handful of static rules.
Two closures then run against the ontology itself:

1. every enabled feature pulls in what it hard-requires, and every feature
   that activates a needed entity gets enabled;
2. the spec is probed with the real `compose()` until no emitted fragment
   has an unsatisfied `requires`, which is what keeps `is_owner()`'s
   reference to `listings` and the `messages` FK to `bookings` resolvable.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from compiler.generator.composer import compose
from compiler.generator.fragments import load
from compiler.generator.models import Fragment
from compiler.generator.rls import parse_rls_id
from compiler.generator.table_fragments import table_entity_ids
from compiler.ontology.loader import Ontology, load_ontology
from compiler.spec.derive import recompute_spec
from compiler.spec.models import BackendSpec

__all__ = ["spec_for"]


#: Mirrors the ontology loader's layout convention.
ONTOLOGY_VERSIONS_DIR = Path(__file__).resolve().parents[1] / "ontology" / "versions" / "v1"

#: Fixed so `spec_for` is deterministic (matrix fixtures stay reproducible).
CREATED_AT = datetime.fromisoformat("2025-01-01T00:00:00+00:00")

_TABLE_PREFIX = "table_"
_MIGRATION_SUFFIX = ".sql"

#: Safety bound for the closure loop; the ontology's graphs are far shallower.
_MAX_CLOSURE_STEPS = 8

# entity -> ingredients needed to emit `table_<entity>` / `rls_<entity>_*`.
# `purposes` are bucket purposes; they are resolved to a single parameter
# value after every fragment has contributed.
_ENTITY_INGREDIENTS: dict[str, dict[str, Any]] = {
    # The authentication feature activates profiles.
    "profiles": {"features": ["authentication"]},
    # listings/bookings come from the bookings feature; reviews and
    # favorites additionally need bookings (hard constraints).
    "listings": {"features": ["bookings"]},
    "bookings": {"features": ["bookings"]},
    "messages": {
        "features": ["messaging"],
        "parameters": {"messaging.trigger_event": "after_request"},
    },
    "payments": {
        "features": ["payments"],
        "parameters": {"payments.provider": "stripe"},
    },
    "reviews": {"features": ["reviews", "bookings"]},
    "files": {
        "features": ["file_storage"],
        "purposes": ["documents"],
    },
    # Verification requires file storage (hard constraint).
    "verification_documents": {
        "features": ["file_storage", "verification"],
        "parameters": {"verification.method": "admin_approval"},
    },
    "favorites": {"features": ["favorites", "bookings"]},
    "notifications": {"features": ["realtime"], "channels": ["notifications"]},
}

# Static fragments that are not reached through an entity.
_STATIC_INGREDIENTS: dict[str, dict[str, Any]] = {
    # Role helpers: emitted whenever authentication is on. `is_owner()`
    # selects from `listings`; the PL/pgSQL body defers that lookup to
    # first call, but `bookings` is still forced so the table always
    # exists in every emitted context.
    "function_is_admin": {"features": ["authentication"]},
    "function_is_owner": {"features": ["authentication", "bookings"]},
    "trigger_verification_status": {
        "features": ["file_storage", "verification"],
        "parameters": {"verification.method": "admin_approval"},
    },
    "bucket_avatars": {"features": ["file_storage"], "purposes": ["avatars"]},
    "bucket_listings": {"features": ["file_storage"], "purposes": ["listings"]},
    "bucket_documents": {"features": ["file_storage"], "purposes": ["documents"]},
    "bucket_verification": {
        "features": ["file_storage", "verification"],
        "parameters": {"verification.method": "admin_approval"},
        "purposes": ["documents"],
    },
    "realtime_messages": {"features": ["realtime"], "channels": ["messages"]},
    "realtime_notifications": {"features": ["realtime"], "channels": ["notifications"]},
    "realtime_bookings": {"features": ["realtime"], "channels": ["bookings"]},
}

# Hard constraints on `realtime.channels` (§2.5 of the ontology bundle).
_CHANNEL_FEATURES: dict[str, dict[str, Any]] = {
    "messages": {
        "features": ["messaging"],
        "parameters": {"messaging.trigger_event": "after_request"},
    },
    "bookings": {"features": ["bookings"]},
}


@lru_cache(maxsize=1)
def _ontology() -> Ontology:
    return load_ontology(ONTOLOGY_VERSIONS_DIR)


def _entity_of(fragment_id: str) -> str | None:
    if fragment_id.startswith(_TABLE_PREFIX):
        return fragment_id[len(_TABLE_PREFIX):]
    parsed = parse_rls_id(fragment_id)
    return parsed[0] if parsed else None


def _features_activating(entity: str) -> set[str]:
    return {
        feature_id
        for feature_id, feature in _ontology().features.items()
        if entity in feature.activates_entities
    }


def _with_dependencies(features: set[str]) -> set[str]:
    """Add every feature the enabled ones hard-require, transitively."""
    ontology = _ontology()
    pending = list(features)
    while pending:
        feature = ontology.features.get(pending.pop())
        if feature is None:
            continue
        for required in feature.requires:
            if required not in features:
                features.add(required)
                pending.append(required)
    return features


def _ingredients_for(fragment_id: str) -> dict[str, Any]:
    static = _STATIC_INGREDIENTS.get(fragment_id)
    if static is not None:
        return static
    return _ENTITY_INGREDIENTS.get(_entity_of(fragment_id) or "", {})


def _requested_ingredients(fragment_ids: Iterable[str]) -> tuple[set[str], dict[str, Any]]:
    """First pass: apply the ingredient table to the requested ids."""
    enabled: set[str] = set()
    parameters: dict[str, Any] = {}
    purposes: list[str] = []
    channels: list[str] = []

    for fragment_id in fragment_ids:
        ingredients = _ingredients_for(fragment_id)
        enabled.update(ingredients.get("features", ()))
        parameters.update(ingredients.get("parameters", {}))
        for purpose in ingredients.get("purposes", ()):
            if purpose not in purposes:
                purposes.append(purpose)
        for channel in ingredients.get("channels", ()):
            if channel not in channels:
                channels.append(channel)

    if purposes:
        # One requested purpose stays exact; conflicting purposes fall back
        # to `mixed`, which derives all three buckets.
        parameters["file_storage.bucket_purpose"] = purposes[0] if len(purposes) == 1 else "mixed"

    if channels:
        enabled.add("realtime")
        parameters["realtime.channels"] = sorted(channels)
        for channel in channels:
            constraints = _CHANNEL_FEATURES.get(channel)
            if constraints is None:
                continue
            enabled.update(constraints.get("features", ()))
            parameters.update(constraints.get("parameters", {}))

    return enabled, parameters


def _required_entities(fragments: Sequence[Fragment]) -> set[str]:
    """Entities whose tables `fragments`' SQL needs, foreign keys included.

    `is_owner()` selects from `listings`; the `messages` table references
    `bookings`. Both show up as `requires` on a fragment, and the parents
    of those requirements as foreign keys of the tables themselves.
    """
    entities: set[str] = set()
    pending: list[str] = []
    for fragment in fragments:
        for requirement in fragment.requires:
            if not requirement.startswith(_TABLE_PREFIX):
                continue
            entity = requirement[len(_TABLE_PREFIX):]
            if entity in table_entity_ids() and entity not in entities:
                entities.add(entity)
                pending.append(entity)

    while pending:
        table = load(f"{_TABLE_PREFIX}{pending.pop()}")
        for requirement in table.requires:
            entity = requirement[len(_TABLE_PREFIX):]
            if entity in table_entity_ids() and entity not in entities:
                entities.add(entity)
                pending.append(entity)
    return entities


def _build_spec(enabled: set[str], parameters: dict[str, Any], ontology: Ontology) -> BackendSpec:
    return BackendSpec(
        version="1.0",
        ontology_version=ontology.version,
        created_at=CREATED_AT,
        features={feature_id: True for feature_id in sorted(enabled)},
        parameters=dict(parameters),
        roles=["user"] if enabled else [],
        rls_overrides={},
        entities=[],
        buckets=[],
        edge_functions=[],
        decisions=[],
        defaulted=[],
        unsupported=[],
    )


def _emitted_fragments(spec: BackendSpec, ontology: Ontology) -> list[Fragment]:
    fragments = []
    for migration in compose(spec, ontology):
        stem = migration.filename.split("_", 1)[1][: -len(_MIGRATION_SUFFIX)]
        fragments.append(load(stem))
    return fragments


def spec_for(fragment_ids: list[str]) -> BackendSpec:
    """Build a valid `BackendSpec` whose `compose()` output covers `fragment_ids`."""
    ontology = _ontology()
    enabled, parameters = _requested_ingredients(fragment_ids)

    # Close over what the spec actually emits: enabling the features that
    # activate those entities can add more fragments, so iterate to a
    # fixpoint (bounded -- the ontology's graphs are shallow).
    for _ in range(_MAX_CLOSURE_STEPS):
        enabled = _with_dependencies(enabled)
        spec = _build_spec(enabled, parameters, ontology)
        needed: set[str] = set()
        for entity in _required_entities(_emitted_fragments(spec, ontology)):
            needed |= _features_activating(entity)
        if needed <= enabled:
            break
        enabled |= needed

    # Every feature hard-requires authentication, so it comes along -- and
    # the closure above may have been the thing that enabled one.
    if enabled:
        enabled.add("authentication")
        parameters["authentication.method"] = "email_password"

    return recompute_spec(_build_spec(enabled, parameters, ontology), ontology)
