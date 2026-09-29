"""Tests for the tiny .env loader (tests/_dotenv.py)."""

from __future__ import annotations

import os

from tests._dotenv import load_dotenv


def test_load_dotenv_sets_vars_from_file(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "environ", {})
    env = tmp_path / ".env"
    env.write_text(
        "GEMINI_API_KEY=abc123\n"
        "# a comment\n"
        "GEMINI_MODEL=\"gemini-3.5-flash\"\n"
        "\n"
        "SUPABASE_ACCESS_TOKEN='sbp_x'\n"
        "NO_EQUALS_HERE\n",
        encoding="utf-8",
    )
    load_dotenv(env)
    assert os.environ["GEMINI_API_KEY"] == "abc123"
    assert os.environ["GEMINI_MODEL"] == "gemini-3.5-flash"
    assert os.environ["SUPABASE_ACCESS_TOKEN"] == "sbp_x"


def test_load_dotenv_does_not_override_existing_env(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "environ", {"GEMINI_API_KEY": "from-shell"})
    env = tmp_path / ".env"
    env.write_text("GEMINI_API_KEY=from-file\n", encoding="utf-8")
    load_dotenv(env)
    assert os.environ["GEMINI_API_KEY"] == "from-shell"


def test_load_dotenv_missing_file_is_noop(tmp_path):
    load_dotenv(tmp_path / "does-not-exist.env")  # must not raise