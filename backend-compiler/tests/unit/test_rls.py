"""RLS policy plans (Developer Spec.md §7.1 `rls`, §7.4 policy naming)."""

import re

import pytest

from compiler.generator.fragments import list_all_fragments, load
from compiler.generator.models import CompositionError
from compiler.generator.rls import (
    RLS_GROUPS,
    build_rls_group,
    parse_rls_id,
    rls_for,
    rls_group_ids,
)

MANAGED_ENTITIES = ("profiles", "listings", "bookings", "messages", "payments",
                    "reviews", "files", "verification_documents", "favorites",
                    "notifications")


def test_rls_fragment_shape():
    fragment = load("rls_listings_owner")
    assert fragment.type == "rls"
    assert "ALTER TABLE listings ENABLE ROW LEVEL SECURITY;" in fragment.sql
    assert (
        "CREATE POLICY listings_select_rls_listings_owner ON listings\n"
        "  FOR SELECT USING (auth.uid() = owner_id);"
    ) in fragment.sql
    assert fragment.requires == ["table_listings", "function_is_admin"]
    assert fragment.provides == ["rls.listings.owner"]


def _created_policies(fragment_id):
    """`(name, operation)` for every policy the fragment creates."""
    return [
        (name, operation.lower())
        for name, operation in re.findall(
            r"CREATE POLICY (\S+) ON \S+\s+FOR (\w+)", load(fragment_id).sql
        )
    ]


def test_policy_name_convention():
    for fragment_id in rls_group_ids():
        entity, group = parse_rls_id(fragment_id)
        for name, operation in _created_policies(fragment_id):
            # §7.4: {table}_{operation}_{fragment_id}
            assert name == f"{entity}_{operation}_{fragment_id}"
            assert name == f"{entity}_{operation}_rls_{entity}_{group}"


def test_policy_names_are_unique_per_operation():
    for fragment_id in rls_group_ids():
        names = [name for name, _ in _created_policies(fragment_id)]
        assert len(names) == len(set(names))
        assert names  # every group creates at least one policy


def test_insert_uses_with_check():
    for fragment_id in rls_group_ids():
        entity, _ = parse_rls_id(fragment_id)
        sql = load(fragment_id).sql
        for line in sql.splitlines():
            if "FOR INSERT" in line:
                assert "WITH CHECK (" in line
            if "FOR SELECT" in line or "FOR UPDATE" in line or "FOR DELETE" in line:
                assert "USING (" in line
        assert f"ALTER TABLE {entity} ENABLE ROW LEVEL SECURITY;" in sql


def test_every_managed_entity_has_rls(ontology):
    for entity in MANAGED_ENTITIES:
        fragments = rls_for(entity, None, ontology)
        assert fragments, f"no rls fragments for {entity}"
        assert [f.id for f in fragments] == [f"rls_{entity}_{g}" for g in RLS_GROUPS[entity]]


def test_users_has_no_rls(ontology):
    assert rls_for("users", None, ontology) == []
    assert not any(fragment_id.startswith("rls_users") for fragment_id in list_all_fragments())


def test_rls_for_ignores_spec_and_ontology_arguments(ontology):
    assert rls_for("listings", None, None) == rls_for("listings", None, ontology)
    assert rls_for("unknown_entity", None, ontology) == []


def test_rls_group_ids_cover_every_planned_group():
    expected = sorted(f"rls_{entity}_{group}" for entity, groups in RLS_GROUPS.items()
                      for group in groups)
    assert rls_group_ids() == expected
    assert set(expected) <= set(list_all_fragments())


def test_parse_rls_id_handles_underscored_entities():
    assert parse_rls_id("rls_verification_documents_owner") == ("verification_documents", "owner")
    assert parse_rls_id("rls_listings_insert") == ("listings", "insert")
    assert parse_rls_id("rls_profiles_auth") == ("profiles", "auth")
    assert parse_rls_id("table_listings") is None
    assert parse_rls_id("rls_listings_nope") is None
    assert parse_rls_id("rls_nope_owner") is None


def test_build_rls_group_unknown_group_raises():
    with pytest.raises(CompositionError, match="unknown rls group: rls_listings_nope"):
        build_rls_group("listings", "nope")
    with pytest.raises(CompositionError, match="unknown rls group: rls_nope_owner"):
        build_rls_group("nope", "owner")


def test_rls_requires_are_uniform(ontology):
    for entity in MANAGED_ENTITIES:
        for fragment in rls_for(entity, None, ontology):
            # Uniform: the admin role helper is always ordered first.
            assert fragment.requires == [f"table_{entity}", "function_is_admin"]
            assert len(fragment.provides) == 1
            assert fragment.provides[0].startswith(f"rls.{entity}.")


def test_rls_groups_cover_every_generated_table():
    """Every generated table must have RLS -- forget an entity here and it
    silently compiles to an unprotected table."""
    from compiler.generator.table_fragments import table_entity_ids

    assert set(table_entity_ids()) == set(RLS_GROUPS)


def test_policy_names_stay_within_postgres_identifier_limit():
    for fragment_id in rls_group_ids():
        for name, _ in _created_policies(fragment_id):
            assert len(name) <= 63
