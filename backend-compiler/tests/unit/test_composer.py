"""Composition engine unit tests (Developer Spec.md §18.11).

The first six tests are the spec's §18.11 block verbatim. Everything below
them covers the same code paths from the plan: fragment selection (D6),
table SQL generation (D3) and every §7.4 conflict rule.
"""

import pytest

from compiler.generator.composer import compose
from compiler.generator.fragments import load
from compiler.generator.models import CompositionError, Migration
from compiler.generator.ordering import topo_sort


def test_compose_minimal_spec(minimal_spec, ontology):
    migrations = compose(minimal_spec, ontology)
    assert len(migrations) > 0
    assert all(m.filename.endswith(".sql") for m in migrations)


def test_compose_marketplace_spec(marketplace_spec, ontology):
    combined = "\n".join(m.sql for m in compose(marketplace_spec, ontology))
    assert "CREATE TABLE IF NOT EXISTS listings" in combined
    assert "CREATE TABLE IF NOT EXISTS bookings" in combined
    assert "CREATE TABLE IF NOT EXISTS messages" in combined
    assert "INSERT INTO storage.buckets" in combined


def test_realtime_empty_channels_no_notifications_table(ontology):
    from compiler.spec.models import BackendSpec
    from compiler.spec.derive import recompute_spec
    spec = recompute_spec(BackendSpec(
        version="1.0", ontology_version=1, created_at="2025-01-01T00:00:00Z",
        features={"authentication": True, "realtime": True},
        parameters={"realtime.channels": []},
        roles=["user"], rls_overrides={},
        entities=[], buckets=[], edge_functions=[],
        decisions=[], defaulted=[], unsupported=[],
    ), ontology)
    combined = "\n".join(m.sql for m in compose(spec, ontology))
    assert "notifications" not in combined


def test_realtime_fragment_present_when_enabled(ontology):
    from compiler.spec.models import BackendSpec
    from compiler.spec.derive import recompute_spec
    spec = recompute_spec(BackendSpec(
        version="1.0", ontology_version=1, created_at="2025-01-01T00:00:00Z",
        features={"authentication": True, "messaging": True, "realtime": True},
        parameters={"realtime.channels": ["messages"],
                    "messaging.trigger_event": "after_request"},
        roles=["user"], rls_overrides={},
        entities=[], buckets=[], edge_functions=[],
        decisions=[], defaulted=[], unsupported=[],
    ), ontology)
    combined = "\n".join(m.sql for m in compose(spec, ontology))
    assert "supabase_realtime" in combined


def test_all_migrations_have_if_not_exists(marketplace_spec, ontology):
    for m in compose(marketplace_spec, ontology):
        for line in m.sql.splitlines():
            if "CREATE TABLE" in line:
                assert "IF NOT EXISTS" in line
            if "CREATE INDEX" in line:
                assert "IF NOT EXISTS" in line


def test_topological_sort_respects_requires(ontology):
    from compiler.generator.composer import load
    a = load("function_is_admin")
    b = load("rls_listings_owner")
    ordered = topo_sort([b, a], key="requires")
    assert ordered.index(a) < ordered.index(b)


# --- plan extras: fragment selection (D6) ---


def _stems(migrations):
    """Fragment ids behind the `{ordinal}_{id}.sql` migration filenames."""
    return [m.filename.split("_", 1)[1][: -len(".sql")] for m in migrations]


def test_compose_requested_fragments_present(marketplace_spec, ontology):
    from compiler.generator.rls import rls_for

    migrations = compose(marketplace_spec, ontology)

    expected = {"function_is_admin", "function_is_owner"}
    for entity in marketplace_spec.entities:
        expected.add(f"table_{entity}")
        expected.update(fragment.id for fragment in rls_for(entity, marketplace_spec, ontology))
    expected.update(f"bucket_{bucket.name}" for bucket in marketplace_spec.buckets)

    assert set(_stems(migrations)) == expected
    assert "function_is_admin" in _stems(migrations)
    assert "function_is_owner" in _stems(migrations)


