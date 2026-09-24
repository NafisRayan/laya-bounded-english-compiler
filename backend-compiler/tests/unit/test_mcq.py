"""MCQ engine unit tests (Developer Spec.md §18.10 + pipeline tests)."""

from compiler.spec.models import PartialSpec


def test_partial_spec_set_form():
    spec = PartialSpec(
        decided_features={"authentication"},
        enabled_features={"authentication"},
    )
    assert spec.decided_features == {"authentication"}
    assert spec.enabled_features == {"authentication"}
    assert spec.decided_parameters == set()
    assert spec.parameter_values == {}


def test_partial_spec_dict_form_normalizes_to_set():
    spec = PartialSpec(decided_features={"authentication": False}, enabled_features=set())
    assert spec.decided_features == {"authentication"}
    assert spec.enabled_features == set()


def test_decide_helpers():
    spec = PartialSpec()
    spec.decide_feature("bookings", enabled=True)
    assert spec.is_decided("bookings") and spec.is_enabled("bookings")
    spec.decide_feature("payments", enabled=False)
    assert spec.is_decided("payments") and not spec.is_enabled("payments")
    spec.decide_parameter("bookings.mode", value="instant")
    assert "bookings.mode" in spec.decided_parameters
    assert spec.parameter_value("bookings.mode") == "instant"


def test_decide_parameter_without_value():
    spec = PartialSpec()
    spec.decide_parameter("bookings.mode")
    assert "bookings.mode" in spec.decided_parameters
    assert spec.parameter_value("bookings.mode") is None


def test_partial_spec_empty_dict_form():
    spec = PartialSpec(decided_features={}, enabled_features=set())
    assert spec.decided_features == set()
    assert spec.enabled_features == set()


def test_partial_spec_dict_form_with_true_value():
    spec = PartialSpec(decided_features={"authentication": True},
                       enabled_features={"authentication"})
    assert spec.is_decided("authentication")
    assert spec.is_enabled("authentication")


from compiler.mcq.selector import Question, next_questions
from compiler.spec.models import PartialSpec


def test_no_questions_when_feature_disabled(ontology):
    spec = PartialSpec(decided_features={"authentication": False}, enabled_features=set())
    qs = next_questions(spec, ontology)
    assert not any(q.feature_id == "bookings" for q in qs)


def test_parameter_question_only_after_feature_enabled(ontology):
    spec = PartialSpec(
        decided_features={"authentication", "bookings"},
        enabled_features={"authentication", "bookings"},
        decided_parameters=set(),
    )
    qs = next_questions(spec, ontology)
    assert any(q.parameter_id == "mode" and q.feature_id == "bookings" for q in qs)


def test_parameter_question_skipped_after_answered(ontology):
    spec = PartialSpec(
        decided_features={"authentication", "bookings"},
        enabled_features={"authentication", "bookings"},
        decided_parameters={"bookings.mode"},
    )
    qs = next_questions(spec, ontology)
    assert not any(q.parameter_id == "mode" and q.feature_id == "bookings" for q in qs)


def test_dependency_pruning_payments_without_auth(ontology):
    spec = PartialSpec(decided_features=set(), enabled_features=set())
    qs = next_questions(spec, ontology)
    assert not any(q.feature_id == "payments" for q in qs)


def test_question_target_values(ontology):
    q = Question(type="confirm_feature", feature_id="payments", options=["yes", "no"], confidence=0.5)
    assert q.target == "features.payments"
    q2 = Question(type="choose_parameter", feature_id="bookings", parameter_id="mode",
                  options=["instant", "owner_approval"], confidence=0.5)
    assert q2.target == "parameters.bookings.mode"
    q3 = Question(type="clarify_unparsed", unparsed_index=1, options=["messaging"], confidence=0.5)
    assert q3.target == "unparsed.1"


from compiler.mcq.graph import order_questions
from compiler.mcq.selector import Question


def _q(type_, feature_id, confidence=0.5):
    return Question(type=type_, feature_id=feature_id,
                    parameter_id=None, options=[], confidence=confidence)


def test_question_ordering_negation_second(ontology):
    qs = [
        _q("confirm_feature", "messaging"),
        _q("resolve_contradiction", "bookings"),
        _q("resolve_negation", "payments"),
        _q("clarify_unparsed", None),
    ]
    ordered = order_questions(qs)
    assert ordered[0].type == "resolve_contradiction"
    assert ordered[1].type == "resolve_negation"
    assert ordered[2].type == "clarify_unparsed"
    assert ordered[3].type == "confirm_feature"


