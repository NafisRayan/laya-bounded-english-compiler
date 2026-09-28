"""Session API integration tests (Developer Spec.md §14; design:
docs/superpowers/specs/2026-09-28-session-api-design.md).

Empirically pinned flow (probe, 2026-09-28): text "We need bookings and
messaging" with the default MockLayaClient yields EXACTLY 2 questions at
interpret (clarify_unparsed unparsed.0, confirm_feature
features.authentication), and the combined answer set below completes the
session (0 remaining, validation ok) in a single /answer call.
"""

import pytest
from fastapi.testclient import TestClient

from compiler.api.app import create_app
from compiler.api.store import InMemorySessionStore
from tests.conftest import MockLayaClient

TEXT = "We need bookings and messaging"
COMPLETE_ANSWERS = {
    "unparsed.0": "authentication",
    "features.authentication": False,
    "features.bookings": False,
    "features.file_storage": False,
    "features.messaging": False,
    "features.payments": False,
    "features.realtime": False,
    "features.roles": False,
    "parameters.authentication.method": "email_password",
}


class FlakyClient:
    """Delegating wrapper that fails exactly one call, at a set index.

    The pipeline makes exactly one laya call per request
    (interpreter/pipeline.py:50), so with `fail_on_call_index=2` the failing
    call is the /answer that follows a successful /interpret. The failure
    latches: later calls pass through, so the same client can keep driving
    requests after the 500.
    """

    def __init__(self, inner, fail_on_call_index=2):
        self._inner = inner
        self._limit = fail_on_call_index
        self.calls = 0
        self.failed = False

    def __getattr__(self, name):
        attr = getattr(self._inner, name)
        if not callable(attr):
            return attr

        def wrapper(*args, **kwargs):
            self.calls += 1
            if not self.failed and self.calls == self._limit:
                self.failed = True
                raise RuntimeError("inference failed")
            return attr(*args, **kwargs)

        return wrapper


@pytest.fixture
def make_app(ontology):
    def _make(client=None, sessions=None):
        return create_app(
            client=client or (lambda: MockLayaClient()),
            sessions=sessions or InMemorySessionStore(),
            ontology=ontology,
        )
    return _make


def test_happy_path_round_trip(make_app):
    c = TestClient(make_app())
    r = c.post("/v1/sessions")
    assert r.status_code == 201
    sid = r.json()["id"]
    assert r.json()["status"] == "new"

    ri = c.post(f"/v1/sessions/{sid}/interpret", json={"text": TEXT})
    assert ri.status_code == 200
    body = ri.json()
    assert body["status"] == "collecting"
    assert body["remaining"] == 2
    assert [q["target"] for q in body["questions"]] == [
        "unparsed.0", "features.authentication"]
    assert {q["type"] for q in body["questions"]} == {
        "clarify_unparsed", "confirm_feature"}

    ra = c.post(f"/v1/sessions/{sid}/answer", json={"answers": COMPLETE_ANSWERS})
    assert ra.status_code == 200
    abody = ra.json()
    assert abody["finished"] is True
    assert abody["remaining"] == 0
    assert abody["status"] == "complete"
    assert abody["questions"] == []

    rs = c.get(f"/v1/sessions/{sid}/spec")
    assert rs.status_code == 200
    spec = rs.json()["spec"]
    assert spec["features"]["authentication"] is True
    assert spec["features"]["bookings"] is False
    assert spec["parameters"] == {"authentication.method": "email_password"}
    assert rs.json()["validation"]["ok"] is True
    assert rs.json()["open_questions"] == []

    ra2 = c.post(f"/v1/sessions/{sid}/approve")
    assert ra2.status_code == 200
    assert ra2.json()["status"] == "approved"


def test_interpret_relock_409(make_app):
    c = TestClient(make_app())
    s = c.post("/v1/sessions").json()["id"]
    assert c.post(f"/v1/sessions/{s}/interpret", json={"text": TEXT}).status_code == 200
    # still allowed while answers are empty
    assert c.post(f"/v1/sessions/{s}/interpret", json={"text": TEXT}).status_code == 200
    c.post(f"/v1/sessions/{s}/answer", json={"answers": {"features.authentication": True}})
    assert c.post(f"/v1/sessions/{s}/interpret", json={"text": TEXT}).status_code == 409


def test_answer_before_interpret_409(make_app):
    c = TestClient(make_app())
    s = c.post("/v1/sessions").json()["id"]
    assert c.post(f"/v1/sessions/{s}/answer", json={"answers": {}}).status_code == 409


def test_spec_before_interpret_409(make_app):
    c = TestClient(make_app())
    s = c.post("/v1/sessions").json()["id"]
    assert c.get(f"/v1/sessions/{s}/spec").status_code == 409


def test_approve_requires_complete(make_app):
    c = TestClient(make_app())
    s = c.post("/v1/sessions").json()["id"]
    assert c.post(f"/v1/sessions/{s}/approve").status_code == 409  # no text yet
    c.post(f"/v1/sessions/{s}/interpret", json={"text": TEXT})
    assert c.post(f"/v1/sessions/{s}/approve").status_code == 409  # open questions