def test_compose_emits_bucket_per_derived_bucket(marketplace_spec, ontology):
    # `file_storage.bucket_purpose = listings` derives exactly one bucket.
    assert "bucket_listings" in _stems(compose(marketplace_spec, ontology))


def test_compose_no_edge_function_migrations(marketplace_spec, ontology):
    migrations = compose(marketplace_spec, ontology)
    assert not any("edge_function" in m.filename for m in migrations)


def test_compose_verification_emits_trigger(ontology):
    from compiler.spec.models import BackendSpec
    from compiler.spec.derive import recompute_spec
    spec = recompute_spec(BackendSpec(
        version="1.0", ontology_version=1, created_at="2025-01-01T00:00:00Z",
        features={"authentication": True, "file_storage": True, "verification": True},
        parameters={"authentication.method": "email_password",
                    "file_storage.bucket_purpose": "documents",
                    "verification.method": "admin_approval"},
        roles=["user"], rls_overrides={},
        entities=[], buckets=[], edge_functions=[],
        decisions=[], defaulted=[], unsupported=[],
    ), ontology)
    stems = _stems(compose(spec, ontology))
    assert "trigger_verification_status" in stems
    assert "bucket_verification" in stems
    assert "table_verification_documents" in stems


def test_compose_is_deterministic(marketplace_spec, ontology):
    first = compose(marketplace_spec, ontology)
    second = compose(marketplace_spec, ontology)
    assert [m.filename for m in first] == [m.filename for m in second]
    assert [m.sql for m in first] == [m.sql for m in second]


def test_compose_renders_bucket_placeholders(ontology):
    from compiler.spec.models import BackendSpec
    from compiler.spec.derive import recompute_spec
    spec = recompute_spec(BackendSpec(
        version="1.0", ontology_version=1, created_at="2025-01-01T00:00:00Z",
        features={"authentication": True, "file_storage": True},
        parameters={"authentication.method": "email_password",
                    "file_storage.bucket_purpose": "mixed"},
        roles=["user"], rls_overrides={},
        entities=[], buckets=[], edge_functions=[],
        decisions=[], defaulted=[], unsupported=[],
    ), ontology)
    migrations = compose(spec, ontology)
    sql = {stem: m.sql for stem, m in
           zip(_stems(migrations), migrations)}
    assert "VALUES ('avatars', 'avatars', true, 10485760)" in sql["bucket_avatars"]
    assert "VALUES ('documents', 'documents', false, 10485760)" in sql["bucket_documents"]
    # Public buckets are readable; private ones are owner-write only.
    assert "avatars_select_public" in sql["bucket_avatars"]
    assert "documents_select_public" not in sql["bucket_documents"]
    assert "documents_insert_owner" in sql["bucket_documents"]
    assert "{" not in sql["bucket_avatars"]


# --- plan extras: table fragment generation (D3) ---


def test_table_fragment_from_ontology():
    listings = load("table_listings")
    assert "CREATE TABLE IF NOT EXISTS listings" in listings.sql
    assert "REFERENCES auth.users(id)" in listings.sql
    assert "DEFAULT gen_random_uuid()" in listings.sql
    assert "CREATE INDEX IF NOT EXISTS listings_1_owner_id_idx ON listings(owner_id);" in listings.sql
    assert listings.provides == ["entity.listings"]


def test_table_fragment_composite_primary_key():
    favorites = load("table_favorites")
    assert "PRIMARY KEY (user_id, listing_id)" in favorites.sql
    assert favorites.requires == ["table_listings"]


def test_table_profiles_has_no_generated_id():
    # `profiles.id` is the auth user id, so it must not default to a new uuid.
    assert "gen_random_uuid()" not in load("table_profiles").sql


def test_table_fragment_requires_only_managed_dependencies():
    assert load("table_bookings").requires == ["table_listings"]
    assert load("table_messages").requires == ["table_bookings"]
    assert load("table_reviews").requires == ["table_bookings"]
    assert load("table_profiles").requires == []


def test_load_unknown_fragment_raises():
    with pytest.raises(CompositionError, match="unknown fragment: table_nope"):
        load("table_nope")
    with pytest.raises(CompositionError, match="unknown fragment: nope"):
        load("nope")