def test_confirm_feature_confidence_split(ontology):
    qs = [
        _q("confirm_feature", "bookings", confidence=0.70),
        _q("confirm_feature", "messaging", confidence=0.30),
    ]
    ordered = order_questions(qs, ontology)
    assert [q.feature_id for q in ordered] == ["messaging", "bookings"]


def test_choose_parameter_ordered_by_feature_depth(ontology):
    qs = [
        Question(type="choose_parameter", feature_id="favorites", parameter_id="x",
                 options=[], confidence=0.5),
        Question(type="choose_parameter", feature_id="bookings", parameter_id="mode",
                 options=[], confidence=0.5),
    ]
    ordered = order_questions(qs, ontology)
    assert [q.feature_id for q in ordered] == ["bookings", "favorites"]


def test_confirm_weak_sorts_last(ontology):
    qs = [_q("confirm_feature", "bookings"), _q("confirm_weak", "authentication")]
    ordered = order_questions(qs, ontology)
    assert ordered[-1].type == "confirm_weak"


from compiler.mcq.pipeline import fold_candidates
from compiler.spec.models import Candidate


def test_fold_classifies_feature_and_param(ontology):
    cands = [
        Candidate("bookings.enabled", True, 1.0, "exact", "bookings"),
        Candidate("bookings.mode", "instant", 1.0, "exact", "instant"),
    ]
    result = fold_candidates(cands, ontology)
    assert result.spec.is_enabled("bookings")
    assert result.spec.parameter_value("bookings.mode") == "instant"


def test_fold_laya_needs_feature_uses_bool(ontology):
    cands = [Candidate("needs_payments", True, 0.95, "laya", None)]
    result = fold_candidates(cands, ontology)
    assert result.spec.is_enabled("payments")


def test_fold_ignores_entity_and_unknown(ontology):
    cands = [
        Candidate("needs_profiles", True, 0.95, "laya", None),
        Candidate("bogus.target", True, 0.95, "laya", None),
    ]
    result = fold_candidates(cands, ontology)
    assert result.spec.decided_features == set()
    assert "bogus.target" in result.unsupported


def test_fold_neutral_confidence_leaves_open(ontology):
    cands = [Candidate("needs_bookings", True, 0.5, "laya", None)]
    result = fold_candidates(cands, ontology)
    assert not result.spec.is_decided("bookings")
    assert result.feature_confidence.get("bookings") == 0.5


def test_fold_conflict_creates_negation(ontology):
    cands = [
        Candidate("payments.enabled", True, 0.9, "phrase", "pay"),
        Candidate("payments.enabled", False, 0.9, "phrase_negated", "no pay"),
    ]
    result = fold_candidates(cands, ontology)
    assert not result.spec.is_decided("payments")
    assert any(q.type == "resolve_negation" and q.feature_id == "payments"
               for q in result.negations)


def test_fold_role_implies_roles_feature(ontology):
    cands = [Candidate("roles.owner", True, 0.9, "phrase", "owner")]
    result = fold_candidates(cands, ontology)
    assert result.spec.is_enabled("roles")
    assert result.spec.parameter_value("roles.role_names") == ["owner"]


def test_fold_seeded_decided_feature_not_overridden_no_negation(ontology):
    spec = PartialSpec()
    spec.decide_feature("payments", enabled=False)
    cands = [
        Candidate("payments.enabled", True, 0.95, "phrase", "pay"),
        Candidate("payments.enabled", False, 0.95, "phrase_negated", "no pay"),
    ]
    result = fold_candidates(cands, ontology, spec=spec)
    assert result.spec is spec  # the seeded spec is carried through
    assert not result.spec.is_enabled("payments")
    assert result.negations == []


def test_fold_param_candidate_for_unenabled_feature_not_decided(ontology):
    cands = [Candidate("authentication.method", "oauth_google", 1.0, "phrase", "google")]
    result = fold_candidates(cands, ontology)
    assert "authentication.method" not in result.spec.decided_parameters
    assert not result.spec.is_enabled("authentication")


def test_fold_negated_role_not_collected(ontology):
    cands = [Candidate("roles.admin", False, 0.9, "phrase_negated", "no admins")]
    result = fold_candidates(cands, ontology)
    assert not result.spec.is_decided("roles")
    assert "roles.role_names" not in result.spec.decided_parameters


def test_fold_role_names_kept_when_roles_decided_this_pass(ontology):
    cands = [
        Candidate("roles.enabled", True, 0.9, "phrase", "roles on"),
        Candidate("roles.admin", True, 0.9, "phrase", "admins"),
    ]
    result = fold_candidates(cands, ontology)
    assert result.spec.is_enabled("roles")
    assert result.spec.parameter_value("roles.role_names") == ["admin"]
