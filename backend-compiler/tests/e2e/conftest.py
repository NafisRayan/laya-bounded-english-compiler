"""Fixtures for the nightly end-to-end tier (Developer Spec.md §18.19).

`temp_supabase_project` creates a real project through the Management API
and deletes it afterwards. It skips unless `SUPABASE_ACCESS_TOKEN` and
`SUPABASE_ORG_SLUG` are set, so CI and credential-free local runs stay
green while nightly gets a genuine deployment.
"""

import os
import uuid

import pytest
import requests

from compiler.deployer.config import DEFAULT_REGION
from compiler.deployer.supabase_api import create_project, wait_for_healthy
from tests._dotenv import load_dotenv

load_dotenv()

API_BASE = "https://api.supabase.com/v1"

#: The project is created with this password, so the deployment must use the
#: very same one (the CLI authenticates with it when applying migrations).
E2E_DB_PASS = "e2e-test-password-1234567890"


@pytest.fixture(scope="session")
def temp_supabase_project():
    token = os.environ.get("SUPABASE_ACCESS_TOKEN")
    org = os.environ.get("SUPABASE_ORG_SLUG")
    if not token or not org:
        pytest.skip(
            "SUPABASE_ACCESS_TOKEN / SUPABASE_ORG_SLUG not set; "
            "the e2e tier needs a real Supabase organization"
        )

    ref = create_project(
        name=f"laya-e2e-{uuid.uuid4().hex[:8]}",
        region=os.environ.get("SUPABASE_REGION", DEFAULT_REGION),
        org_slug=org,
        db_pass=E2E_DB_PASS,
    )
    try:
        wait_for_healthy(ref)
        yield {"ref": ref, "token": token, "db_pass": E2E_DB_PASS}
    finally:
        requests.delete(
            f"{API_BASE}/projects/{ref}",
            headers={"Authorization": f"Bearer {token}"},
        )