def test_load_users_table_is_rejected():
    # `users` is Supabase-managed: never a generated fragment.
    with pytest.raises(CompositionError, match="unknown fragment: table_users"):
        load("table_users")


# --- plan extras: the Migration model (D1) ---


def test_migration_models_have_filename_and_sql():
    migration = Migration(filename="0000_table_listings.sql", sql="SELECT 1;")
    assert migration.filename == "0000_table_listings.sql"
    assert migration.sql == "SELECT 1;"
    assert set(Migration.model_fields) == {"filename", "sql"}


def test_migration_filenames_are_ordinal_prefixed(marketplace_spec, ontology):
    migrations = compose(marketplace_spec, ontology)
    assert [m.filename for m in migrations] == [
        f"{index:04d}_{stem}.sql" for index, stem in enumerate(_stems(migrations))
    ]


# --- plan extras: conflict detection (D8 / §7.4) ---


def test_detect_conflicts_clean_for_marketplace(marketplace_spec, ontology):
    from compiler.generator.composer import detect_conflicts
    from compiler.generator.rls import rls_for

    fragments = [load("function_is_admin"), load("function_is_owner")]
    for entity in marketplace_spec.entities:
        fragments.append(load(f"table_{entity}"))
        fragments.extend(rls_for(entity, marketplace_spec, ontology))
    for bucket in marketplace_spec.buckets:
        fragments.append(load(f"bucket_{bucket.name}"))

    assert detect_conflicts(topo_sort(fragments, key="requires")) == []


def test_conflict_duplicate_bucket_raises():
    from compiler.generator.composer import detect_conflicts

    # A duplicated bucket fragment is exactly what two BucketSpecs with the
    # same name would produce.
    ordered = topo_sort([load("bucket_avatars"), load("bucket_avatars")], key="requires")
    conflicts = detect_conflicts(ordered)

    assert any("duplicate fragment id: bucket_avatars" in issue for issue in conflicts)
    assert any("duplicate bucket name: avatars" in issue for issue in conflicts)
    with pytest.raises(CompositionError):
        raise CompositionError(conflicts)


def test_compose_duplicate_fragment_raises(ontology):
    from compiler.spec.models import BackendSpec
    from compiler.spec.derive import recompute_spec
    spec = recompute_spec(BackendSpec(
        version="1.0", ontology_version=1, created_at="2025-01-01T00:00:00Z",
        features={"authentication": True, "messaging": True, "realtime": True},
        parameters={"authentication.method": "email_password",
                    "messaging.trigger_event": "after_request",
                    "realtime.channels": ["messages", "messages"]},
        roles=["user"], rls_overrides={},
        entities=[], buckets=[], edge_functions=[],
        decisions=[], defaulted=[], unsupported=[],
    ), ontology)

    with pytest.raises(CompositionError, match="duplicate fragment id: realtime_messages"):
        compose(spec, ontology)


def test_conflict_duplicate_object_name_detected():
    from compiler.generator.composer import detect_conflicts
    from compiler.generator.models import Fragment

    a = Fragment(id="a", type="table", sql="CREATE TABLE IF NOT EXISTS dup (id uuid);")
    b = Fragment(id="b", type="table", sql="CREATE TABLE IF NOT EXISTS dup (id uuid);")

    conflicts = detect_conflicts([a, b])

    assert any(issue.startswith("duplicate object name: dup") for issue in conflicts)


def test_conflict_policy_name_collision_detected():
    from compiler.generator.composer import detect_conflicts
    from compiler.generator.models import Fragment

    a = Fragment(id="a", type="rls",
                 sql="CREATE POLICY listings_select_rls ON listings FOR SELECT USING (true);")
    b = Fragment(id="b", type="rls",
                 sql="CREATE POLICY listings_select_rls ON listings FOR SELECT USING (true);")

    conflicts = detect_conflicts([a, b])

    assert any("RLS policy name collision: listings_select_rls" in issue for issue in conflicts)


