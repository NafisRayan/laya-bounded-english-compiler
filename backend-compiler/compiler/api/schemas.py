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
