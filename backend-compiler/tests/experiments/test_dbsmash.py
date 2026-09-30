"""Tests for the DbSmash baseline adapter (offline, subprocess faked).

DbSmash (npm, v1.0.7) is an interactive-scaffold CLI: piped stdin carries the
app description, it scaffolds into the CWD, and it calls OpenRouter
(`OPENROUTER_API_KEY`) for generation. The adapter shells out with piped
stdin in a temp dir and scores whatever CREATE TABLE statements appear in the
generated SQL.
"""

from pathlib import Path

from tests.experiments import baselines


def _fake_run_writes_sql(monkeypatch, sql):
    def fake_run(cmd, input, cwd, env, capture_output, text, timeout):
        Path(cwd, "schema.sql").write_text(sql, encoding="utf-8")
        class R:
            returncode = 0
            stderr = ""
        return R()

    monkeypatch.setattr(baselines.subprocess, "run", fake_run)


def test_dbsmash_unavailable_reports_both_requirements(monkeypatch):
    monkeypatch.setattr(baselines.shutil, "which", lambda name: None)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    b = baselines.DbSmashBaseline()
    assert not b.available()
    result = b.run("a blog", case_name="c")
    assert result.skipped and "dbsmash" in result.skip_reason
    assert "OPENROUTER_API_KEY" in result.skip_reason


def test_dbsmash_runs_cli_and_scores_generated_sql(monkeypatch, tmp_path):
    calls = {}

    def fake_run(cmd, input, cwd, env, capture_output, text, timeout):
        calls.update(cmd=cmd, input=input, cwd=cwd, env=env, timeout=timeout)
        Path(cwd, "schema.sql").write_text(
            "CREATE TABLE posts (id serial);\nCREATE TABLE comments (id serial);",
            encoding="utf-8")
        class R:
            returncode = 0
            stderr = ""
        return R()

    monkeypatch.setattr(baselines.subprocess, "run", fake_run)
    monkeypatch.setattr(baselines.shutil, "which", lambda name: "C:\\npm\\dbsmash.cmd")
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")

    b = baselines.DbSmashBaseline()
    assert b.available()
    result = b.run("A blog where users can comment on posts",
                   case_name="blog_case", gold_entities=["posts", "comments", "users"])

    assert not result.skipped
    assert calls["input"] == "A blog where users can comment on posts"
    assert any("dbsmash" in part.lower() for part in calls["cmd"])
    assert calls["env"]["OPENROUTER_API_KEY"] == "k"
    assert result.extra["tables_found"] == 2
    assert result.extra["tables_hit"] == 2
    assert "CREATE TABLE posts" in result.raw_output


def test_dbsmash_cli_failure_skips_with_stderr(monkeypatch):
    def fake_run(cmd, input, cwd, env, capture_output, text, timeout):
        class R:
            returncode = 1
            stderr = "OpenRouter error: 401"
        return R()

    monkeypatch.setattr(baselines.subprocess, "run", fake_run)
    monkeypatch.setattr(baselines.shutil, "which", lambda name: "C:\\npm\\dbsmash.cmd")
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")

    result = baselines.DbSmashBaseline().run("x", case_name="c")
    assert result.skipped and "401" in result.skip_reason


def test_dbsmash_respects_dbsmash_cmd_override(monkeypatch):
    monkeypatch.setenv("DBSMASH_CMD", "C:\\tools\\dbsmash-cli.exe")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    b = baselines.DbSmashBaseline()
    # key still required: the tool shells out to OpenRouter for generation
    assert not b.available()
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    assert b.available()
