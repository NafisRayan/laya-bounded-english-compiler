"""Auth config payloads (Developer Spec.md §8.4)."""

import pytest

from compiler.deployer import auth_config


class _FakeResponse:
    def raise_for_status(self):
        return None


@pytest.fixture
def patch_capture(monkeypatch):
    calls = {}

    def fake_patch(url, headers=None, json=None):
        calls["url"] = url
        calls["headers"] = headers
        calls["json"] = json
        return _FakeResponse()

    monkeypatch.setattr(auth_config, "access_token", lambda: "token-123")
    monkeypatch.setattr(auth_config.requests, "patch", fake_patch)
    return calls


def test_email_password_payload(marketplace_spec, patch_capture):
    auth_config.configure_auth("ref-1", marketplace_spec)
    assert patch_capture["url"] == "https://api.supabase.com/v1/projects/ref-1/config/auth"
    assert patch_capture["headers"] == {"Authorization": "Bearer token-123"}
    assert patch_capture["json"] == {"external_email_enabled": True}


@pytest.mark.parametrize("method,extra", [
    ("oauth_google", {"external_google_enabled": True}),
    ("magic_link", {"mailer_autoconfirm": True}),
    ("oauth_github", {"external_github_enabled": True}),
])
def test_method_payloads(method, extra):
    payload = auth_config.auth_payload(method)
    assert payload == {"external_email_enabled": True, **extra}


def test_missing_method_defaults_to_email_password(marketplace_spec, patch_capture):
    spec = marketplace_spec.model_copy(update={"parameters": {}})
    auth_config.configure_auth("ref-2", spec)
    assert patch_capture["json"] == {"external_email_enabled": True}
