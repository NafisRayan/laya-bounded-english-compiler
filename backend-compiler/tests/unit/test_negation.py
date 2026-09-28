import pytest

from compiler.interpreter.negation import is_negated, phrase_match_with_negation


@pytest.mark.parametrize("text,start,end,expected", [
    ("please don't charge users with Stripe", 20, 27, True),
    ("no payments needed", 0, 2, True),
    ("we do not want reviews", 11, 18, True),
    ("avoid checkout", 6, 14, True),
    ("users can message each other", 10, 17, False),
    ("payments via Stripe", 0, 8, False),
    ("No matter what, users can message each other", 28, 35, False),
    ("Not only do users message, but they share files", 24, 31, False),
    ("There is no doubt users can message each other", 31, 38, False),
    ("Needless to say, users can message each other", 28, 35, False),
    ("Users should really, truly, absolutely not message each other", 50, 57, True),
])
def test_is_negated(text, start, end, expected):
    assert is_negated(text, start, end) == expected


def test_negation_does_not_bleed_across_sentence_boundary():
    text = "Users can message each other. No payments."
    import re
    m = re.search(r"message", text)
    assert not is_negated(text, m.start(), m.end())


def test_negation_across_sentence_with_same_sentence_negator():
    text = "Users cannot message each other. Payments work."
    import re
    m = re.search(r"message", text)
    assert is_negated(text, m.start(), m.end())


def test_multi_word_negators_are_not_dead_code():
    for text in ["no need for payments", "we do not need payments",
                 "we don't need payments", "no need payments"]:
        candidates = phrase_match_with_negation(text)
        assert any(c.capability_id == "payments.enabled" and c.value is False
                   for c in candidates), f"failed on: {text}"


def test_no_matter_exception_does_not_flip():
    text = "No matter what, users can message each other"
    candidates = phrase_match_with_negation(text)
    msg = [c for c in candidates if c.capability_id == "messaging.enabled"]
    assert all(c.value is True for c in msg)


def test_negation_source_tagged():
    text = "we don't need payments"
    candidates = phrase_match_with_negation(text)
    negated = [c for c in candidates if c.capability_id == "payments.enabled"]
    assert any(c.source == "phrase_negated" for c in negated)