def test_deploy_side_stubs_501(make_app):
    c = TestClient(make_app())
    s = c.post("/v1/sessions").json()["id"]
    endpoints = [
        ("post", f"/v1/sessions/{s}/deploy"),
        ("get", f"/v1/sessions/{s}/deploy/status"),
        ("post", f"/v1/sessions/{s}/remediate"),
        ("get", f"/v1/sessions/{s}/logs"),
    ]
    for method, route in endpoints:
        r = getattr(c, method)(route)
        assert r.status_code == 501, (method, route)
        assert r.json()["detail"].startswith("Not implemented")


def test_unknown_session_404(make_app):
    c = TestClient(make_app())
    nope = "0" * 32
    assert c.post(f"/v1/sessions/{nope}/interpret",
                  json={"text": "x"}).status_code == 404
    assert c.post(f"/v1/sessions/{nope}/answer",
                  json={"answers": {}}).status_code == 404
    assert c.get(f"/v1/sessions/{nope}/spec").status_code == 404
    assert c.post(f"/v1/sessions/{nope}/approve").status_code == 404


def test_empty_text_422(make_app):
    c = TestClient(make_app())
    s = c.post("/v1/sessions").json()["id"]
    assert c.post(f"/v1/sessions/{s}/interpret", json={"text": ""}).status_code == 422


def test_laya_unavailable_503(make_app):
    def broken():
        raise ImportError("laya not installed")
    c = TestClient(make_app(client=broken))
    s = c.post("/v1/sessions").json()["id"]
    assert c.post(f"/v1/sessions/{s}/interpret", json={"text": TEXT}).status_code == 503


def test_laya_client_constructed_once(make_app):
    calls = []

    def factory():
        calls.append(1)
        return MockLayaClient()

    c = TestClient(make_app(client=factory))
    for _ in range(3):
        s = c.post("/v1/sessions").json()["id"]
        assert c.post(f"/v1/sessions/{s}/interpret",
                      json={"text": TEXT}).status_code == 200
    assert len(calls) == 1


def test_stale_answer_ignored(make_app):
    c = TestClient(make_app())
    s = c.post("/v1/sessions").json()["id"]
    c.post(f"/v1/sessions/{s}/interpret", json={"text": TEXT})
    ra = c.post(f"/v1/sessions/{s}/answer",
                json={"answers": {"features.zzz_not_a_feature": True}})
    assert ra.status_code == 200
    body = ra.json()
    assert body["finished"] is False
    assert body["remaining"] == 2
    assert [q["target"] for q in body["questions"]] == [
        "unparsed.0", "features.authentication"]


def test_max_mcqs_clamp(make_app):
    c = TestClient(make_app())
    s = c.post("/v1/sessions").json()["id"]
    r1 = c.post(f"/v1/sessions/{s}/interpret", json={"text": TEXT, "max_mcqs": 1})
    assert r1.json()["remaining"] == 1  # clamped down; default client gives 2

    s2 = c.post("/v1/sessions").json()["id"]
    r0 = c.post(f"/v1/sessions/{s2}/interpret", json={"text": TEXT, "max_mcqs": 0})
    assert r0.json()["remaining"] == 1  # clamped up to 1
    # Note: the upper clamp (min(10, x)) is unreachable with the default mock —
    # question count per interpret call is 2; exercising it needs a
    # >10-question client.


def test_spec_before_completion_lists_open_questions(make_app):
    c = TestClient(make_app())
    s = c.post("/v1/sessions").json()["id"]
    c.post(f"/v1/sessions/{s}/interpret", json={"text": TEXT})
    rs = c.get(f"/v1/sessions/{s}/spec")
    assert rs.status_code == 200
    assert rs.json()["validation"]["ok"] is True
    assert len(rs.json()["open_questions"]) == 2


def test_create_app_default_wiring_loads_production_ontology():
    app = create_app()
    assert app.title == "Laya compiler session API"


def test_failed_pipeline_does_not_commit_state(make_app):
    flaky = FlakyClient(MockLayaClient(), fail_on_call_index=2)
    store = InMemorySessionStore()
    c = TestClient(make_app(client=lambda: flaky, sessions=store),
                   raise_server_exceptions=False)
    s = c.post("/v1/sessions").json()["id"]
    assert c.post(f"/v1/sessions/{s}/interpret",
                  json={"text": TEXT}).status_code == 200
    assert flaky.calls == 1  # one laya call per request: index 2 is the /answer

    # second pipeline run (the /answer) blows up mid-flight
    assert c.post(f"/v1/sessions/{s}/answer",
                  json={"answers": {"features.authentication": True}}).status_code == 500

    # the failed answer was never committed to the stored session
    stored = store.get(s)
    assert stored.answers == {}
    assert stored.text == TEXT

    # ...so the text lock never engaged: re-interpret is still allowed
    assert c.post(f"/v1/sessions/{s}/interpret",
                  json={"text": TEXT}).status_code == 200

    # ...and a clean follow-up answer completes the session as usual
    ra = c.post(f"/v1/sessions/{s}/answer", json={"answers": COMPLETE_ANSWERS})
    assert ra.status_code == 200
    assert ra.json()["finished"] is True
    assert ra.json()["remaining"] == 0
