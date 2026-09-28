# Session API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose the interpreted-session loop (`text → MCQs → BackendSpec`) as the §14 FastAPI behind a session store; the four deploy-side endpoints are 501 stubs.

**Architecture:** Thin, stateless wrapper over the complete pipeline — a session stores only `{text, answers, max_mcqs}` and every `interpret`/`answer`/`spec`/`approve` call re-runs `run_interpreter` → `run_mcq_loop` → `validate`. FastAPI app built by a `create_app(client, sessions, ontology)` factory (dependency injection — tests inject `MockLayaClient` + a fresh store; the default path lazily builds a real `LayaClient` and 503s on construction failure).

**Tech Stack:** FastAPI + uvicorn (new runtime deps), httpx (Starlette TestClient, dev dep), existing pydantic v2 (request models).

---

## Environment commands (use verbatim)

- Pytest (venv), from `backend-compiler`:
  `& "C:\Users\BS00861\Documents\GitHub\Laya Supabase\system\backend-compiler\.venv\Scripts\python.exe" -m pytest <args>`
- pip install (venv):
  `& "C:\Users\BS00861\Documents\GitHub\Laya Supabase\system\backend-compiler\.venv\Scripts\python.exe" -m pip install fastapi uvicorn httpx`
- Git root: `C:\Users\BS00861\Documents\GitHub\Laya Supabase\system` (branch `master`).
- LF→CRLF git warnings are expected and harmless.

---

### Task 1: Session store + unit tests

**Files:**
- Create: `backend-compiler/compiler/api/__init__.py`
- Create: `backend-compiler/compiler/api/store.py`
- Test: `backend-compiler/tests/unit/test_session_store.py`

- [ ] **Step 1: Write the failing test**

Create `backend-compiler/tests/unit/test_session_store.py` with EXACTLY:

