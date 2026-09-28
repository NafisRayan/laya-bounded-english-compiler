# tests/integration/test_idempotency.py
import hashlib

import psycopg
import pytest

from compiler.generator.composer import compose


def _hash_migrations(migrations):
    blob = "\n--SPLIT--\n".join(m.sql for m in migrations)
    return hashlib.sha256(blob.encode()).hexdigest()


@pytest.mark.parametrize("spec_fixture", ["minimal_spec", "marketplace_spec"])
def test_compile_twice_identical(spec_fixture, request, ontology):
    spec = request.getfixturevalue(spec_fixture)
    first = _hash_migrations(compose(spec, ontology))
    second = _hash_migrations(compose(spec, ontology))
    assert first == second


def test_migrations_apply_twice_cleanly(marketplace_spec, ontology, fresh_db):
    migrations = compose(marketplace_spec, ontology)
    with psycopg.connect(fresh_db, autocommit=True) as conn:
        for m in migrations:
            conn.execute(m.sql)
    with psycopg.connect(fresh_db, autocommit=True) as conn:
        for m in migrations:
            conn.execute(m.sql)


def test_policy_drop_create_present(marketplace_spec, ontology):
    import re
    combined = "\n".join(m.sql for m in compose(marketplace_spec, ontology))
    creates = re.findall(r"CREATE POLICY (\w+)", combined)
    drops = re.findall(r"DROP POLICY IF EXISTS (\w+)", combined)
    assert set(creates).issubset(set(drops))


# --- hardening extra (plan): the auth-only spec must also apply cleanly ---
# PL/pgSQL defers is_owner()'s `listings` lookup to first call, so a spec
# with authentication but no bookings still compiles to executable SQL.
def test_minimal_spec_applies_cleanly(minimal_spec, ontology, fresh_db):
    migrations = compose(minimal_spec, ontology)
    assert migrations
    with psycopg.connect(fresh_db, autocommit=True) as conn:
        for m in migrations:
            conn.execute(m.sql)