def test_conflict_trigger_collision_detected():
    from compiler.generator.composer import detect_conflicts
    from compiler.generator.models import Fragment

    a = Fragment(id="a", type="trigger",
                 sql="CREATE TRIGGER t_listings BEFORE UPDATE ON listings FOR EACH ROW EXECUTE FUNCTION f();")
    b = Fragment(id="b", type="trigger",
                 sql="CREATE TRIGGER t_listings BEFORE UPDATE ON listings FOR EACH ROW EXECUTE FUNCTION f();")

    conflicts = detect_conflicts([a, b])

    assert any("trigger collision: t_listings on listings" in issue for issue in conflicts)


def test_conflict_fk_cycle_detected():
    from compiler.generator.composer import detect_conflicts
    from compiler.generator.models import Fragment

    a = Fragment(id="table_a", type="table", requires=["table_b"], sql="")
    b = Fragment(id="table_b", type="table", requires=["table_a"], sql="")

    conflicts = detect_conflicts([a, b])

    assert any(issue.startswith("FK cycle: table_a -> table_b") for issue in conflicts)


def test_conflict_ordering_violation_detected():
    from compiler.generator.composer import detect_conflicts
    from compiler.generator.models import Fragment

    dependent = Fragment(id="dependent", type="rls", requires=["base"], sql="")
    base = Fragment(id="base", type="function", sql="")

    conflicts = detect_conflicts([dependent, base])

    assert any("ordering violation: dependent requires base" in issue for issue in conflicts)


def test_composition_error_renders_every_issue():
    error = CompositionError(["first issue", "second issue"])
    assert error.issues == ["first issue", "second issue"]
    assert str(error) == "first issue; second issue"
    assert str(CompositionError("only issue")) == "only issue"


# --- review hardening: rendering, idempotent guards, integrity ---


def test_realtime_renders_channel_and_keeps_dollar_quotes(ontology):
    from compiler.spec.models import BackendSpec
    from compiler.spec.derive import recompute_spec
    spec = recompute_spec(BackendSpec(
        version="1.0", ontology_version=1, created_at="2025-01-01T00:00:00Z",
        features={"authentication": True, "messaging": True, "realtime": True},
        parameters={"messaging.trigger_event": "after_request",
                    "realtime.channels": ["messages"]},
        roles=["user"], rls_overrides={},
        entities=[], buckets=[], edge_functions=[],
        decisions=[], defaulted=[], unsupported=[],
    ), ontology)
    migrations = compose(spec, ontology)
    realtime = [m for m in migrations if m.filename.endswith("realtime_messages.sql")]
    assert realtime
    sql = realtime[0].sql
    assert "ALTER PUBLICATION supabase_realtime ADD TABLE messages;" in sql
    assert "{channel}" not in sql
    assert sql.count("$$") == 2


def test_generated_migrations_have_idempotent_guards(marketplace_spec, ontology):
    for migration in compose(marketplace_spec, ontology):
        sql = migration.sql
        # Every CREATE POLICY must be preceded by its DROP; PostgreSQL
        # errors on a re-created policy otherwise.
        if "CREATE POLICY" in sql:
            assert sql.count("DROP POLICY IF EXISTS") == sql.count("CREATE POLICY")
        # The trigger fragment runs function + DROP + CREATE every time.
        if "CREATE TRIGGER" in sql:
            assert "DROP TRIGGER IF EXISTS" in sql
        assert "{" not in sql


def test_table_fk_graph_is_acyclic():
    from compiler.generator.composer import detect_conflicts
    from compiler.generator.ordering import topo_sort
    from compiler.generator.table_fragments import table_entity_ids

    tables = [load(f"table_{entity}") for entity in table_entity_ids()]
    # topo_sort raises on a cycle; the table graph must be acyclic.
    ordered = topo_sort(tables, key="requires")
    assert detect_conflicts(ordered) == []


def test_fragment_rejects_extra_fields():
    from pydantic import ValidationError

    from compiler.generator.models import Fragment

    # A hand-edited YAML typo (`require:` instead of `requires:`) must fail
    # loudly rather than silently drop an ordering edge.
    with pytest.raises(ValidationError):
        Fragment(id="x", type="table", sql="", require=["oops"])
