"""Unit tests for the experiment tier (metrics + mechanism toggle + runner).

The abstraction harness is what feeds Paper.md §5.2, so its scoring contract
and the mechanism subsetting are pinned here.
"""

from __future__ import annotations

from datetime import datetime, timezone

from compiler.interpreter.pipeline import run_interpreter
from compiler.spec.models import BackendSpec
from tests.conftest import MockLayaClient
from tests.experiments.metrics import extract_labels, score
from tests.experiments.personas import build_persona
from tests.experiments.runner import iter_cases, run_case
from tests.golden.test_golden import GoldenCase


def _spec(features: dict[str, bool], parameters: dict | None = None,
          roles: list[str] | None = None,
          entities: list[str] | None = None) -> BackendSpec:
    return BackendSpec(
        version="1.0", ontology_version=1,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        features=features, parameters=parameters or {}, roles=roles or [],
        rls_overrides={}, entities=entities or [], decisions=[], defaulted=[],
        unsupported=[],
    )


def test_score_precision_recall_omissions_hallucinations():
    labels = extract_labels({
        "features": {"bookings": True, "payments": True},
        "parameters": {"payments.provider": "stripe"},
    })
    m = score(_spec(features={"bookings": True, "payments": True, "reviews": True},
                    parameters={"payments.provider": "stripe"}),
              labels)
    assert m.true_positives == 2
    assert m.omissions == 0
    assert m.hallucinations == 1          # reviews: added, not in gold
    assert m.precision == 2 / 3
    assert m.recall == 1.0
    assert m.params_match is True


def test_score_empty_gold_convention():
    # A pure-negation case: gold enables nothing. Enabling nothing scores 1.0;
    # enabling anything is a hallucination.
    labels = extract_labels({"features": {"bookings": False, "payments": False}})
    clean = score(_spec(features={}), labels)
    assert clean.recall == 1.0 and clean.precision == 1.0
    assert clean.omissions == 0 and clean.hallucinations == 0
    noisy = score(_spec(features={"bookings": True}), labels)
    assert noisy.recall != 1.0 and noisy.hallucinations == 1


def test_score_params_match_gold_only():
    labels = extract_labels({"parameters": {"authentication.method": "magic_link"}})
    m = score(_spec(features={"authentication": True},
                    parameters={"authentication.method": "magic_link",
                                "bookings.mode": "instant"}),
              labels)
    assert m.params_match is True          # extra actual params are not scored


def test_score_dimensions_pinned_vs_unpinned():
    labels = extract_labels({"features": {"bookings": True}, "roles": ["user"]})
    m = score(_spec(features={"bookings": True}, roles=["user"]), labels)
    assert m.roles_match is True
    assert m.entities_match is None        # case pinned no entities dimension


def test_mechanisms_toggle_filters_candidates(mock_laya, ontology):
    text = "Use stripe for payments and email password for login"
    all_c = run_interpreter(text, ontology, laya=mock_laya, mechanisms="ABC")
    assert {c.source for c in all_c} == {"exact", "phrase", "laya"}
    a_only = run_interpreter(text, ontology, laya=mock_laya, mechanisms="A")
    assert {c.source for c in a_only} == {"exact"}
    rules = run_interpreter(text, ontology, laya=mock_laya, mechanisms="AB")
    assert {c.source for c in rules} <= {"exact", "phrase", "phrase_negated"}
    assert len(mock_laya.calls) == 1       # mechanism C not contacted again
    laya_only = run_interpreter(text, ontology, laya=mock_laya, mechanisms="C")
    assert {c.source for c in laya_only} == {"laya"}
    assert len(mock_laya.calls) == 2


def test_run_case_matches_golden_flow_for_every_case(ontology):
    # The hybrid + MCQ-on config must reproduce the golden suite's spec on
    # every case — one reason the ablation numbers are trustworthy.
    for case_name, data in iter_cases():
        GoldenCase.model_validate(data)   # case files must stay well-formed
        m = run_case(case_name, data, ontology, "ABC", mcq_on=True)
        assert m.omissions == 0, case_name
        assert m.entities_match is not False, case_name
        assert m.params_match is not False, case_name


def test_persona_builder_contract():
    assert isinstance(build_persona("default"), MockLayaClient)
    assert isinstance(build_persona("high"), MockLayaClient)
    none = build_persona("none")
    resp = none.predict("x", {})
    assert resp["answers"] == {}

def test_run_case_uses_an_injected_laya_client(ontology):
    """--real-laya plumbing: the injected client replaces the persona and is
    named in the metrics row, so real-checkpoint runs are distinguishable."""

    class RecordingClient(MockLayaClient):
        def predict(self, state, questions):
            self.calls.append((state, questions))
            return self._envelope({})

    client = RecordingClient()
    name, data = iter_cases()[0]

    metrics = run_case(name, data, ontology, "C", mcq_on=False,
                       laya_client=client, persona_label="real-english")

    assert client.calls, "injected client must be used for mechanism C"
    assert metrics.persona == "real-english"


def test_run_case_default_still_uses_the_case_persona(ontology):
    name, data = iter_cases()[0]
    metrics = run_case(name, data, ontology, "AB", mcq_on=False)
    assert metrics.persona == str(data.get("laya", "default"))
