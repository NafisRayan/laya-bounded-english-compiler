from compiler.spec.derive import derive_buckets, derive_entities, recompute_spec
from compiler.spec.models import BackendSpec


def _spec(ontology, **kwargs):
    base = dict(
        version="1.0", ontology_version=1, created_at="2025-01-01T00:00:00Z",
        features={}, parameters={}, roles=[], rls_overrides={},
        entities=[], buckets=[], edge_functions=[],
        decisions=[], defaulted=[], unsupported=[],
    )
    base.update(kwargs)
    return recompute_spec(BackendSpec(**base), ontology)


def test_derive_entities_minimal(ontology):
    spec = _spec(ontology, features={"authentication": True})
    assert derive_entities(spec, ontology) == ["profiles"]


def test_derive_entities_marketplace(ontology):
    spec = _spec(ontology, features={
        "authentication": True, "bookings": True, "messaging": True,
        "payments": True, "file_storage": True,
    })
    entities = derive_entities(spec, ontology)
    for expected in ("listings", "bookings", "messages", "payments", "files"):
        assert expected in entities


def test_recompute_updates_entities(ontology):
    spec = _spec(ontology, features={"authentication": True, "bookings": True})
    assert "listings" in spec.entities


def test_entity_derivation_invariant_enforced(ontology):
    from compiler.spec.validator import validate
    spec = _spec(ontology, features={"authentication": True})
    spec = spec.model_copy(update={"entities": ["wizard_table"]})
    assert not validate(spec, ontology).ok


def test_realtime_with_table_channel_derives_notifications(ontology):
    spec = _spec(ontology,
        features={"authentication": True, "realtime": True},
        parameters={"realtime.channels": ["notifications"]},
    )
    assert "notifications" in derive_entities(spec, ontology)


def test_realtime_with_empty_channels_does_not_derive_notifications(ontology):
    spec = _spec(ontology,
        features={"authentication": True, "realtime": True},
        parameters={"realtime.channels": []},
    )
    assert "notifications" not in derive_entities(spec, ontology)


def test_derive_buckets_listings_purpose(ontology):
    spec = _spec(ontology,
        features={"authentication": True, "file_storage": True},
        parameters={"file_storage.bucket_purpose": "listings"},
    )
    assert any(b.name == "listings" for b in derive_buckets(spec))


def test_derive_buckets_mixed_includes_verification(ontology):
    spec = _spec(ontology,
        features={"authentication": True, "file_storage": True, "verification": True},
        parameters={"file_storage.bucket_purpose": "mixed",
                    "verification.method": "government_id"},
    )
    assert "verification" in {b.name for b in derive_buckets(spec)}


def test_bucket_derivation_invariant_enforced(ontology):
    from compiler.spec.models import BucketSpec
    from compiler.spec.validator import validate
    spec = _spec(ontology,
        features={"authentication": True, "file_storage": True},
        parameters={"file_storage.bucket_purpose": "avatars"},
    )
    spec = spec.model_copy(update={
        "buckets": [BucketSpec(name="ghost", public=True, rls_pattern="owner_only")]
    })
    assert not validate(spec, ontology).ok