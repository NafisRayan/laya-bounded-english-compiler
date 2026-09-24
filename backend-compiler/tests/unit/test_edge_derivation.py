from compiler.spec.derive import derive_edge_functions, recompute_spec
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


def test_no_edge_functions_for_minimal_app(ontology):
    spec = _spec(ontology, features={"authentication": True})
    assert derive_edge_functions(spec, ontology) == []


def test_stripe_derives_webhook(ontology):
    spec = _spec(ontology,
        features={"authentication": True, "payments": True},
        parameters={"payments.provider": "stripe"},
    )
    assert "stripe_webhook" in derive_edge_functions(spec, ontology)


def test_verification_derives_webhook(ontology):
    spec = _spec(ontology,
        features={"authentication": True, "file_storage": True, "verification": True},
        parameters={"file_storage.bucket_purpose": "documents",
                    "verification.method": "government_id"},
    )
    assert "verification_webhook" in derive_edge_functions(spec, ontology)


def test_realtime_with_table_channel_derives_notification_dispatch(ontology):
    spec = _spec(ontology,
        features={"authentication": True, "realtime": True},
        parameters={"realtime.channels": ["notifications"]},
    )
    assert "notification_dispatch" in derive_edge_functions(spec, ontology)


def test_realtime_with_empty_channels_drops_notification_dispatch(ontology):
    spec = _spec(ontology,
        features={"authentication": True, "realtime": True},
        parameters={"realtime.channels": []},
    )
    assert "notification_dispatch" not in derive_edge_functions(spec, ontology)


def test_recompute_sets_edge_functions(ontology):
    spec = _spec(ontology,
        features={"authentication": True, "payments": True},
        parameters={"payments.provider": "stripe"},
    )
    assert "stripe_webhook" in spec.edge_functions


def test_edge_function_derivation_invariant_enforced(ontology):
    from compiler.spec.validator import validate
    spec = _spec(ontology, features={"authentication": True})
    spec = spec.model_copy(update={"edge_functions": ["ghost_webhook"]})
    assert not validate(spec, ontology).ok