# tests/integration/test_remediation.py
import pytest
from compiler.deployer import deployer
from compiler.deployer.errors import MigrationError


@pytest.mark.parametrize("error_message,expected_category,should_retry", [
    ('relation "listings" already exists', "duplicate_object", True),
    ('policy "x" already exists', "rls_conflict", True),
    ('foreign key constraint "bookings_listing_id_fkey"', "fk_ordering", True),
    ('extension "pgcrypto" does not exist', "extension_missing", True),
    ('HTTP 503', "transient", True),
    ('permission denied to create extension', "permission_denied", False),
    ('exceeded max number of tables for plan', "quota_exceeded", False),
    ('syntax error at or near "XYZ"', "sql_syntax", False),
])
def test_remediation_category(monkeypatch, marketplace_spec,
                              error_message, expected_category, should_retry):
    attempts = {"apply": 0, "create": 0}

    def fake_create(*a, **k):
        attempts["create"] += 1
        return "fake-ref"

    def fake_apply(ref, db_pass, migrations):
        attempts["apply"] += 1
        raise MigrationError(error_message)

    monkeypatch.setattr(deployer, "create_project", fake_create)
    monkeypatch.setattr(deployer, "wait_for_healthy", lambda *a, **k: None)
    monkeypatch.setattr(deployer, "link_project", lambda *a, **k: None)
    monkeypatch.setattr(deployer, "apply_migrations", fake_apply)
    monkeypatch.setattr(deployer, "present_mcq", lambda opts: opts[0]["value"])

    result = deployer.deploy_with_remediation(marketplace_spec)

    assert attempts["create"] == 1
    if should_retry:
        assert attempts["apply"] >= 2
    assert result.category == expected_category


def test_max_attempts_cap_reuses_project(monkeypatch, marketplace_spec):
    attempts = {"apply": 0, "create": 0}

    def fake_create(*a, **k):
        attempts["create"] += 1
        return "ref"

    def fake_apply(ref, db_pass, migrations):
        attempts["apply"] += 1
        raise MigrationError('relation "listings" already exists')

    monkeypatch.setattr(deployer, "create_project", fake_create)
    monkeypatch.setattr(deployer, "wait_for_healthy", lambda *a, **k: None)
    monkeypatch.setattr(deployer, "link_project", lambda *a, **k: None)
    monkeypatch.setattr(deployer, "apply_migrations", fake_apply)
    monkeypatch.setattr(deployer, "present_mcq", lambda opts: opts[0]["value"])

    result = deployer.deploy_with_remediation(marketplace_spec, max_attempts=3)
    assert attempts["apply"] == 3
    assert attempts["create"] == 1
    assert not result.success
