"""Shared fixtures for all tests (Developer Spec.md §18.2).

`ontology` loads the merged bundle fixture exactly as the spec specifies;
it is kept in parity with ``compiler/ontology/versions/v1`` by
``tests/unit/test_ontology.py``.

Also hosts the Laya test doubles from §18.2: ``MockLayaClient`` (the
envelope-shaped contract test double), ``_make_laya_answer`` (single-answer
builder mirroring the real library shape) and ``_first_choice``.
"""

import json
from pathlib import Path

import pytest

from compiler.interpreter.laya_client import LayaClient
from compiler.ontology.loader import Ontology, load_ontology
from compiler.spec.derive import recompute_spec
from compiler.spec.models import BackendSpec, Decision

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def ontology() -> Ontology:
    return load_ontology(FIXTURES / "ontology.yaml")


@pytest.fixture
def minimal_spec(ontology) -> BackendSpec:
    spec = BackendSpec(
        version="1.0", ontology_version=1, created_at="2025-01-01T00:00:00Z",
        features={"authentication": True},
        parameters={"authentication.method": "email_password"},
        roles=["user"], rls_overrides={},
        entities=[], buckets=[], edge_functions=[],
        decisions=[
            Decision(capability_id="authentication.enabled",
                     value=True, confidence=0.95, source="user", evidence=None),
        ],
        defaulted=[], unsupported=[],
    )
    return recompute_spec(spec, ontology)


@pytest.fixture
def marketplace_spec(ontology) -> BackendSpec:
    spec = BackendSpec(
        version="1.0", ontology_version=1, created_at="2025-01-01T00:00:00Z",
        features={
            "authentication": True, "bookings": True, "messaging": True,
            "payments": True, "file_storage": True,
        },
        parameters={
            "authentication.method": "email_password",
            "bookings.mode": "owner_approval",
            "messaging.trigger_event": "after_request",
            "payments.provider": "stripe",
            "file_storage.bucket_purpose": "listings",
        },
        roles=["user", "owner", "renter"], rls_overrides={},
        entities=[], buckets=[], edge_functions=[],
        decisions=[], defaulted=[], unsupported=[],
    )
    return recompute_spec(spec, ontology)


def _first_choice(criteria) -> str:
    """
    v1.9 — criteria may be either a list of option labels or a dict
    {label: description}. Return the first label in either case.
    """
    if isinstance(criteria, dict):
        return next(iter(criteria))
    if isinstance(criteria, (list, tuple)):
        return criteria[0]
    raise TypeError(f"unsupported criteria type: {type(criteria)}")


def _make_laya_answer(qtype: str, value, act_probability: float = 0.5) -> dict:
    """
    v1.10 — mirrors the real laya envelope for a single answer.

    Real single-predict shape (agent.py:699-707, 660-675):
      {
        "type":              "noul" | "choice",
        "noul" | "choice":   <raw value>,
        "confidence":        <max(p, 1-p)>,
        "answer_confidence": <ECE-calibrated>,
        "action":            {"act_probability": <float>},
      }

    `act_probability` comes from a SEPARATE action head (`act[r, 0]`)
    trained independently of the option logits (agent.py:676). It is
    NOT `noul`/`confidence` and must not be conflated with them. The
    mock does not simulate the action head, so this defaults to a
    fixed, documented value; a contract test that depends on the act
    value must pin it explicitly.
    """
    if qtype == "noul":
        p = float(value)
        return {
            "type": "noul",
            "noul": p,
            "confidence": max(p, 1 - p),
            "answer_confidence": max(p, 1 - p),
            "action": {"act_probability": act_probability},
        }
    if qtype == "choice":
        return {
            "type": "choice",
            "choice": value,
            "confidence": 1.0,
            "answer_confidence": 1.0,
            "action": {"act_probability": act_probability},
        }
    raise ValueError(f"unknown qtype {qtype}")


class MockLayaClient(LayaClient):
    """
    v1.9 — returns the real library envelope, matching both top-level
    and per-answer shapes.

    Real top-level shape (router.py:435, 557; agent.py:817):
      {
        "model":   "laya-rl-agent",                  # constant
        "answers": { qid: {...}, ... },
        "usage":   {"input_tokens": ..., "output_tokens": ...},
        "routing": {"model": ..., "repo": ..., "reason": ...},
      }

    The mock is a contract test double: if the interpreter reads a
    field, the mock must supply it. If it doesn't, the wiring bug
    goes unnoticed. The mock does not simulate the action head
    (agent.py:676 — a separately trained head), so mock answers use
    the fixed default `act_probability` from `_make_laya_answer`,
    which is independent of `noul`/`confidence`.
    """

    CONSTANT_MODEL = "laya-rl-agent"

    def __init__(self, responses: dict[str, dict] | None = None,
                 checkpoint: str = "english",
                 repo: str = "convaiinnovations/laya"):
        # v1.10 — super().__init__() is deliberately NOT called: it builds a
        # real Router with preload=True (downloads ~800MB of weights) and
        # loads calibration.json. Every LayaClient method that touches that
        # state is overridden below, so the mock never needs it. The None
        # placeholders make a future LayaClient method that forgets to
        # override fail loudly at dev time (AttributeError) instead of
        # silently using a parent that was never constructed.
        self.router = None
        self.calibration = None
        self.responses = responses or {}
        self.checkpoint = checkpoint
        self.repo = repo
        self.calls: list[tuple[str, dict]] = []

    def predict(self, state: str, questions: dict) -> dict:
        self.calls.append((state, questions))
        key = self._key(state, questions)
        if key in self.responses:
            return self.responses[key]

        answers = {}
        for qid, q in questions.items():
            if q["type"] == "noul":
                answers[qid] = _make_laya_answer("noul", 0.5)
            elif q["type"] == "choice":
                answers[qid] = _make_laya_answer("choice", _first_choice(q["criteria"]))
        return self._envelope(answers)

    def predict_batch(self, states: list[str], questions: dict) -> list[dict]:
        return [self.predict(s, questions) for s in states]

    def calibrated_confidence(self, answer: dict) -> float:
        # Mock: pass-through; ECE test uses this
        return answer["answer_confidence"]

    def _envelope(self, answers: dict) -> dict:
        return {
            "model": self.CONSTANT_MODEL,
            "answers": answers,
            "usage": {"input_tokens": 0, "output_tokens": 0},
            "routing": {
                "model": self.checkpoint,
                "repo": self.repo,
                "reason": "pinned",
            },
        }

    @staticmethod
    def _key(state: str, questions: dict) -> str:
        import hashlib
        blob = json.dumps({"state": state, "questions": questions}, sort_keys=True)
        return hashlib.sha256(blob.encode()).hexdigest()[:16]


@pytest.fixture
def mock_laya() -> MockLayaClient:
    return MockLayaClient()


@pytest.fixture
def mock_laya_high_confidence() -> MockLayaClient:
    class HighConf(MockLayaClient):
        def predict(self, state, questions):
            answers = {}
            for qid, q in questions.items():
                if q["type"] == "noul":
                    answers[qid] = _make_laya_answer("noul", 0.95)
                elif q["type"] == "choice":
                    answers[qid] = _make_laya_answer("choice", _first_choice(q["criteria"]))
            return self._envelope(answers)
    return HighConf()