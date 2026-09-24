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
