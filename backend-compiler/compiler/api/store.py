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
