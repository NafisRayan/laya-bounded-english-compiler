"""Ten-session e2e deployment battery for the deployability success rate.

Each session wraps the same three operations as tests/e2e/test_full_pipeline.py
on a FRESH project: (1) marketplace spec deploy + table/bucket verification,
(2) minimal spec deploy, (3) idempotent redeploy with no-shadow-table check.
Per-operation success/failure, wall-clock, and the tear-down result are
recorded as one JSONL line per session. Sessions run strictly sequentially
(they share the org's project quota). The battery is resumable: session
indices already present in the output file are skipped.

Usage:
    python -m tests.experiments.run_e2e_battery \
        --sessions 10 --out tests/experiments/results/e2e_battery.jsonl
"""

from __future__ import annotations

import argparse
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import requests

from compiler.deployer.config import DEFAULT_REGION, access_token
from compiler.deployer.deployer import deploy_spec, link_project
from compiler.deployer.supabase_api import API_BASE, create_project, wait_for_healthy
from compiler.generator.composer import compose
from compiler.interpreter.pipeline import run_interpreter
from compiler.mcq.pipeline import run_mcq_loop
from compiler.ontology.loader import load_ontology
from compiler.spec.validator import validate
from tests._dotenv import load_dotenv
from tests.conftest import FIXTURES, MockLayaClient, _first_choice, _make_laya_answer

load_dotenv()

E2E_DB_PASS = "e2e-test-password-1234567890"

MARKETPLACE_INPUT = (
    "Build an Airbnb-like marketplace for renting photography equipment. "
    "Owners list equipment, renters book them, owners need verification, "
    "users can message each other, payments use Stripe."
)
MINIMAL_INPUT = "Users sign up and log in with email and password."


def high_conf_laya() -> MockLayaClient:
    class HighConf(MockLayaClient):
        def predict(self, state, questions):
            answers = {}
            for qid, q in questions.items():
                if q["type"] == "noul":
                    answers[qid] = _make_laya_answer("noul", 0.95)
                elif q["type"] == "choice":
                    answers[qid] = _make_laya_answer(
                        "choice", _first_choice(q["criteria"]))
            return self._envelope(answers)
    return HighConf()


def _timed(fn, *args, **kwargs) -> dict:
    start = time.perf_counter()
    try:
        fn(*args, **kwargs)
        return {"success": True, "seconds": round(time.perf_counter() - start, 1),
                "error": None}
    except Exception as exc:  # noqa: BLE001 — a failure is data, not a crash
        return {"success": False, "seconds": round(time.perf_counter() - start, 1),
                "error": f"{type(exc).__name__}: {exc}"}


def _compile(user_input, ontology, laya):
    candidates = run_interpreter(user_input, ontology, laya=laya)
    spec, _ = run_mcq_loop(candidates, ontology, user_answers={}, laya=laya)
    if not validate(spec, ontology).ok:
        raise AssertionError("spec validation failed")
    if len(compose(spec, ontology)) == 0:
        raise AssertionError("composition produced no artifacts")
    return spec


def _public_tables(ref: str) -> set[str]:
    resp = requests.post(
        f"{API_BASE}/projects/{ref}/database/query",
        headers={"Authorization": f"Bearer {access_token()}"},
        json={"query": "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"},
    )
    resp.raise_for_status()
    return {t["tablename"] for t in resp.json()}


def _bucket_ids(ref: str) -> set[str]:
    resp = requests.post(
        f"{API_BASE}/projects/{ref}/database/query",
        headers={"Authorization": f"Bearer {access_token()}"},
        json={"query": "SELECT id FROM storage.buckets"},
    )
    resp.raise_for_status()
    return {b["id"] for b in resp.json()}


def _check(cond: bool, message: str) -> None:
    if not cond:
        raise AssertionError(message)


