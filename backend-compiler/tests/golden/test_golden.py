"""Golden end-to-end cases: text -> run_interpreter -> run_mcq_loop -> validate.

Developer Spec.md §18.13; design:
docs/superpowers/specs/2026-09-25-golden-runner-design.md (persona doubles,
text= passed, typed schema, validate_ok, absent_question_targets).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from compiler.interpreter.pipeline import run_interpreter
from compiler.mcq.pipeline import run_mcq_loop
from compiler.spec.validator import validate
from tests.conftest import MockLayaClient, _first_choice, _make_laya_answer

CASES = sorted((Path(__file__).parent / "cases").glob("*.yaml"))
assert CASES, "no golden cases found in tests/golden/cases/"


class GoldenCase(BaseModel):
    model_config = ConfigDict(extra="forbid")  # a typo'd case key must fail loudly

    input: str
    laya: Literal["default", "high", "none"] = "default"
    user_answers: dict[str, Any] = Field(default_factory=dict)
    expected_spec: dict[str, Any]
    expect_question_types: list[str] = Field(default_factory=list)
    absent_question_types: list[str] = Field(default_factory=list)
    absent_question_targets: list[str] = Field(default_factory=list)
    max_mcqs: int = 10
    validate_ok: bool = True


class _NoLaya(MockLayaClient):
    """Persona 'none': empty answers — run_interpreter always calls predict()."""

    def predict(self, state: str, questions: dict) -> dict:
        self.calls.append((state, questions))
        return self._envelope({})


class _HighConfidence(MockLayaClient):
    """Persona 'high': 0.95 noul — every needs_* proposal clears AUTO_ACCEPT."""

    def predict(self, state: str, questions: dict) -> dict:
        answers = {}
        for qid, q in questions.items():
            if q["type"] == "noul":
                answers[qid] = _make_laya_answer("noul", 0.95)
            else:
                answers[qid] = _make_laya_answer("choice", _first_choice(q["criteria"]))
        return self._envelope(answers)


def _persona(name: str) -> MockLayaClient:
    if name == "none":
        return _NoLaya()
    if name == "high":
        return _HighConfidence()
    return MockLayaClient()


def pytest_generate_tests(metafunc):
    if "case_path" in metafunc.fixturenames:
        metafunc.parametrize("case_path", CASES, ids=[c.stem for c in CASES])


def spec_matches(actual, expected: dict) -> list[tuple]:
    """Partial submatch of actual.model_dump() against expected (§18.13).

    Dict values submatch per key; an EMPTY dict value additionally pins the
    actual field to be empty ({} never means 'unchecked' — omit the key for
    that); list values compare order-insensitively (JSON-canonical sort so
    dict entries cannot crash sorted()); absent keys are unchecked. Returns
    mismatch tuples so failures print diffs.
    """
    actual_dict = actual.model_dump()
    diffs: list[tuple] = []

    def canon(items) -> list:
        return sorted(items or [], key=lambda x: json.dumps(x, sort_keys=True, default=str))

    for key, expected_val in expected.items():
        actual_val = actual_dict.get(key)
        if isinstance(expected_val, dict):
            actual_sub = actual_val or {}
            if not expected_val and actual_sub:
                diffs.append((key, None, {}, actual_sub))
            for k, v in expected_val.items():
                if actual_sub.get(k) != v:
                    diffs.append((key, k, v, actual_sub.get(k)))
        elif isinstance(expected_val, list):
            if canon(actual_val) != canon(expected_val):
                diffs.append((key, None, expected_val, actual_val))
        elif actual_val != expected_val:
            diffs.append((key, None, expected_val, actual_val))
    return diffs


def test_golden(case_path, ontology):
    case = GoldenCase.model_validate(yaml.safe_load(case_path.read_text(encoding="utf-8")))
    mock = _persona(case.laya)

    candidates = run_interpreter(case.input, ontology, laya=mock)
    spec, mcqs = run_mcq_loop(candidates, ontology,
                              user_answers=case.user_answers,
                              text=case.input,
                              laya=mock,
                              max_mcqs=case.max_mcqs)

    diffs = spec_matches(spec, case.expected_spec)
    assert not diffs, f"{case_path.stem}: spec mismatch — {diffs}"
    for qtype in case.expect_question_types:
        assert any(q.type == qtype for q in mcqs), (
            f"{case_path.stem}: expected a {qtype} question, "
            f"got {[(q.type, q.target) for q in mcqs]}")
    for qtype in case.absent_question_types:
        assert not [q for q in mcqs if q.type == qtype], (
            f"{case_path.stem}: {qtype} should be absent, "
            f"got {[(q.type, q.target) for q in mcqs]}")
    for target in case.absent_question_targets:
        assert not [q for q in mcqs if q.target == target], (
            f"{case_path.stem}: nothing should target {target}, "
            f"got {[(q.type, q.target) for q in mcqs]}")
    assert len(mcqs) <= case.max_mcqs, (
        f"{case_path.stem}: {len(mcqs)} questions exceed max_mcqs={case.max_mcqs}")
    result = validate(spec, ontology)
    assert result.ok == case.validate_ok, (
        f"{case_path.stem}: validate ok={result.ok}, expected "
        f"{case.validate_ok}: {result.errors}")
