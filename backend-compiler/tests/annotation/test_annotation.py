"""Annotation tooling tests: generation is blind and the validator works."""

import yaml

from tests.annotation.generate_worksheets import generate_worksheets
from tests.annotation.validate import (
    bucket_key,
    check_worksheet,
    legal_buckets,
    legal_edge_functions,
    load_worksheets,
    param_items,
    score_worksheets,
)
from tests.experiments.metrics import extract_labels
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


def test_bucket_key_accepts_both_entry_forms():
    assert bucket_key("listings") == bucket_key({"name": "listings"})
    assert bucket_key({"name": "listings"}) == "listings"


def test_param_items_makes_list_values_hashable():
    got = param_items({"roles.role_names": ["verifier", "admin"],
                       "payments.provider": "stripe"})
    assert got == {("payments.provider", "stripe"),
                   ("roles.role_names", ("admin", "verifier"))}
    assert param_items(None) == set()


def test_legal_vocabularies_come_from_ontology():
    ontology = load_test_ontology()
    buckets = legal_buckets(ontology)
    edges = legal_edge_functions(ontology)
    assert buckets, "file_storage.bucket_purpose options must exist"
    assert "stripe_webhook" in edges
    # an unknown bucket/edge in a worksheet is flagged, a known one is not
    errors: list[str] = []
    check_worksheet("c", {"buckets": [next(iter(sorted(buckets)))],
                          "edge_functions": [next(iter(sorted(edges)))]},
                    ontology, errors)
    assert errors == []
    check_worksheet("c", {"buckets": ["nope"], "edge_functions": ["nope"]},
                    ontology, errors)
    assert any("bucket" in e for e in errors)
    assert any("edge function" in e for e in errors)


def test_score_ignores_derived_entities(tmp_path):
    name, data = iter_first_case()
    labels = extract_labels(data.get("expected_spec") or {})
    target = tmp_path / "golden"
    target.mkdir(parents=True)
    worksheet = {
        "case": name, "input": str(data["input"]),
        "features": {f: True for f in labels.feature_map},
        "parameters": dict(labels.parameters or {}),
        "roles": list(labels.roles or []),
        "buckets": [{"name": b} for b in (labels.buckets or [])],
        "edge_functions": list(labels.edge_functions or []),
        "notes": "",
    }
    (target / f"{name}.yaml").write_text(yaml.safe_dump(worksheet), encoding="utf-8")
    result = score_worksheets(tmp_path, "golden")
    # entities are derived (recompute_spec), never annotated: copying every
    # gold label except entities must yield zero disagreements
    assert result["problems"] == []
    assert result["disagreements"] == []


def iter_first_case():
    from tests.experiments.runner import iter_cases
    return iter_cases()[0]

def test_build_human_gold_applies_verdicts(tmp_path, monkeypatch):
    import tests.annotation.build_human_gold as bhg

    engine_spec = {
        "features": {"payments": True, "reviews": True},
        "parameters": {"payments.provider": "stripe"},
        "roles": ["admin"],
        "buckets": [{"name": "docs", "purpose": "documents"}],
        "edge_functions": [],
    }
    monkeypatch.setattr(
        bhg, "iter_cases",
        lambda: [("c1", {"input": "x", "expected_spec": engine_spec})])

    # worksheet: human missed payments (engine-only), invented reviews
    # (annotation-only), misread provider (annotation-only vs engine stripe),
    # invented admin role by misread.
    worksheet = {
        "case": "c1", "input": "x",
        "features": {"payments": True, "reviews": True},
        "parameters": {"payments.provider": "venmo"},
        "roles": ["admin"], "buckets": [], "edge_functions": [], "notes": "",
    }
    ann = tmp_path / "golden"
    ann.mkdir(parents=True)
    (ann / "c1.yaml").write_text(yaml.safe_dump(worksheet), encoding="utf-8")

    adjudication = {"c1": {"disagreements": [
        {"kind": "features", "item": "reviews", "side": "annotation-only",
         "verdict": "engine-wrong"},
        {"kind": "features", "item": "payments", "side": "engine-only",
         "verdict": "both-defensible"},
        {"kind": "parameters", "item": ["payments.provider", "venmo"],
         "side": "annotation-only", "verdict": "annotator-misread"},
        {"kind": "parameters", "item": ["payments.provider", "stripe"],
         "side": "engine-only", "verdict": "annotator-misread"},
        {"kind": "roles", "item": "admin", "side": "annotation-only",
         "verdict": "annotator-misread"},
    ]}}
    adj_path = tmp_path / "adj.yaml"
    adj_path.write_text(yaml.safe_dump(adjudication), encoding="utf-8")
    monkeypatch.setattr(bhg, "ADJUDICATION_PATH", adj_path)

    gold = bhg.build_human_gold(tmp_path)
    # engine-wrong -> annotation-only item stays out; engine-only
    # both-defensible does NOT enter human gold (annotator side stands);
    # engine-wrong on the annotation-only item keeps the annotator's reading
    assert gold["c1"]["features"] == {"payments": True, "reviews": True}
    # annotator-misread -> engine value restored
    assert gold["c1"]["parameters"] == {"payments.provider": "stripe"}
    assert gold["c1"]["roles"] == []
