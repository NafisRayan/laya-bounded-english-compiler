"""Management API client + config (Developer Spec.md §8.1, §8.2)."""

import pytest

from compiler.deployer import supabase_api
from compiler.deployer.config import access_token, generate_db_pass, project_name


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_create_project_requires_org_slug(monkeypatch):
    def fail_post(*args, **kwargs):
        raise AssertionError("must not POST without an organization")

    monkeypatch.setattr(supabase_api.requests, "post", fail_post)
    with pytest.raises(RuntimeError, match="SUPABASE_ORG_SLUG"):
        supabase_api.create_project("laya-x", "ap-southeast-1", "", "pw")


def test_create_project_posts_spec_payload(monkeypatch):
    calls = {}

    def fake_post(url, headers=None, json=None):
        calls.update(url=url, headers=headers, json=json)
        return _FakeResponse({"ref": "abc123"})

    monkeypatch.setattr(supabase_api, "access_token", lambda: "tok")
    monkeypatch.setattr(supabase_api.requests, "post", fake_post)

    ref = supabase_api.create_project("laya-x", "ap-southeast-1", "my-org", "pw")

    assert ref == "abc123"
    assert calls["url"] == "https://api.supabase.com/v1/projects"
    assert calls["headers"] == {"Authorization": "Bearer tok"}
    assert calls["json"] == {
        "name": "laya-x",
        "organization_slug": "my-org",
        "region_selection": {"type": "smartGroup", "code": "ap-southeast-1"},
        "db_pass": "pw",
    }


def test_wait_for_healthy_returns_when_all_active(monkeypatch):
    monkeypatch.setattr(supabase_api, "access_token", lambda: "tok")
    monkeypatch.setattr(supabase_api.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(
        supabase_api.requests, "get",
        lambda *a, **k: _FakeResponse([{"status": "ACTIVE_HEALTHY"}]),
    )
    supabase_api.wait_for_healthy("ref")


def test_wait_for_healthy_times_out(monkeypatch):
    monkeypatch.setattr(supabase_api, "access_token", lambda: "tok")
    monkeypatch.setattr(supabase_api.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(
        supabase_api.requests, "get",
        lambda *a, **k: _FakeResponse([{"status": "IN_PROGRESS"}]),
    )
    with pytest.raises(TimeoutError):
        supabase_api.wait_for_healthy("ref", timeout=1)


def test_access_token_missing_raises(monkeypatch):
    monkeypatch.delenv("SUPABASE_ACCESS_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="SUPABASE_ACCESS_TOKEN"):
        access_token()


def test_project_name_is_deterministic_per_features(minimal_spec, marketplace_spec):
    assert project_name(marketplace_spec) == project_name(marketplace_spec)
    assert project_name(minimal_spec) != project_name(marketplace_spec)


def test_generate_db_pass_is_urlsafe_and_fresh():
    first, second = generate_db_pass(), generate_db_pass()
    assert first != second
    assert len(first) >= 20
