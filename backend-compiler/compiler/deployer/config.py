"""Environment-driven deployer configuration (Developer Spec.md §8.1, §9.2).

`SUPABASE_ACCESS_TOKEN` and `SUPABASE_ORG_SLUG` are required for real
deployments; `SUPABASE_REGION` defaults to Singapore's smart-group code.
Tests never hit the network, so these accessors only run on live paths.
"""

from __future__ import annotations

import hashlib
import os
import secrets

from compiler.spec.models import BackendSpec

__all__ = [
    "ORG_SLUG",
    "REGION",
    "access_token",
    "generate_db_pass",
    "project_name",
]

DEFAULT_REGION = "ap-southeast-1"

#: §9.2 calls `create_project(..., region=REGION, org_slug=ORG_SLUG, ...)`
#: with import-time constants, so the remediation loop never touches the
#: environment. An empty `ORG_SLUG` fails loudly in the real
#: `create_project` (supabase_api validates before the POST).
REGION = os.environ.get("SUPABASE_REGION", DEFAULT_REGION)
ORG_SLUG = os.environ.get("SUPABASE_ORG_SLUG", "")


def access_token() -> str:
    token = os.environ.get("SUPABASE_ACCESS_TOKEN")
    if not token:
        raise RuntimeError(
            "SUPABASE_ACCESS_TOKEN is not set; create a personal access token at "
            "https://supabase.com/dashboard/account/tokens"
        )
    return token


def generate_db_pass() -> str:
    """A fresh database password per deployment (never logged, never stored)."""
    return secrets.token_urlsafe(24)


def project_name(spec: BackendSpec) -> str:
    """Deterministic, CLI-safe project name derived from enabled features."""
    enabled = "".join(sorted(feature for feature, on in spec.features.items() if on))
    digest = hashlib.sha256(enabled.encode()).hexdigest()[:8]
    return f"laya-{digest}"
