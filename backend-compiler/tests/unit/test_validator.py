"""
_spec() calls recompute_spec so derived fields (entities, buckets,
edge_functions) are consistent with features/parameters.
"""
from compiler.spec.derive import recompute_spec
from compiler.spec.models import BackendSpec
from compiler.spec.validator import validate


def _spec(ontology, **kwargs):
    base = dict(
        version="1.0", ontology_version=1, created_at="2025-01-01T00:00:00Z",
        features={}, parameters={}, roles=[], rls_overrides={},
        entities=[], buckets=[], edge_functions=[],
        decisions=[], defaulted=[], unsupported=[],
    )
    base.update(kwargs)
    return recompute_spec(BackendSpec(**base), ontology)


def test_valid_minimal_spec(minimal_spec, ontology):
    result = validate(minimal_spec, ontology)
    assert result.ok
    assert result.errors == []


def test_valid_marketplace_spec(marketplace_spec, ontology):
    assert validate(marketplace_spec, ontology).ok


def test_missing_dependency_rejected(ontology):
    spec = _spec(ontology,
        features={"payments": True, "authentication": False},
        parameters={"payments.provider": "stripe"},
    )
    assert not validate(spec, ontology).ok


def test_hard_constraint_instant_booking_with_verification(ontology):
    spec = _spec(ontology,
        features={"authentication": True, "bookings": True,
                  "verification": True, "file_storage": True},
        parameters={"bookings.mode": "instant",
                    "verification.method": "government_id_and_admin",
                    "file_storage.bucket_purpose": "mixed"},
    )
    assert not validate(spec, ontology).ok


def test_soft_constraint_anytime_messaging_warns(ontology):
    spec = _spec(ontology,
        features={"authentication": True, "messaging": True},
        parameters={"messaging.trigger_event": "anytime"},
    )
    result = validate(spec, ontology)
    assert result.ok, f"unexpected errors: {result.errors}"
    assert len(result.warnings) >= 1


def test_list_choice_invalid_member_rejected(ontology):
    spec = _spec(ontology,
        features={"authentication": True, "realtime": True},
        parameters={"realtime.channels": ["notifications", "ghost_channel"]},
    )
    assert not validate(spec, ontology).ok


def test_list_choice_valid_members_accepted(ontology):
    spec = _spec(ontology,
        features={"authentication": True, "realtime": True},
        parameters={"realtime.channels": ["notifications"]},
    )
    assert validate(spec, ontology).ok


def test_list_string_below_min_rejected(ontology):
    spec = _spec(ontology,
        features={"authentication": True, "roles": True},
        parameters={"roles.role_names": []},
    )
    assert not validate(spec, ontology).ok


def test_list_string_above_max_rejected(ontology):
    spec = _spec(ontology,
        features={"authentication": True, "roles": True},
        parameters={"roles.role_names": ["a", "b", "c", "d", "e", "f"]},
    )
    assert not validate(spec, ontology).ok


def test_list_string_empty_member_rejected(ontology):
    spec = _spec(ontology,
        features={"authentication": True, "roles": True},
        parameters={"roles.role_names": ["admin", "  "]},
    )
    assert not validate(spec, ontology).ok


def test_realtime_messages_channel_without_messaging_feature_rejected(ontology):
    spec = _spec(ontology,
        features={"authentication": True, "realtime": True, "messaging": False},
        parameters={"realtime.channels": ["messages"]},
    )
    result = validate(spec, ontology)
    assert not result.ok
    assert any("messaging" in str(e).lower() for e in result.errors)


def test_realtime_bookings_channel_without_bookings_feature_rejected(ontology):
    spec = _spec(ontology,
        features={"authentication": True, "realtime": True, "bookings": False},
        parameters={"realtime.channels": ["bookings"]},
    )
    result = validate(spec, ontology)
    assert not result.ok
    assert any("booking" in str(e).lower() for e in result.errors)


def test_realtime_messages_channel_with_messaging_feature_accepted(ontology):
    spec = _spec(ontology,
        features={"authentication": True, "realtime": True, "messaging": True},
        parameters={"realtime.channels": ["messages"],
                    "messaging.trigger_event": "after_request"},
    )
    assert validate(spec, ontology).ok


