"""
Contract test between MockLayaClient and the interpreter's consumption
of answer fields.

Verifies:
  - Mock returns the same top-level shape as the real library envelope
    (model / answers / usage / routing).
  - Each answer carries type, noul/choice, confidence, answer_confidence,
    action.
  - The interpreter reads answer_confidence (not bare noul) when
    computing candidate confidence.
  - Router.predict_batch is invoked as list-of-dicts, not list-of-strings
    with a model= kwarg.
  - Router is constructed without a models= override.
"""
import pytest

from compiler.interpreter.laya_client import CHECKPOINT, LayaClient
from tests.conftest import MockLayaClient, _first_choice, _make_laya_answer


def test_mock_returns_full_envelope():
    mock = MockLayaClient()
    resp = mock.predict("some state", {
        "q1": {"type": "noul", "instructions": "..."},
        "q2": {"type": "choice", "instructions": "...", "criteria": ["a", "b"]},
    })
    assert "model" in resp
    assert "answers" in resp
    assert "usage" in resp
    assert "routing" in resp
    assert resp["answers"]["q1"]["type"] == "noul"
    assert "noul" in resp["answers"]["q1"]
    assert "confidence" in resp["answers"]["q1"]
    assert "answer_confidence" in resp["answers"]["q1"]
    assert "action" in resp["answers"]["q1"]
    assert resp["answers"]["q2"]["type"] == "choice"
    assert "choice" in resp["answers"]["q2"]


def test_top_level_model_is_constant():
    """v1.9 — real library returns the constant 'laya-rl-agent' at top level."""
    mock = MockLayaClient()
    resp = mock.predict("s", {"q": {"type": "noul", "instructions": "..."}})
    assert resp["model"] == "laya-rl-agent"


def test_routing_has_real_keys():
    """v1.9 — real routing has model/repo/reason, not checkpoint/auto_routed."""
    mock = MockLayaClient()
    resp = mock.predict("s", {"q": {"type": "noul", "instructions": "..."}})
    assert set(resp["routing"].keys()) >= {"model", "repo", "reason"}


def test_usage_has_real_keys():
    """v1.9 — real usage has input_tokens/output_tokens."""
    mock = MockLayaClient()
    resp = mock.predict("s", {"q": {"type": "noul", "instructions": "..."}})
    assert set(resp["usage"].keys()) >= {"input_tokens", "output_tokens"}


def test_action_has_act_probability():
    """v1.9 — real action carries act_probability."""
    mock = MockLayaClient()
    resp = mock.predict("s", {"q": {"type": "noul", "instructions": "..."}})
    assert "act_probability" in resp["answers"]["q"]["action"]


def test_act_probability_is_independent_of_noul():
    """v1.10 — the action head is a separate trained quantity (agent.py:676);
    a caller-pinned act_probability must be preserved verbatim, not recomputed
    from noul/confidence."""
    a = _make_laya_answer("noul", 0.9, act_probability=0.4)
    assert a["noul"] == 0.9
    assert a["confidence"] == 0.9
    assert a["action"]["act_probability"] == 0.4
    assert a["action"]["act_probability"] != a["noul"]


def test_mock_constructs_without_network():
    """v1.10 — MockLayaClient must never build the real Router (which preloads
    and downloads weights). router/calibration are explicit None placeholders."""
    mock = MockLayaClient()
    assert mock.router is None
    assert mock.calibration is None
    assert mock.predict("s", {"q": {"type": "noul", "instructions": "..."}})[
        "model"] == "laya-rl-agent"


def test_criteria_dict_supported():
    """v1.9 — criteria may be a dict {label: description}; _first_choice handles it."""
    assert _first_choice({"a": "A", "b": "B"}) == "a"
    assert _first_choice(["a", "b"]) == "a"


def test_default_checkpoint_is_english():
    assert CHECKPOINT == "english"


def test_client_never_uses_typed_decisions():
    import compiler.interpreter.laya_client as lc
    src = open(lc.__file__).read()
    assert "laya-typed-decisions" not in src


def test_client_does_not_override_models():
    """
    v1.9 — Router must be constructed without a models= override so
    the library's default checkpoint resolution applies. Passing
    models={"english": None} overwrites the default with None and
    breaks preload.
    """
    import compiler.interpreter.laya_client as lc
    src = open(lc.__file__).read()
    assert "models=" not in src, \
        "LayaClient must not pass models to Router(); library defaults apply"


def test_interpreter_consumes_answer_confidence():
    """
    The interpreter must use answer_confidence as the calibrated
    confidence. Given noul=0.9 and answer_confidence=0.6, the candidate
    confidence surfaced should be 0.6.
    """
    from compiler.interpreter.pipeline import candidates_from_laya_response

    mock_resp = {
        "model": "laya-rl-agent",
        "answers": {
            "needs_listings": {
                "type": "noul",
                "noul": 0.9,
                "confidence": 0.9,
                "answer_confidence": 0.6,
                "action": {"act_probability": 0.9},
            }
        },
        "usage": {"input_tokens": 0, "output_tokens": 0},
        "routing": {"model": "english", "repo": "convaiinnovations/laya", "reason": "pinned"},
    }
    candidates = candidates_from_laya_response(mock_resp)
    c = next(c for c in candidates if c.capability_id == "needs_listings")
    assert c.confidence == pytest.approx(0.6), \
        "interpreter must read answer_confidence, not noul"
# --- real LayaClient: router-forwarding and calibration logic (no weights) ---


def _client_with_router(router, calibration=None):
    client = LayaClient.__new__(LayaClient)
    client.router = router
    client.calibration = calibration or {"english": {"temperature": 1.0}}
    return client


def test_predict_forwards_to_router_with_pinned_checkpoint():
    calls = {}

    class _Router:
        def predict(self, state, questions, model):
            calls.update(state=state, questions=questions, model=model)
            return {"answers": {}}

    client = _client_with_router(_Router())
    out = client.predict("s", {"q1": {"type": "noul"}})

    assert out == {"answers": {}}
    assert calls == {"state": "s", "questions": {"q1": {"type": "noul"}}, "model": CHECKPOINT}


def test_predict_batch_builds_per_state_request_dicts():
    class _Router:
        def predict_batch(self, requests):
            return [r["state"] + "!" for r in requests]

    client = _client_with_router(_Router())
    assert client.predict_batch(["a", "b"], {}) == ["a!", "b!"]


def test_calibrated_confidence_passes_through_at_temperature_one():
    client = _client_with_router(None)
    assert client.calibrated_confidence({"answer_confidence": 0.7}) == 0.7


def test_calibrated_confidence_applies_fitted_temperature():
    from compiler.interpreter.calibration import apply_temperature

    client = _client_with_router(None, {"english": {"temperature": 2.0}})
    raw = 0.9
    assert client.calibrated_confidence({"answer_confidence": raw}) == pytest.approx(
        apply_temperature(raw, 2.0)
    )
