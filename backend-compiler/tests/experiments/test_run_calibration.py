"""Offline tests for the real-Laya calibration harness (Paper §5.3).

The tests inject a fake client that returns a canned Router envelope, so no
`laya` package, torch, or network is needed — CI exercises the pair logic,
the sweep math, and the fixture-schema round trip.
"""

import json

from compiler.interpreter.calibration import expected_calibration_error
from tests.experiments.run_calibration import (
    SWEEP_THRESHOLDS,
    collect_pairs,
    sweep_thresholds,
)
from tests.experiments.runner import iter_cases, load_test_ontology


class FakeLaya:
    """Returns noul answers keyed by feature item; records the questions asked."""

    def __init__(self, noul_by_item: dict[str, float], conf: float = 0.9):
        self.noul_by_item = noul_by_item
        self.conf = conf
        self.default = 0.0
        self.calls: list[tuple[str, dict]] = []

    def predict(self, state: str, questions: dict) -> dict:
        self.calls.append((state, questions))
        answers = {}
        for qid in questions:
            item = qid[len("needs_"):]
            p = self.noul_by_item.get(item, self.default)
            answers[qid] = {
                "type": "noul",
                "noul": p,
                "confidence": max(p, 1 - p),
                "answer_confidence": self.conf,
                "action": {"act_probability": 0.5},
            }
        return {"model": "laya-rl-agent", "answers": answers,
                "usage": {}, "routing": {"model": "english"}}


def _ontology_with(features: list[str], entities: list[str]):
    ontology = load_test_ontology()
    # The shared fixture ontology is used as-is; feature membership decides
    # which pairs are kept, so the test picks items from the real fixture.
    assert all(f in ontology.features for f in features)
    return ontology


def test_collect_pairs_labels_match_gold(monkeypatch, tmp_path):
    ontology = load_test_ontology()
    cases = iter_cases()
    name, data = cases[0]
    gold = {fid: bool(v) for fid, v in
            (data.get("expected_spec") or {}).get("features", {}).items()}
    assert gold, "first golden case must pin at least one feature"

    # Answer 'yes' for every gold feature, 'no' for everything else: every
    # pair must then be labelled correct.
    yes = {fid: 0.9 for fid in gold}
    fake = FakeLaya(yes)
    pairs = collect_pairs(fake, cases[:1], ontology)

    assert fake.calls and set(fake.calls[0][1])  # questions came from laya_questions
    assert pairs
    assert all(p["case"] == name for p in pairs)
    assert all(p["label"] == 1 for p in pairs)
    assert all(p["truth"] == gold.get(p["item"], False) for p in pairs)
    # feature items only: every pair's item is an ontology feature
    assert all(p["item"] in ontology.features for p in pairs)


def test_collect_pairs_marks_wrong_decisions_and_skips_entities():
    ontology = load_test_ontology()
    cases = iter_cases()
    name, data = cases[0]
    gold = {fid: bool(v) for fid, v in
            (data.get("expected_spec") or {}).get("features", {}).items()}
    first_feature = next(iter(gold))

    # Answer 'yes' only for gold-true features, 'no' everywhere else, then
    # flip one gold-true feature to 'no': exactly one wrong decision.
    noul = {fid: (0.9 if gold.get(fid, False) else 0.1) for fid in ontology.features}
    noul[first_feature] = 0.1
    fake = FakeLaya(noul, conf=0.8)
    pairs = collect_pairs(fake, cases[:1], ontology)

    wrong = [p for p in pairs if p["item"] == first_feature]
    assert wrong and wrong[0]["label"] == 0 and wrong[0]["predicted"] is False
    assert wrong[0]["answer_confidence"] == 0.8
    assert all(p["label"] == 1 for p in pairs if p["item"] != first_feature)
    # entity items must not appear even though laya_questions asks them
    entity_items = ontology.items and [
        i for i in ontology.items if i not in ontology.features
    ]
    if entity_items:
        assert all(p["item"] not in entity_items for p in pairs)


def test_sweep_coverage_monotone_and_accuracy_none_when_empty():
    probs = [0.6, 0.7, 0.8, 0.9]
    labels = [1, 0, 1, 1]
    rows = sweep_thresholds(probs, labels, SWEEP_THRESHOLDS)

    assert [r["threshold"] for r in rows] == SWEEP_THRESHOLDS
    coverages = [r["coverage"] for r in rows]
    assert coverages == sorted(coverages, reverse=True)
    assert rows[0]["coverage"] == 1.0 and rows[0]["n"] == 4
    below = [r for r in rows if r["threshold"] > 0.9]
    assert all(r["n"] == 0 and r["accuracy"] is None for r in below)
    at_075 = next(r for r in rows if r["threshold"] == 0.75)
    assert at_075["n"] == 2 and at_075["accuracy"] == 1.0


def test_pairs_match_the_golden_calibration_fixture_schema(tmp_path):
    """The measured JSONL must reduce to exactly the fixture schema the
    §18.17 gate consumes: a bare list of {answer_confidence, label}."""
    ontology = load_test_ontology()
    cases = iter_cases()
    fake = FakeLaya({fid: 0.9 for fid in ontology.features}, conf=0.85)
    pairs = collect_pairs(fake, cases[:2], ontology)

    fixture_schema = [
        {"answer_confidence": p["answer_confidence"], "label": p["label"]}
        for p in pairs
    ]
    fixture_path = tmp_path / "calibration_set.json"
    fixture_path.write_text(json.dumps(fixture_schema), encoding="utf-8")
    loaded = json.loads(fixture_path.read_text(encoding="utf-8"))
    assert loaded and all(set(d) == {"answer_confidence", "label"} for d in loaded)

    # and the ECE function accepts the reduction directly
    ece = expected_calibration_error(
        [d["answer_confidence"] for d in loaded], [d["label"] for d in loaded])
    assert 0.0 <= ece <= 1.0