```python
"""Session store unit tests (design: 2026-09-28-session-api-design.md)."""

from datetime import datetime, timedelta, timezone

from compiler.api.store import InMemorySessionStore, Session


def test_create_session_assigns_id_and_status():
    store = InMemorySessionStore()
    s = store.create()
    assert len(s.id) == 32
    assert s.status == "new"
    assert s.text is None
    assert s.answers == {}
    assert s.created_at.tzinfo is not None


def test_save_then_get_round_trips():
    store = InMemorySessionStore()
    s = store.create()
    s.text = "hello"
    s.answers = {"features.authentication": True}
    store.save(s)
    got = store.get(s.id)
    assert got is not None
    assert got.text == "hello"
    assert got.answers == {"features.authentication": True}


def test_get_unknown_returns_none():
    store = InMemorySessionStore()
    assert store.get("deadbeef" * 4) is None


def test_expired_session_is_evicted_on_get():
    store = InMemorySessionStore(ttl=timedelta(days=7))
    old = Session(id="a" * 32, created_at=datetime.now(timezone.utc) - timedelta(days=8))
    store.save(old)
    assert store.get(old.id) is None


def test_fresh_session_survives_get():
    store = InMemorySessionStore(ttl=timedelta(days=7))
    s = store.create()
    assert store.get(s.id) is not None
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `tests/unit/test_session_store.py -q` (see Environment commands)
Expected: `ModuleNotFoundError: No module named 'compiler.api'`

- [ ] **Step 3: Implement `compiler/api/__init__.py` and `compiler/api/store.py`**

Create `backend-compiler/compiler/api/__init__.py`:

```python
"""Session API package (Developer Spec.md §14; Phase 5)."""
```

Create `backend-compiler/compiler/api/store.py`:

```python
"""Session storage (Developer Spec.md §14; design: 2026-09-28-session-api-design).

Sessions hold only the interpretable state {text, answers, max_mcqs};
interpret/answer/spec/approve re-run the pipeline from this state each call
(stateless re-run). TTL expiry is lazy: an expired session evicts on access
and surfaces as 404 at the route layer.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

__all__ = ["Session", "SessionStore", "InMemorySessionStore"]


@dataclass
class Session:
    id: str
    created_at: datetime
    status: str = "new"
    text: str | None = None
    answers: dict[str, Any] = field(default_factory=dict)
    max_mcqs: int = 10


class SessionStore(Protocol):
    def create(self) -> Session: ...

    def get(self, session_id: str) -> Session | None: ...

    def save(self, session: Session) -> None: ...


class InMemorySessionStore:
    """Thread-safe dict store, 7-day TTL, lazy eviction.

    Deviation from Developer Spec.md §12 ('State store: Postgres'): no
    Postgres exists in the project yet; a Postgres-backed store implementing
    this same interface slots in at deployer time with no API changes.
    """

    def __init__(self, ttl: timedelta = timedelta(days=7)):
        self._ttl = ttl
        self._sessions: dict[str, Session] = {}
        self._lock = threading.RLock()

    def create(self) -> Session:
        with self._lock:
            session = Session(
                id=uuid.uuid4().hex,
                created_at=datetime.now(timezone.utc),
            )
            self._sessions[session.id] = session
            return session

    def get(self, session_id: str) -> Session | None:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None
            if datetime.now(timezone.utc) - session.created_at > self._ttl:
                del self._sessions[session_id]
                return None
            return session

    def save(self, session: Session) -> None:
        with self._lock:
            self._sessions[session.id] = session
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `tests/unit/test_session_store.py -q`
Expected: `5 passed in 0.0Xs`

- [ ] **Step 5: Commit**

```bash
git add backend-compiler/compiler/api backend-compiler/tests/unit/test_session_store.py
git commit -m "Add session store with TTL and unit tests"
```

---

### Task 2: FastAPI app + routes + integration tests

**Files:**
- Create: `backend-compiler/compiler/api/schemas.py`
- Create: `backend-compiler/compiler/api/app.py`
- Test: `backend-compiler/tests/integration/test_session_api.py`
- Modify: `backend-compiler/compiler/api/__init__.py` (add the `create_app` re-export)
- Modify: `backend-compiler/pyproject.toml` (dependencies + dev extras)

- [ ] **Step 1: Install new dependencies into the venv**

Run:
```bash
& "C:\Users\BS00861\Documents\GitHub\Laya Supabase\system\backend-compiler\.venv\Scripts\python.exe" -m pip install fastapi uvicorn httpx
```
Expected: three packages installed (matching existing installed versions).

- [ ] **Step 2: Record the dependencies in `pyproject.toml`**

In `backend-compiler/pyproject.toml`, change the `[project] dependencies` list from:

```toml
dependencies = [
    "pydantic>=2",
    "pyyaml>=6",
]
```

to:

```toml
dependencies = [
    "pydantic>=2",
    "pyyaml>=6",
    "fastapi>=0.110",
    "uvicorn>=0.29",
]
```

and the `dev` extra from:

```toml
dev = [
    "pytest>=8",
]
```

to:

```toml
dev = [
    "pytest>=8",
    "httpx>=0.27",
]
```

- [ ] **Step 3: Write the failing integration tests**

Create `backend-compiler/tests/integration/test_session_api.py` with EXACTLY:

```python
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
    assert r1.json()["remaining"] == 1

    s2 = c.post("/v1/sessions").json()["id"]
    r50 = c.post(f"/v1/sessions/{s2}/interpret", json={"text": TEXT, "max_mcqs": 50})
    assert r50.json()["remaining"] == 2  # clamped to 10; 2 < 10 unchanged

    s3 = c.post("/v1/sessions").json()["id"]
    r0 = c.post(f"/v1/sessions/{s3}/interpret", json={"text": TEXT, "max_mcqs": 0})
    assert r0.json()["remaining"] == 1  # clamped up to 1


def test_spec_before_completion_lists_open_questions(make_app):
    c = TestClient(make_app())
    s = c.post("/v1/sessions").json()["id"]
    c.post(f"/v1/sessions/{s}/interpret", json={"text": TEXT})
    rs = c.get(f"/v1/sessions/{s}/spec")
    assert rs.status_code == 200
    assert rs.json()["validation"]["ok"] is True
    assert len(rs.json()["open_questions"]) == 2
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `tests/integration/test_session_api.py -q`
Expected: `ModuleNotFoundError: No module named 'compiler.api.app'` (dependency collection loads `compiler.api.app` before any test runs).

- [ ] **Step 5: Implement `schemas.py`, `app.py`, and update `__init__.py`**

Create `backend-compiler/compiler/api/schemas.py`:

```python
"""Request/response bodies for the session API (Developer Spec.md §14).

