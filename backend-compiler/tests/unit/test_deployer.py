"""Deployer orchestration (Developer Spec.md §8.3, §8.8, §9.2)."""

import pytest

from compiler.deployer import deployer
from compiler.deployer.deployer import (
    apply_migrations,
    deploy_spec,
    deploy_with_remediation,
    link_project,
)
from compiler.deployer.errors import MigrationError
from compiler.deployer.models import DeployResult
from compiler.generator.composer import compose


class _FakeCompleted:
    def __init__(self, returncode=0, stderr=""):
        self.returncode = returncode
        self.stderr = stderr


def test_apply_migrations_writes_and_clears_stale_files(
    monkeypatch, tmp_path, marketplace_spec, ontology
):
    monkeypatch.chdir(tmp_path)
    migrations_dir = tmp_path / "supabase" / "migrations"
    migrations_dir.mkdir(parents=True)
    (migrations_dir / "9999_stale.sql").write_text("-- stale", encoding="utf-8")

    runs = []

    def fake_run(*args, **kwargs):
        runs.append((args, kwargs))
        return _FakeCompleted()

    monkeypatch.setattr(deployer.subprocess, "run", fake_run)
    monkeypatch.setattr(deployer, "supabase_cli", lambda *a: ["supabase", *a])

    migrations = compose(marketplace_spec, ontology)
    apply_migrations("ref", "db-pass", migrations)

    written = sorted(p.name for p in migrations_dir.iterdir())
    assert written == [m.filename for m in migrations]
    assert runs and runs[0][0][0] == ["supabase", "db", "push", "--include-all"]
    assert runs[0][1]["env"]["SUPABASE_DB_PASSWORD"] == "db-pass"


def test_apply_migrations_raises_on_failure(monkeypatch, tmp_path, marketplace_spec, ontology):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        deployer.subprocess, "run", lambda *a, **k: _FakeCompleted(returncode=1, stderr="boom")
    )
    migrations = compose(marketplace_spec, ontology)
    with pytest.raises(MigrationError, match="boom"):
        apply_migrations("ref", "pw", migrations)


def test_link_project_passes_db_password(monkeypatch):
    runs = {}

    def fake_run(cmd, **kwargs):
        runs["cmd"] = cmd
        runs["kwargs"] = kwargs
        return _FakeCompleted()

    monkeypatch.setattr(deployer.subprocess, "run", fake_run)
    monkeypatch.setattr(deployer, "supabase_cli", lambda *a: ["supabase", *a])

    link_project("ref-9", "secret")

    assert runs["cmd"] == ["supabase", "link", "--project-ref", "ref-9"]
    assert runs["kwargs"]["env"]["SUPABASE_DB_PASSWORD"] == "secret"


def test_deploy_spec_happy_path(monkeypatch, marketplace_spec):
    calls = []
    monkeypatch.setattr(
        deployer, "apply_migrations",
        lambda ref, pw, migrations: calls.append(("apply", ref, len(migrations))),
    )
    monkeypatch.setattr(deployer, "configure_auth", lambda ref, spec: calls.append(("auth", ref)))
    monkeypatch.setattr(
        deployer, "deploy_edge_functions", lambda ref, spec: calls.append(("edge", ref))
    )

    result = deploy_spec(marketplace_spec, "ref-1", "pw")

    assert result == DeployResult(success=True, ref="ref-1")
    assert calls[0][:2] == ("apply", "ref-1")
    assert calls[0][2] > 0
    assert ("auth", "ref-1") in calls
    assert ("edge", "ref-1") in calls


def test_deploy_with_remediation_transient_retries_same_project(monkeypatch, marketplace_spec):
    attempts = {"apply": 0, "create": 0, "sleep": []}

    def fake_create(*a, **k):
        attempts["create"] += 1
        return "ref"

    def fake_apply(ref, db_pass, migrations):
        attempts["apply"] += 1
        raise MigrationError("HTTP 503")

    monkeypatch.setattr(deployer, "create_project", fake_create)
    monkeypatch.setattr(deployer, "wait_for_healthy", lambda *a, **k: None)
    monkeypatch.setattr(deployer, "link_project", lambda *a, **k: None)
    monkeypatch.setattr(deployer, "apply_migrations", fake_apply)
    monkeypatch.setattr(deployer.time, "sleep", lambda seconds: attempts["sleep"].append(seconds))

    result = deploy_with_remediation(marketplace_spec)

    assert attempts["apply"] == 3
    assert attempts["create"] == 1
    assert attempts["sleep"] == [1, 2, 4]
    assert result.success is False
    assert result.category == "transient"
    assert result.ref == "ref"


def test_deploy_with_remediation_non_retryable_escalates(monkeypatch, marketplace_spec):
    attempts = {"apply": 0}

    def fake_create(*a, **k):
        return "ref"

    def fake_apply(ref, db_pass, migrations):
        attempts["apply"] += 1
        raise MigrationError('syntax error at or near "XYZ"')

    monkeypatch.setattr(deployer, "create_project", fake_create)
    monkeypatch.setattr(deployer, "wait_for_healthy", lambda *a, **k: None)
    monkeypatch.setattr(deployer, "link_project", lambda *a, **k: None)
    monkeypatch.setattr(deployer, "apply_migrations", fake_apply)

    result = deploy_with_remediation(marketplace_spec)

    assert attempts["apply"] == 1
    assert result.success is False
    assert result.category == "sql_syntax"


def test_deploy_with_remediation_reuses_project_after_mcq(monkeypatch, marketplace_spec):
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

    result = deploy_with_remediation(marketplace_spec)

    assert attempts["apply"] == 3
    assert attempts["create"] == 1
    assert result.success is False
    assert result.category == "duplicate_object"


def test_present_mcq_returns_selected_value(monkeypatch, capsys):
    options = [{"label": "First", "value": "first"}, {"label": "Second", "value": "second"}]
    monkeypatch.setattr("builtins.input", lambda prompt="": "1")
    assert deployer.present_mcq(options) == "second"
    assert "Deployment hit an issue" in capsys.readouterr().out


def test_deploy_result_defaults():
    result = DeployResult(success=False)
    assert result.ref is None
    assert result.error is None
    assert result.category is None