def test_realtime_notifications_channel_needs_no_backing_feature(ontology):
    spec = _spec(ontology,
        features={"authentication": True, "realtime": True},
        parameters={"realtime.channels": ["notifications"]},
    )
    assert validate(spec, ontology).ok

# --- direct-construction branches (raw specs, no recompute) ---


def _raw(**kwargs):
    base = dict(
        version="1.0", ontology_version=1, created_at="2025-01-01T00:00:00Z",
        features={}, parameters={}, roles=[], rls_overrides={},
        entities=[], buckets=[], edge_functions=[],
        decisions=[], defaulted=[], unsupported=[],
    )
    base.update(kwargs)
    return BackendSpec(**base)


def test_unknown_parameter_rejected(ontology):
    result = validate(_raw(parameters={"not_a_feature.method": "x"}), ontology)
    assert not result.ok
    assert any("not_a_feature.method" in str(e) for e in result.errors)


def test_unknown_parameter_without_dot_rejected(ontology):
    result = validate(_raw(parameters={"nodot": "x"}), ontology)
    assert not result.ok


def test_unknown_parameter_for_known_feature_rejected(ontology):
    result = validate(_raw(parameters={"authentication.altitude": "high"}), ontology)
    assert not result.ok
    assert any("authentication.altitude" in str(e) for e in result.errors)


def test_invalid_choice_value_rejected(ontology):
    result = validate(_raw(
        features={"authentication": True},
        parameters={"authentication.method": "carrier_pigeon"},
    ), ontology)
    assert not result.ok
    assert any("carrier_pigeon" in str(e) for e in result.errors)


def test_list_choice_non_list_value_rejected(ontology):
    result = validate(_raw(parameters={"realtime.channels": "bookings"}), ontology)
    assert not result.ok
    assert any("realtime.channels" in str(e) for e in result.errors)


def test_list_string_non_list_value_rejected(ontology):
    result = validate(_raw(parameters={"roles.role_names": "admin"}), ontology)
    assert not result.ok


def test_list_string_blank_item_rejected(ontology):
    result = validate(_raw(parameters={"roles.role_names": ["admin", "   "]}), ontology)
    assert not result.ok


def test_undefined_role_rejected(ontology):
    result = validate(_raw(roles=["wizard"]), ontology)
    assert not result.ok
    assert any("wizard" in str(e) for e in result.errors)


def test_rls_override_unknown_entity_rejected(ontology):
    spec = _raw(features={"authentication": True}, rls_overrides={"ghost": "auth.uid() = id"})
    result = validate(spec, ontology)
    assert not result.ok
    assert any("ghost" in str(e) for e in result.errors)


def test_entity_derivation_mismatch_rejected(ontology):
    spec = _raw(features={"authentication": True}, entities=["ghost"])
    result = validate(spec, ontology)
    assert not result.ok
    assert any("entit" in str(e).lower() for e in result.errors)


def test_bucket_derivation_mismatch_rejected(ontology):
    from compiler.spec.models import BucketSpec

    spec = _raw(
        features={"authentication": True, "file_storage": True},
        buckets=[BucketSpec(name="junk", public=True, rls_pattern="owner_only")],
    )
    result = validate(spec, ontology)
    assert not result.ok
    assert any("bucket" in str(e).lower() for e in result.errors)


def test_edge_function_derivation_mismatch_rejected(ontology):
    spec = _raw(
        features={"authentication": True, "payments": True},
        edge_functions=["junk_fn"],
    )
    result = validate(spec, ontology)
    assert not result.ok
    assert any("edge" in str(e).lower() for e in result.errors)


def _fake_ontology(extra_features=None):
    """A duck-typed ontology for branches the real v1 graph cannot reach."""
    from types import SimpleNamespace

    def feat(requires):
        return SimpleNamespace(
            requires=list(requires),
            activates_entities=[],
            activates_edge_functions=[],
            parameters={},
        )

    features = {fid: feat(reqs) for fid, reqs in (extra_features or {}).items()}
    return SimpleNamespace(version=1, features=features, constraints=[], roles=set(), entities={})


def test_circular_feature_dependency_rejected():
    from compiler.spec.validator import validate as _validate

    ontology = _fake_ontology(extra_features={"a": ["b"], "b": ["a"]})
    result = _validate(_raw(features={"a": True, "b": True}), ontology)
    assert not result.ok
    assert any("circular" in str(e).lower() for e in result.errors)

