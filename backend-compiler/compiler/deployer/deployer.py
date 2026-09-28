"""Deployment orchestration and the remediation loop (Developer Spec.md
§8.3, §8.8, §9.2).

`create_project` / `wait_for_healthy` are imported into this module's
namespace on purpose: the §18.16 harness patches them here, so the
remediation loop must resolve them as module globals at call time. The
final return carries the last seen category, which §18.16 asserts on even
when attempts run out (§9.2's literal snippet omits it).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from functools import lru_cache
from pathlib import Path

from compiler.deployer.auth_config import configure_auth
from compiler.deployer.config import ORG_SLUG, REGION, generate_db_pass, project_name
from compiler.deployer.edge_functions import deploy_edge_functions
from compiler.deployer.errors import (
    MigrationError,
    apply_remediation,
    classify_error,
    remediation_options,
)
from compiler.deployer.models import DeployResult
from compiler.deployer.supabase_api import create_project, wait_for_healthy
from compiler.generator.composer import compose
from compiler.generator.models import Migration
from compiler.ontology.loader import Ontology, load_ontology
from compiler.spec.models import BackendSpec

__all__ = [
    "apply_migrations",
    "deploy_spec",
    "deploy_with_remediation",
    "link_project",
    "present_mcq",
]

#: Compose against the shipped v1 ontology (deploy_spec has no ontology arg).
DEFAULT_ONTOLOGY_DIR = Path(__file__).resolve().parents[1] / "ontology" / "versions" / "v1"


def link_project(ref: str, db_pass: str) -> None:
    env = os.environ.copy()
    env["SUPABASE_DB_PASSWORD"] = db_pass
    subprocess.run(
        ["supabase", "link", "--project-ref", ref],
        check=True, capture_output=True, text=True, env=env,
    )


def apply_migrations(ref: str, db_pass: str, migrations: list[Migration]) -> None:
    migrations_dir = Path("supabase/migrations")

    # CRITICAL: clear stale migration files from previous attempts
    if migrations_dir.exists():
        shutil.rmtree(migrations_dir)
    migrations_dir.mkdir(parents=True, exist_ok=True)

    for m in migrations:
        (migrations_dir / m.filename).write_text(m.sql, encoding="utf-8")

    env = os.environ.copy()
    env["SUPABASE_DB_PASSWORD"] = db_pass
    result = subprocess.run(
        ["supabase", "db", "push", "--include-all"],
        check=False, capture_output=True, text=True, env=env,
    )
    if result.returncode != 0:
        raise MigrationError(result.stderr)


def present_mcq(options: list[dict[str, str]]) -> str:
    """Ask the operator to pick one remediation option (§9.3)."""
    print("Deployment hit an issue. Pick a remediation:")
    for index, option in enumerate(options):
        print(f"  [{index}] {option['label']}")
    choice = input("Option number: ")
    return options[int(choice)]["value"]


@lru_cache(maxsize=1)
def _ontology() -> Ontology:
    return load_ontology(DEFAULT_ONTOLOGY_DIR)


def deploy_spec(spec: BackendSpec, ref: str, db_pass: str) -> DeployResult:
    migrations = compose(spec, _ontology())
    apply_migrations(ref, db_pass, migrations)
    configure_auth(ref, spec)
    deploy_edge_functions(ref, spec)
    return DeployResult(success=True, ref=ref)


def deploy_with_remediation(spec: BackendSpec, max_attempts: int = 3) -> DeployResult:
    ref = None
    db_pass = generate_db_pass()
    last_error: str | Exception = "max attempts exceeded"
    last_category: str | None = None

    for attempt in range(max_attempts):
        try:
            if ref is None:
                ref = create_project(
                    name=project_name(spec), region=REGION,
                    org_slug=ORG_SLUG, db_pass=db_pass,
                )
                wait_for_healthy(ref)
                link_project(ref, db_pass)

            return deploy_spec(spec, ref, db_pass)

        except MigrationError as e:
            last_error = e
            last_category = classify_error(str(e))

            if last_category == "transient":
                time.sleep(2 ** attempt)
                continue

            remediation = remediation_options(last_category, spec, e)
            if not remediation:
                return DeployResult(success=False, error=e,
                                    category=last_category, ref=ref)

            answer = present_mcq(remediation)
            spec = apply_remediation(spec, last_category, answer)

        except Exception as e:
            # create/link/health/auth failures (HTTPError, TimeoutError,
            # CalledProcessError) must still produce an observable result
            # so the created project's ref is never lost to the caller.
            return DeployResult(success=False, error=e,
                                category=classify_error(str(e)), ref=ref)

    return DeployResult(success=False, error=last_error,
                        category=last_category, ref=ref)
