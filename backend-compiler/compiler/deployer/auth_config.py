"""Auth configuration via the Management API (Developer Spec.md §8.4)."""

from __future__ import annotations

import requests

from compiler.deployer.config import access_token
from compiler.spec.models import BackendSpec

__all__ = ["auth_payload", "configure_auth"]

API_BASE = "https://api.supabase.com/v1"


def auth_payload(method: str) -> dict[str, bool]:
    """The §8.4 config payload for one authentication method."""
    payload = {"external_email_enabled": True}
    if method == "oauth_google":
        payload["external_google_enabled"] = True
    elif method == "magic_link":
        payload["mailer_autoconfirm"] = True
    elif method == "oauth_github":
        payload["external_github_enabled"] = True
    return payload


def configure_auth(ref: str, spec: BackendSpec) -> None:
    method = spec.parameters.get("authentication.method", "email_password")
    resp = requests.patch(
        f"{API_BASE}/projects/{ref}/config/auth",
        headers={"Authorization": f"Bearer {access_token()}"},
        json=auth_payload(method),
    )
    resp.raise_for_status()