def _deploy_and_verify(user_input, ontology, laya, ref, expected_tables,
                       shadow_check=False):
    def op():
        spec = _compile(user_input, ontology, laya)
        link_project(ref, E2E_DB_PASS)
        result = deploy_spec(spec, ref, E2E_DB_PASS)
        if not result.success:
            raise AssertionError(f"deploy_spec failed: {result}")
        tables = _public_tables(ref)
        _check(expected_tables <= tables,
               f"missing tables: {sorted(expected_tables - tables)}")
        if shadow_check:
            _check(not [n for n in tables if n.endswith(("_new", "_old"))],
                   f"re-push created shadow tables: {sorted(tables)}")
    return op


def run_session(index: int, ontology, laya) -> dict:
    record: dict = {"session": index,
                    "started": datetime.now(timezone.utc).isoformat()}
    start = time.perf_counter()
    token = access_token()
    import os
    org = os.environ.get("SUPABASE_ORG_SLUG")
    if not token or not org:
        raise RuntimeError("SUPABASE_ACCESS_TOKEN / SUPABASE_ORG_SLUG not set")

    ref = None

    def _create():
        nonlocal ref
        ref = create_project(
            name=f"laya-e2e-{uuid.uuid4().hex[:8]}",
            region=os.environ.get("SUPABASE_REGION", DEFAULT_REGION),
            org_slug=org, db_pass=E2E_DB_PASS)
        wait_for_healthy(ref)
    record["create"] = _timed(_create)

    if record["create"]["success"]:
        def marketplace_op():
            _deploy_and_verify(
                MARKETPLACE_INPUT, ontology, laya, ref,
                {"listings", "bookings", "messages"})()
            _check("listings" in _bucket_ids(ref), "missing bucket: listings")

        record["ops"] = [
            {"name": "marketplace_deploy", **_timed(marketplace_op)},
            {"name": "minimal_deploy",
             **_timed(_deploy_and_verify(MINIMAL_INPUT, ontology, laya, ref,
                                         {"profiles"}))},
            {"name": "idempotent_redeploy",
             **_timed(_deploy_and_verify(MARKETPLACE_INPUT, ontology, laya, ref,
                                         {"listings", "bookings", "messages"},
                                         shadow_check=True))},
        ]
    else:
        record["ops"] = []

    def _teardown():
        resp = requests.delete(f"{API_BASE}/projects/{ref}",
                               headers={"Authorization": f"Bearer {token}"})
        _check(resp.status_code in (200, 202, 204),
               f"delete returned HTTP {resp.status_code}: {resp.text[:200]}")
    record["teardown"] = (_timed(_teardown) if ref
                          else {"success": True, "seconds": 0.0,
                                "error": "no project created"})
    record["wall_seconds"] = round(time.perf_counter() - start, 1)
    record["project_ref"] = ref
    return record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sessions", type=int, default=10)
    parser.add_argument("--out", type=Path,
                        default=Path(__file__).parent / "results"
                        / "e2e_battery.jsonl")
    args = parser.parse_args(argv)

    done: set[int] = set()
    if args.out.exists():
        for line in args.out.read_text(encoding="utf-8").splitlines():
            if line.strip():
                done.add(json.loads(line)["session"])
    todo = [i for i in range(1, args.sessions + 1) if i not in done]
    if not todo:
        print(f"battery already complete: {args.out}")
        return 0

    args.out.parent.mkdir(parents=True, exist_ok=True)
    ontology = load_ontology(FIXTURES / "ontology.yaml")
    laya = high_conf_laya()

    print(f"resuming: {len(done)} done, {len(todo)} to run "
          f"({', '.join(map(str, todo))})", flush=True)
    for index in todo:
        try:
            record = run_session(index, ontology, laya)
        except Exception as exc:  # noqa: BLE001 — record and continue
            record = {"session": index,
                      "started": datetime.now(timezone.utc).isoformat(),
                      "fatal_error": f"{type(exc).__name__}: {exc}"}
        with args.out.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
        ok = [o for o in record.get("ops", []) if o.get("success")]
        print(f"session {index}: create={record.get('create', {}).get('success')} "
              f"ops={len(ok)}/{len(record.get('ops', []))} ok "
              f"teardown={record.get('teardown', {}).get('success')} "
              f"wall={record.get('wall_seconds')}s "
              f"{record.get('fatal_error', '')}", flush=True)
    print(f"battery written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
