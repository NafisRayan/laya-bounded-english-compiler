"""Session API routes (Developer Spec.md §14; phase 5).

Thin, stateless wrapper over run_interpreter -> run_mcq_loop -> validate.
Sessions store {text, answers, max_mcqs}; every call re-runs the pipeline
from that state. The four deploy-side endpoints are 501 stubs — the deployer
(Phase 3) does not exist yet.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, HTTPException

from compiler.api.schemas import AnswerRequest, InterpretRequest, SessionOut
from compiler.api.store import InMemorySessionStore, Session, SessionStore
from compiler.interpreter.pipeline import run_interpreter
from compiler.mcq.pipeline import run_mcq_loop
from compiler.mcq.selector import Question
from compiler.ontology.loader import load_ontology
from compiler.spec.validator import validate

__all__ = ["create_app"]

V1 = "/v1/sessions"
STUB_DETAIL = "Not implemented (deployer, Phase 3)"
ERR_RESPONSES = {
    404: {"description": "Session not found"},
    409: {"description": "State violation"},
    503: {"description": "Laya client construction failed"},
}


def _question_dict(q: Question) -> dict[str, Any]:
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
        Path(__file__).resolve().parents[1] / "ontology" / "versions" / "v1")
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

    @app.post(V1, response_model=SessionOut, status_code=201)
    def create_session() -> SessionOut:
        session = sessions.create()
        return SessionOut(id=session.id, created_at=session.created_at,
                          status=session.status)

    @app.post(f"{V1}/{{session_id}}/interpret", responses=ERR_RESPONSES)
    def interpret(session_id: str, body: InterpretRequest):
        session = sessions.get(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="session not found")
        if session.text is not None and session.answers:
            raise HTTPException(status_code=409,
                                detail="text is locked once answers exist")
        pending = replace(session, text=body.text,
                          max_mcqs=max(1, min(10, body.max_mcqs)),
                          status="collecting")
        _, mcqs = _run(pending)
        sessions.save(pending)
        # interpret reports "collecting" even with 0 open questions; the
        # complete transition is owned by /answer (single answer source).
        return {"status": pending.status,
                "questions": [_question_dict(q) for q in mcqs],
                "remaining": len(mcqs)}

    @app.post(f"{V1}/{{session_id}}/answer", responses=ERR_RESPONSES)
    def answer(session_id: str, body: AnswerRequest):
        session = sessions.get(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="session not found")
        if session.text is None:
            raise HTTPException(status_code=409,
                                detail="interpret required before answering")
        if session.status == "approved":
            raise HTTPException(status_code=409,
                                detail="session is approved and immutable")
        # Merge on a local copy; the store hands out the live object, so
        # mutating in place would survive a mid-pipeline 500.
        pending = replace(session, answers={**session.answers, **body.answers})
        _, mcqs = _run(pending)
        pending.status = "complete" if not mcqs else "collecting"
        sessions.save(pending)
        return {"status": pending.status,
                "questions": [_question_dict(q) for q in mcqs],
                "remaining": len(mcqs),
                "finished": not mcqs}

    @app.get(f"{V1}/{{session_id}}/spec", responses=ERR_RESPONSES)
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

    @app.post(f"{V1}/{{session_id}}/approve", responses=ERR_RESPONSES)
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
        approved = replace(session, status="approved")
        sessions.save(approved)
        return {"status": approved.status}

    @app.post(f"{V1}/{{session_id}}/deploy", status_code=501,
              responses={501: {"description": STUB_DETAIL}})
    def deploy(session_id: str):
        return {"detail": STUB_DETAIL}

    @app.get(f"{V1}/{{session_id}}/deploy/status", status_code=501,
             responses={501: {"description": STUB_DETAIL}})
    def deploy_status(session_id: str):
        return {"detail": STUB_DETAIL}

    @app.post(f"{V1}/{{session_id}}/remediate", status_code=501,
              responses={501: {"description": STUB_DETAIL}})
    def remediate(session_id: str):
        return {"detail": STUB_DETAIL}

    @app.get(f"{V1}/{{session_id}}/logs", status_code=501,
             responses={501: {"description": STUB_DETAIL}})
    def logs(session_id: str):
        return {"detail": STUB_DETAIL}

    return app
