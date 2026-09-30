"""Annotation tooling tests: generation is blind and the validator works."""

import yaml

from tests.annotation.generate_worksheets import generate_worksheets
from tests.annotation.validate import (
    check_worksheet,
    load_worksheets,
    score_worksheets,
)
from tests.experiments.runner import load_test_ontology


def test_generated_worksheets_contain_no_gold(tmp_path):
    generate_worksheets(tmp_path)
    ontology = load_test_ontology()
    problems = []
    for set_name in ("golden", "held_out"):
        for case, data in load_worksheets(tmp_path, set_name).items():
            assert data["input"], f"{case}: input must be present"
            blob = yaml.safe_dump(data)
            assert "expected_spec" not in blob
            # blank schema: nothing pre-decided from the engine
            assert data["features"] == {}
            check_worksheet(case, data, ontology, problems)
    assert problems == []


def test_validator_flags_unknown_values(tmp_path):
    ontology = load_test_ontology()
    errors = []
    check_worksheet("c", {"features": {"nope": True},
                          "parameters": {"payments.provider": "venmo"}},
                    ontology, errors)
    assert any("nope" in e for e in errors)
    assert any("venmo" in e for e in errors)


def test_score_reports_disagreements_both_ways(tmp_path):
    name, data = iter_first_case()
    target = tmp_path / "golden"
    target.mkdir(parents=True)
    worksheet = {
        "case": name, "input": str(data["input"]),
        "features": {}, "parameters": {}, "roles": [], "buckets": [],
        "edge_functions": [], "notes": "",
    }
    (target / f"{name}.yaml").write_text(yaml.safe_dump(worksheet), encoding="utf-8")
    result = score_worksheets(tmp_path, "golden")
    kinds = {(d["case"], d["side"]) for d in result["disagreements"]}
    assert result["n"] == 1
    # an empty worksheet must disagree with gold on engine-only items
    assert any(side == "engine-only" for _, side in kinds)


def iter_first_case():
    from tests.experiments.runner import iter_cases
    return iter_cases()[0]
