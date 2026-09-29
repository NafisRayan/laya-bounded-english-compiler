"""Environment-driven deployer configuration (Developer Spec.md §8.1, §9.2).

`SUPABASE_ACCESS_TOKEN` and `SUPABASE_ORG_SLUG` are required for real
deployments; `SUPABASE_REGION` defaults to the APAC smart-group code
(`apac`; the API accepts only `americas` | `emea` | `apac`). Tests never
hit the network, so these accessors only run on live paths.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import shutil

from compiler.spec.models import BackendSpec

__all__ = [
    "ORG_SLUG",
    "REGION",
    "access_token",
    "generate_db_pass",
    "project_name",
    "supabase_cli",
]

DEFAULT_REGION = "apac"

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


def supabase_cli(*args: str) -> list[str]:
    """Resolve the Supabase CLI into an argv list that can be executed.

    `npm install -g supabase` only puts shims (a `.cmd`/`.ps1` wrapper around
    a binary in the package tree) on PATH. Windows' `CreateProcess` runs
    executables, not shell scripts, so on Windows a shim is invoked through
    `cmd` rather than passed straight to `subprocess`.
    """
    exe = shutil.which("supabase.exe") or shutil.which("supabase")
    if exe is None:
        raise FileNotFoundError(
            "the Supabase CLI is required for deployment; install it with "
            "`npm install -g supabase`"
        )
    if os.name == "nt" and not exe.lower().endswith(".exe"):
        return ["cmd", "/c", exe, *args]
    return [exe, *args]
