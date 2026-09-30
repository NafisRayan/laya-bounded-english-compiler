from compiler.interpreter.merge import merge
from compiler.spec.models import Candidate


def test_merge_positive_and_negative_phrase_flags_ambiguity():
    b = [
        Candidate("payments.enabled", True,  0.85, "phrase",         "s1"),
        Candidate("payments.enabled", False, 0.85, "phrase_negated", "s2"),
    ]
    merged = merge([], b, [])
    assert len(merged) == 2
    assert {c.value for c in merged} == {True, False}


def test_merge_only_positive_phrase():
    b = [Candidate("payments.enabled", True, 0.85, "phrase", "s1")]
    merged = merge([], b, [])
    assert len(merged) == 1
    assert merged[0].value is True


def test_merge_only_negative_phrase():
    b = [Candidate("payments.enabled", False, 0.85, "phrase_negated", "s1")]
    merged = merge([], b, [])
    assert len(merged) == 1
    assert merged[0].value is False


def test_merge_exact_beats_phrase_and_negated_phrase():
    a = [Candidate("payments.enabled", True, 1.0, "exact", None)]
    b = [
        Candidate("payments.enabled", False, 0.9, "phrase_negated", "s1"),
        Candidate("payments.enabled", True,  0.9, "phrase",         "s2"),
    ]
    c = [Candidate("payments.enabled", True, 0.7, "laya", None)]
    merged = merge(a, b, c)
    assert len(merged) == 1
    assert merged[0].source == "exact"


def test_merge_laya_only_when_no_phrase():
    c = [Candidate("reviews.enabled", True, 0.7, "laya", None)]
    merged = merge([], [], c)
    assert len(merged) == 1
    assert merged[0].source == "laya"


def test_merge_disjoint_capabilities():
    a = [Candidate("payments.provider", "stripe", 1.0, "exact", None)]
    b = [Candidate("messaging.enabled", True, 0.9, "phrase", "s1")]
    c = [Candidate("reviews.enabled", True, 0.7, "laya", None)]
    merged = merge(a, b, c)
    assert len(merged) == 3


def test_merge_two_exact_same_value_picks_highest_confidence():
    a = [
        Candidate("payments.provider", "stripe", 1.0, "exact", "s1"),
        Candidate("payments.provider", "stripe", 0.9, "exact", "s2"),
    ]
    merged = merge(a, [], [])
    assert len(merged) == 1
    assert merged[0].confidence == 1.0


def test_merge_two_exact_different_values_flags_ambiguity():
    a = [
        Candidate("authentication.method", "oauth_google", 1.0, "exact", "s1"),
        Candidate("authentication.method", "magic_link",   1.0, "exact", "s2"),
    ]
    merged = merge(a, [], [])
    assert len(merged) == 2

def test_merge_groups_laya_needs_with_rule_feature_target():
    """needs_X (laya) and X.enabled / X param keys (rules) are the same
    feature target: the laya twin must not reach the fold alongside the
    rule candidate, or fold's distinct-value check fires a spurious
    negation (measured in the real-checkpoint ablation, paper 5.2)."""
    from compiler.interpreter.merge import merge
    from compiler.spec.models import Candidate
    merged = merge(
        [],
        [Candidate("payments.enabled", True, 0.8, "phrase", "pay")],
        [Candidate("needs_payments", False, 0.99, "laya", None)],
    )
    payments = [c for c in merged if "payments" in c.capability_id]
    assert all(c.source != "laya" for c in payments)
    assert any(c.value is True and c.source == "phrase" for c in payments)
