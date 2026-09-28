"""Fragment id -> minimal valid spec (Developer Spec.md §18.18).

The pairwise matrix needs, for any set of fragment ids, a spec that
`validate()` accepts and whose `compose()` output covers those ids.
"""

import itertools

import pytest

from compiler.generator.composer import compose
from compiler.generator.fragment_spec_map import spec_for
from compiler.generator.fragments import list_all_fragments, load
from compiler.spec.validator import validate


def _emitted(fragment_ids, ontology):
    migrations = compose(spec_for(fragment_ids), ontology)
    return {m.filename.split("_", 1)[1][: -len(".sql")] for m in migrations}


def test_spec_for_bucket_only_id(ontology):
    spec = spec_for(["bucket_avatars"])

    assert validate(spec, ontology).ok, validate(spec, ontology).errors
    assert spec.features["file_storage"] is True
    assert spec.parameters["file_storage.bucket_purpose"] == "avatars"
    assert "bucket_avatars" in _emitted(["bucket_avatars"], ontology)


def test_spec_for_realtime_only_id(ontology):
    spec = spec_for(["realtime_messages"])

    assert validate(spec, ontology).ok, validate(spec, ontology).errors
    assert spec.features["realtime"] is True
    assert spec.parameters["realtime.channels"] == ["messages"]
    # Hard constraint: realtime messages require the messaging feature.
    assert spec.features["messaging"] is True
    assert "realtime_messages" in _emitted(["realtime_messages"], ontology)


def test_spec_for_rls_only_id(ontology):
    spec = spec_for(["rls_listings_owner"])

    assert validate(spec, ontology).ok, validate(spec, ontology).errors
    assert spec.features["bookings"] is True
    assert "rls_listings_owner" in _emitted(["rls_listings_owner"], ontology)


def test_spec_for_pair(ontology):
    fragment_ids = ["table_messages", "bucket_listings"]
    spec = spec_for(fragment_ids)

    assert validate(spec, ontology).ok, validate(spec, ontology).errors
    emitted = _emitted(fragment_ids, ontology)
    assert {"table_messages", "bucket_listings"} <= emitted


def test_spec_for_enables_authentication_with_any_feature(ontology):
    spec = spec_for(["table_payments"])
    assert spec.features["authentication"] is True
    assert spec.parameters["authentication.method"] == "email_password"
    assert spec.roles == ["user"]
    assert validate(spec, ontology).ok


def test_spec_for_conflicting_bucket_purposes_fall_back_to_mixed(ontology):
    spec = spec_for(["bucket_avatars", "bucket_listings"])
    assert spec.parameters["file_storage.bucket_purpose"] == "mixed"
    assert validate(spec, ontology).ok
    assert {"bucket_avatars", "bucket_listings"} <= _emitted(
        ["bucket_avatars", "bucket_listings"], ontology
    )


def test_spec_for_deduplicates_realtime_channels(ontology):
    spec = spec_for(["realtime_bookings", "realtime_bookings"])
    assert spec.parameters["realtime.channels"] == ["bookings"]
    assert validate(spec, ontology).ok


def test_spec_for_ignores_unknown_fragment_ids(ontology):
    spec = spec_for(["edge_function_does_not_exist"])
    assert spec.features == {}
    assert validate(spec, ontology).ok
    assert compose(spec, ontology) == []


def test_spec_for_is_deterministic(ontology):
    first = spec_for(["table_files", "rls_files_owner"])
    second = spec_for(["table_files", "rls_files_owner"])
    assert first.model_dump() == second.model_dump()
    assert validate(first, ontology).ok


@pytest.mark.parametrize("fragment_id", list_all_fragments())
def test_spec_for_every_fragment_covers_it_and_validates(fragment_id, ontology):
    spec = spec_for([fragment_id])

    assert validate(spec, ontology).ok, validate(spec, ontology).errors
    assert fragment_id in _emitted([fragment_id], ontology)


@pytest.mark.parametrize("fragment_id", list_all_fragments())
def test_spec_for_leaves_no_unsatisfied_requirement(fragment_id, ontology):
    # Every declared `requires` must be a migration the same spec emits
    # (and `topo_sort` therefore places earlier), so the composed SQL has
    # no reference to a table that was never created.
    migrations = compose(spec_for([fragment_id]), ontology)
    emitted = {m.filename.split("_", 1)[1][: -len(".sql")] for m in migrations}

    for migration in migrations:
        stem = migration.filename.split("_", 1)[1][: -len(".sql")]
        for requirement in load(stem).requires:
            assert requirement in emitted, f"{stem} requires missing {requirement}"


#: Representative ids covering every fragment family; the §18.18 matrix
#: pairs all 35 ids, so at least every pair here must close cleanly.
_CURATED_IDS = [
    "function_is_admin",
    "function_is_owner",
    "trigger_verification_status",
    "bucket_avatars",
    "bucket_documents",
    "bucket_verification",
    "realtime_messages",
    "realtime_bookings",
    "table_listings",
    "table_messages",
    "table_payments",
    "table_favorites",
    "rls_listings_owner",
    "rls_messages_participant",
    "rls_profiles_owner",
]


@pytest.mark.parametrize(
    "a,b", list(itertools.combinations(_CURATED_IDS, 2))
)
def test_spec_for_pair_leaves_no_unsatisfied_requirement(a, b, ontology):
    fragment_ids = [a, b]
    spec = spec_for(fragment_ids)

    assert validate(spec, ontology).ok, validate(spec, ontology).errors

    migrations = compose(spec, ontology)
    emitted = {m.filename.split("_", 1)[1][: -len(".sql")] for m in migrations}
    assert {a, b} <= emitted

    for migration in migrations:
        stem = migration.filename.split("_", 1)[1][: -len(".sql")]
        for requirement in load(stem).requires:
            assert requirement in emitted, f"{stem} requires missing {requirement}"
