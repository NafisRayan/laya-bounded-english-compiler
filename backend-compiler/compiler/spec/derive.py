"""Deterministic derivation of entities, buckets and edge functions.

Copied verbatim from the Developer Spec.md §5.3. `entities`, `buckets` and
`edge_functions` are always derived, never hand-edited; the validator (§6)
rejects any spec where these fields do not equal their derived values.
"""

from __future__ import annotations

from compiler.ontology.loader import Ontology
from compiler.spec.models import BackendSpec, BucketSpec

__all__ = [
    "TABLE_BACKED_REALTIME_CHANNELS",
    "derive_buckets",
    "derive_edge_functions",
    "derive_entities",
    "recompute_spec",
]

TABLE_BACKED_REALTIME_CHANNELS = {"messages", "notifications", "bookings"}


def derive_entities(spec: BackendSpec, ontology: Ontology) -> list[str]:
    entities: set[str] = set()
    for feature_id, enabled in spec.features.items():
        if not enabled:
            continue
        if feature_id == "realtime":
            channels = set(spec.parameters.get("realtime.channels", []))
            if not (channels & TABLE_BACKED_REALTIME_CHANNELS):
                continue
        entities.update(ontology.features[feature_id].activates_entities)
    return sorted(entities)


def derive_buckets(spec: BackendSpec) -> list[BucketSpec]:
    if not spec.features.get("file_storage"):
        return []
    purpose = spec.parameters.get("file_storage.bucket_purpose", "mixed")
    mapping = {
        "avatars": [BucketSpec(name="avatars", public=True, rls_pattern="owner_only")],
        "listings": [BucketSpec(name="listings", public=True, rls_pattern="owner_only")],
        "documents": [BucketSpec(name="documents", public=False, rls_pattern="owner_only")],
        "mixed": [
            BucketSpec(name="avatars", public=True, rls_pattern="owner_only"),
            BucketSpec(name="listings", public=True, rls_pattern="owner_only"),
            BucketSpec(name="documents", public=False, rls_pattern="owner_only"),
        ],
    }
    buckets = list(mapping[purpose])
    if spec.features.get("verification"):
        buckets.append(BucketSpec(name="verification", public=False, rls_pattern="owner_only"))
    return buckets


def derive_edge_functions(spec: BackendSpec, ontology: Ontology) -> list[str]:
    fns: set[str] = set()
    for feature_id, enabled in spec.features.items():
        if enabled:
            fns.update(ontology.features[feature_id].activates_edge_functions)

    if spec.features.get("realtime"):
        channels = set(spec.parameters.get("realtime.channels", []))
        if not (channels & TABLE_BACKED_REALTIME_CHANNELS):
            fns.discard("notification_dispatch")

    if spec.features.get("payments") and spec.parameters.get("payments.provider") != "stripe":
        fns.discard("stripe_webhook")

    return sorted(fns)


def recompute_spec(spec: BackendSpec, ontology: Ontology) -> BackendSpec:
    return spec.model_copy(update={
        "entities": derive_entities(spec, ontology),
        "buckets": derive_buckets(spec),
        "edge_functions": derive_edge_functions(spec, ontology),
    })