"""Edge function scaffolding (Developer Spec.md §8.7)."""

import pytest

from compiler.deployer import edge_functions
from compiler.deployer.edge_functions import (
    _managed_function_names,
    deploy_edge_functions,
    scaffold_edge_functions,
)


class _FakeCompleted:
    returncode = 0
    stderr = ""


def test_managed_function_names_are_the_three_templates():
    assert _managed_function_names() == {
        "stripe_webhook",
        "verification_webhook",
        "notification_dispatch",
    }


def test_scaffold_copies_template_to_index_ts(marketplace_spec, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    spec = marketplace_spec.model_copy(update={"edge_functions": ["stripe_webhook"]})

    scaffold_edge_functions(spec)

    written = tmp_path / "supabase" / "functions" / "stripe_webhook" / "index.ts"
    template = edge_functions.TEMPLATES / "stripe_webhook.ts"
    assert written.read_text(encoding="utf-8") == template.read_text(encoding="utf-8")


def test_scaffold_removes_stale_managed_dirs_but_keeps_unmanaged(
    marketplace_spec, monkeypatch, tmp_path
):
    monkeypatch.chdir(tmp_path)
    stale = tmp_path / "supabase" / "functions" / "stripe_webhook"
    stale.mkdir(parents=True)
    (stale / "old.ts").write_text("old", encoding="utf-8")
    custom = tmp_path / "supabase" / "functions" / "my_custom"
    custom.mkdir(parents=True)

    spec = marketplace_spec.model_copy(update={"edge_functions": ["verification_webhook"]})
    scaffold_edge_functions(spec)

    assert not stale.exists()
    assert custom.exists()
    assert (tmp_path / "supabase" / "functions" / "verification_webhook" / "index.ts").exists()


def test_scaffold_unknown_function_raises(marketplace_spec, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    spec = marketplace_spec.model_copy(update={"edge_functions": ["nope"]})
    with pytest.raises(ValueError, match="no template for edge function nope"):
        scaffold_edge_functions(spec)


def test_deploy_is_noop_without_edge_functions(monkeypatch, marketplace_spec):
    def boom(*args, **kwargs):
        raise AssertionError("subprocess must not run for an empty list")

    monkeypatch.setattr(edge_functions.subprocess, "run", boom)
    spec = marketplace_spec.model_copy(update={"edge_functions": []})
    deploy_edge_functions("ref", spec)


def test_deploy_bundles_server_side_per_function(monkeypatch, marketplace_spec, tmp_path):
    monkeypatch.chdir(tmp_path)
    runs = []

    def fake_run(cmd, **kwargs):
        runs.append(cmd)
        return _FakeCompleted()

    monkeypatch.setattr(edge_functions.subprocess, "run", fake_run)
    monkeypatch.setattr(edge_functions, "supabase_cli", lambda *a: ["supabase", *a])

    spec = marketplace_spec.model_copy(update={"edge_functions": ["stripe_webhook"]})
    deploy_edge_functions("ref-3", spec)

    assert runs == [[
        "supabase", "functions", "deploy", "stripe_webhook",
        "--project-ref", "ref-3", "--use-api",
    ]]