Rich response bodies (questions, spec, validation) are plain dicts built in
app.py — FastAPI JSON-encodes them (nested BackendSpec datetimes handled by
pydantic's model_dump + the encoder). Request bodies and the session
response are validated pydantic models.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

__all__ = ["InterpretRequest", "AnswerRequest", "SessionOut"]


class InterpretRequest(BaseModel):
    text: str = Field(min_length=1)
    max_mcqs: int = 10


class AnswerRequest(BaseModel):
    answers: dict[str, Any] = Field(default_factory=dict)


class SessionOut(BaseModel):
    id: str
    created_at: datetime
    status: str
```

Create `backend-compiler/compiler/api/app.py`:

```python
"""Session API routes (Developer Spec.md §14; phase 5).

Thin, stateless wrapper over run_interpreter -> run_mcq_loop -> validate.
Sessions store {text, answers, max_mcqs}; every call re-runs the pipeline
from that state. The four deploy-side endpoints are 501 stubs — the deployer
(Phase 3) does not exist yet.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from compiler.api.schemas import AnswerRequest, InterpretRequest, SessionOut
from compiler.api.store import InMemorySessionStore, Session, SessionStore
from compiler.interpreter.pipeline import run_interpreter
from compiler.mcq.pipeline import run_mcq_loop
from compiler.ontology.loader import load_ontology
from compiler.spec.validator import validate

__all__ = ["create_app"]

V1 = "/v1/sessions"
STUB_DETAIL = "Not implemented (deployer, Phase 3)"


def _question_dict(q) -> dict[str, Any]:
    """Question.serialize + the computed `target` (a @property, selector.py:36)."""

    return {**q.model_dump(), "target": q.target}


def create_app(
    client: Callable[[], Any] | None = None,
    sessions: SessionStore | None = None,
    ontology=None,
) -> FastAPI:
    """Build the FastAPI app.

    `client` is a nullary callable returning a LayaClient-compatible object,
    invoked lazily on the first pipeline call; a construction failure (e.g.
    the `laya` package is not installed) surfaces as 503. Tests inject e.g.
    `lambda: MockLayaClient()`. `sessions` is the session store (default
    InMemorySessionStore); `ontology` the loaded Ontology (default the
    production v1 bundle).
    """
    sessions = sessions or InMemorySessionStore()
    ontology = ontology or load_ontology(
        Path(__file__).resolve().parents[2] / "ontology" / "versions" / "v1")
    if client is None:
        from compiler.interpreter.laya_client import LayaClient

        client = LayaClient
    resolved: dict[str, Any] = {}

    app = FastAPI(title="Laya compiler session API")

    def _laya() -> Any:
        try:
            if "client" not in resolved:
                resolved["client"] = client()
            return resolved["client"]
        except Exception as exc:
            raise HTTPException(
                status_code=503, detail="laya unavailable",
            ) from exc

    def _run(session: Session):
        laya = _laya()
        candidates = run_interpreter(session.text, ontology, laya=laya)
        return run_mcq_loop(candidates, ontology,
                            user_answers=session.answers,
                            text=session.text, laya=laya,
                            max_mcqs=session.max_mcqs)

    @app.post(V1)
    def create_session():
        session = sessions.create()
        return SessionOut(id=session.id, created_at=session.created_at,
                          status=session.status)

    @app.post(f"{V1}/{{session_id}}/interpret")
    def interpret(session_id: str, body: InterpretRequest):
        session = sessions.get(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="session not found")
        if session.text is not None and session.answers:
            raise HTTPException(status_code=409,
                                detail="text is locked once answers exist")
        session.text = body.text
        session.max_mcqs = max(1, min(10, body.max_mcqs))
        session.status = "collecting"
        _, mcqs = _run(session)
        sessions.save(session)
        return {"status": session.status,
                "questions": [_question_dict(q) for q in mcqs],
                "remaining": len(mcqs)}

    @app.post(f"{V1}/{{session_id}}/answer")
    def answer(session_id: str, body: AnswerRequest):
        session = sessions.get(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="session not found")
        if session.text is None:
            raise HTTPException(status_code=409,
                                detail="interpret required before answering")
        session.answers.update(body.answers)
        _, mcqs = _run(session)
        session.status = "complete" if not mcqs else "collecting"
        sessions.save(session)
        return {"status": session.status,
                "questions": [_question_dict(q) for q in mcqs],
                "remaining": len(mcqs),
                "finished": not mcqs}

    @app.get(f"{V1}/{{session_id}}/spec")
    def get_spec(session_id: str):
        session = sessions.get(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="session not found")
        if session.text is None:
            raise HTTPException(status_code=409,
                                detail="interpret required before fetching spec")
        spec, mcqs = _run(session)
        result = validate(spec, ontology)
        return {
            "spec": spec.model_dump(),
            "validation": {
                "ok": result.ok,
                "errors": [str(e) for e in result.errors],
                "warnings": [str(e) for e in result.warnings],
            },
            "open_questions": [_question_dict(q) for q in mcqs],
        }

    @app.post(f"{V1}/{{session_id}}/approve")
    def approve(session_id: str):
        session = sessions.get(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="session not found")
        if session.text is None:
            raise HTTPException(status_code=409,
                                detail="interpret required before approving")
        _, mcqs = _run(session)
        if mcqs:
            raise HTTPException(
                status_code=409,
                detail=f"{len(mcqs)} open question(s) remain",
            )
        session.status = "approved"
        sessions.save(session)
        return {"status": session.status}

    @app.post(f"{V1}/{{session_id}}/deploy")
    def deploy(session_id: str):
        return JSONResponse(status_code=501, content={"detail": STUB_DETAIL})

    @app.get(f"{V1}/{{session_id}}/deploy/status")
    def deploy_status(session_id: str):
        return JSONResponse(status_code=501, content={"detail": STUB_DETAIL})

    @app.post(f"{V1}/{{session_id}}/remediate")
    def remediate(session_id: str):
        return JSONResponse(status_code=501, content={"detail": STUB_DETAIL})

    @app.get(f"{V1}/{{session_id}}/logs")
    def logs(session_id: str):
        return JSONResponse(status_code=501, content={"detail": STUB_DETAIL})

    return app
```

Replace `backend-compiler/compiler/api/__init__.py` with:

```python
"""Session API package (Developer Spec.md §14; Phase 5)."""

from compiler.api.app import create_app

__all__ = ["create_app"]
```

- [ ] **Step 6: Run the new tests to verify they pass**

Run: `tests/integration/test_session_api.py -q`
Expected: `12 passed in 0.Xs`
Also run `tests/unit/test_session_store.py -q` → `5 passed` (store untouched).

- [ ] **Step 7: Run the full suite**

Run: `-m pytest -q` (full repo run)
Expected: `157 passed in 0.Xs` (140 baseline + 5 unit + 12 integration)

- [ ] **Step 8: Commit**

```bash
git add backend-compiler/compiler/api backend-compiler/tests/integration/test_session_api.py backend-compiler/pyproject.toml
git commit -m "Add session API routes with integration tests"
```

---

## Verification summary

- Baseline: 140 passed. After Task 1: 145. After Task 2: 157.
- The happy-path flow is empirically pinned: `"We need bookings and messaging"` with MockLayaClient → 2 questions at interpret → the `COMPLETE_ANSWERS` dict → 0 remaining, `validation.ok True`, approve → `approved`.
- Zero changes allowed outside `backend-compiler/compiler/api/`, the two new test files, `pyproject.toml`, and `backend-compiler/compiler/api/__init__.py`. Existing compiler modules, conftest, fixtures, and `calibration.json` must not change.