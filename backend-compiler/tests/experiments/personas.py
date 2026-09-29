"""Golden-case Laya personas for experiment runs.

Personas are the same contract doubles the golden suite uses
(``tests.conftest`` / ``tests.golden.test_golden``): 'none' returns the
empty envelope, 'high' returns 0.95 for every noul, and the default persona
answers 0.5 unless its response table pins a value. A persona is a mock of
the Laya mechanism (C); experiment runs that include 'C' must supply one,
and runs that exclude it never touch the model wrapper.
"""

from __future__ import annotations

from tests.conftest import MockLayaClient, _first_choice, _make_laya_answer

__all__ = ["build_persona"]


class _NoLaya(MockLayaClient):
    """Persona 'none': empty answers."""

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


def build_persona(name: str) -> MockLayaClient:
    if name == "none":
        return _NoLaya()
    if name == "high":
        return _HighConfidence()
    return MockLayaClient()