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


def test_dbsmash_unavailable_reports_all_requirements(monkeypatch):
    monkeypatch.setattr(baselines.shutil, "which", lambda name: None)
    for var in ("OPENROUTER_API_KEY", "GEMINI_API_KEY", "OPEN_ROUTER_MISTRAL"):
        monkeypatch.delenv(var, raising=False)
    b = baselines.DbSmashBaseline()
    assert not b.available()
    result = b.run("a blog", case_name="c")
    assert result.skipped and "dbsmash" in result.skip_reason
    assert "OPENROUTER_API_KEY" in result.skip_reason
    assert "GEMINI_API_KEY" in result.skip_reason


def test_dbsmash_maps_our_key_to_the_tools_env(monkeypatch, tmp_path):
    """dbsmash 1.0.7 reads OPEN_ROUTER_MISTRAL (its OpenRouter path) and
    GEMINI_API_KEY (its schema agent); the adapter translates our variable."""
    seen = {}

    def fake_run(cmd, input, cwd, env, capture_output, text, encoding, errors, timeout):
        seen.update(env=env)
        Path(cwd, "src", "schemas").mkdir(parents=True, exist_ok=True)
        Path(cwd, "src", "schemas", "mermaid.mmd").write_text(
            "erDiagram\n    Listings {\n        id int PK\n    }\n"
            "    BOOKINGS {\n        id int PK\n    }\n",
            encoding="utf-8")
        class R:
            returncode = 0
            stdout = "CREATE TABLE profiles (id serial);"
            stderr = ""
        return R()

    monkeypatch.setattr(baselines.subprocess, "run", fake_run)
    monkeypatch.setattr(baselines.shutil, "which", lambda name: "C:\\npm\\dbsmash.cmd")
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    monkeypatch.setenv("GEMINI_API_KEY", "g-key")

    result = baselines.DbSmashBaseline().run(
        "x", case_name="c", gold_entities=["listings", "bookings", "profiles"])

    assert seen["env"]["OPEN_ROUTER_MISTRAL"] == "or-key"
    assert not result.skipped
    # mermaid entities are case-insensitively matched against gold
    assert result.extra["tables_found"] == 3
    assert result.extra["tables_hit"] == 3


def test_dbsmash_runs_cli_and_scores_generated_sql(monkeypatch, tmp_path):
    calls = {}

    def fake_run(cmd, input, cwd, env, capture_output, text, encoding, errors, timeout):
        calls.update(cmd=cmd, input=input, cwd=cwd, env=env, timeout=timeout)
        Path(cwd, "schema.sql").write_text(
            "CREATE TABLE posts (id serial);\nCREATE TABLE comments (id serial);",
            encoding="utf-8")
        class R:
            returncode = 0
            stdout = ""
            stderr = ""
        return R()

    monkeypatch.setattr(baselines.subprocess, "run", fake_run)
    monkeypatch.setattr(baselines.shutil, "which", lambda name: "C:\\npm\\dbsmash.cmd")
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    monkeypatch.setenv("GEMINI_API_KEY", "k")

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
    def fake_run(cmd, input, cwd, env, capture_output, text, encoding, errors, timeout):
        class R:
            returncode = 1
            stdout = ""
            stderr = "OpenRouter error: 401"
        return R()

    monkeypatch.setattr(baselines.subprocess, "run", fake_run)
    monkeypatch.setattr(baselines.shutil, "which", lambda name: "C:\\npm\\dbsmash.cmd")
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    monkeypatch.setenv("GEMINI_API_KEY", "k")

    result = baselines.DbSmashBaseline().run("x", case_name="c")
    assert result.skipped and "401" in result.skip_reason


def test_dbsmash_respects_dbsmash_cmd_override(monkeypatch):
    monkeypatch.setenv("DBSMASH_CMD", "C:\\tools\\dbsmash-cli.exe")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    b = baselines.DbSmashBaseline()
    # provider keys are still required: the tool shells out to OpenRouter
    # (intent) and calls Gemini directly (schema agent)
    assert not b.available()
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    assert b.available()
