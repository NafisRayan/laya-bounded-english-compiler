# tests/e2e/test_full_pipeline.py
import pytest
import requests

from compiler.deployer.deployer import deploy_spec, link_project
from compiler.generator.composer import compose
from compiler.interpreter.pipeline import run_interpreter
from compiler.mcq.pipeline import run_mcq_loop
from compiler.spec.validator import validate


@pytest.mark.slow
def test_full_pipeline_creates_working_project(
    ontology, mock_laya_high_confidence, temp_supabase_project
):
    user_input = (
        "Build an Airbnb-like marketplace for renting photography equipment. "
        "Owners list equipment, renters book them, owners need verification, "
        "users can message each other, payments use Stripe."
    )

    candidates = run_interpreter(user_input, ontology, laya=mock_laya_high_confidence)
    spec, mcqs = run_mcq_loop(candidates, ontology, user_answers={},
                              laya=mock_laya_high_confidence)

    assert validate(spec, ontology).ok
    assert len(compose(spec, ontology)) > 0

    ref = temp_supabase_project["ref"]
    link_project(ref, temp_supabase_project["db_pass"])
    result = deploy_spec(spec, ref, temp_supabase_project["db_pass"])
    assert result.success

    tables = requests.post(
        f"https://api.supabase.com/v1/projects/{ref}/database/query",
        headers={"Authorization": f"Bearer {temp_supabase_project['token']}"},
        json={"query": "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"},
    ).json()
    names = {t["tablename"] for t in tables}
    assert {"listings", "bookings", "messages"} <= names

    buckets = requests.post(
        f"https://api.supabase.com/v1/projects/{ref}/database/query",
        headers={"Authorization": f"Bearer {temp_supabase_project['token']}"},
        json={"query": "SELECT id FROM storage.buckets"},
    ).json()
    assert "listings" in {b["id"] for b in buckets}
