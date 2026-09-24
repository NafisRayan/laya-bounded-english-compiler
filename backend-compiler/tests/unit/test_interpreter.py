import pytest
from compiler.interpreter.aliases import exact_match
from compiler.interpreter.rules import phrase_match
from compiler.interpreter.merge import check_coverage
from compiler.spec.models import Candidate


def test_exact_map_stripe():
    candidates = exact_match("I want to use Stripe for payments")
    assert any(c.capability_id == "payments.provider" and c.value == "stripe"
               for c in candidates)


def test_exact_map_case_insensitive():
    assert exact_match("STRIPE") == exact_match("stripe")


def test_exact_map_no_match():
    assert exact_match("something unrelated") == []


@pytest.mark.parametrize("text,expected", [
    ("users can message each other", "messaging.enabled"),
    ("owners can talk to renters", "messaging.enabled"),
    ("people should be able to contact users", "messaging.enabled"),
])
def test_phrase_messaging(text, expected):
    candidates = phrase_match(text)
    assert any(c.capability_id == expected for c in candidates)


def test_coverage_unparsed_sentence_flagged():
    text = "Users can message each other. Owners can reject bad actors."
    mapped = [Candidate("messaging.enabled", True, 0.9, "phrase", "s1")]
    unparsed = check_coverage(text, mapped)
    assert len(unparsed) == 1
    assert "reject bad actors" in unparsed[0]


def test_run_interpreter_uses_all_three_mechanisms(ontology):
    from compiler.interpreter.pipeline import run_interpreter
    from tests.conftest import MockLayaClient, _make_laya_answer

    class FixedLaya(MockLayaClient):
        def predict(self, state, questions):
            answers = {}
            for qid in questions:
                p = 0.9 if qid == "needs_messaging" else 0.05
                answers[qid] = _make_laya_answer("noul", p)
            return self._envelope(answers)

    candidates = run_interpreter(
        "users can message each other and pay with stripe",
        ontology, laya=FixedLaya(),
    )
    ids = {c.capability_id for c in candidates}
    assert "messaging.enabled" in ids
    assert "payments.provider" in ids
    assert "needs_messaging" in ids