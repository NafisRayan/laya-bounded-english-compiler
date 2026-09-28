"""Supabase Management API client (Developer Spec.md §8.1, §8.2)."""

from __future__ import annotations

import time

import requests

from compiler.deployer.config import access_token

__all__ = ["create_project", "wait_for_healthy"]

API_BASE = "https://api.supabase.com/v1"


def create_project(name: str, region: str, org_slug: str, db_pass: str) -> str:
    """Create a project and return its ref (§8.1)."""
    if not org_slug:
        raise RuntimeError(
            "SUPABASE_ORG_SLUG is not set; it names the organization that owns new projects"
        )
    resp = requests.post(
        f"{API_BASE}/projects",
        headers={"Authorization": f"Bearer {access_token()}"},
        json={
            "name": name,
            "organization_slug": org_slug,
            "region_selection": {"type": "smartGroup", "code": region},
            "db_pass": db_pass,
        },
    )
    resp.raise_for_status()
    return resp.json()["ref"]


def wait_for_healthy(ref: str, timeout: int = 600) -> None:
    """Poll project health until every service is ACTIVE_HEALTHY (§8.2)."""
    start = time.time()
    while time.time() - start < timeout:
        resp = requests.get(
            f"{API_BASE}/projects/{ref}/health",
            headers={"Authorization": f"Bearer {access_token()}"},
        )
        if all(s["status"] == "ACTIVE_HEALTHY" for s in resp.json()):
            return
        time.sleep(10)
    raise TimeoutError(f"Project {ref} did not become healthy in {timeout}s")
