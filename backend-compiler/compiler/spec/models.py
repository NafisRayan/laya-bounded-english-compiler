"""BackendSpec intermediate representation models."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

__all__ = ["BackendSpec", "BucketSpec", "Candidate", "Decision"]

DecisionSource = Literal["exact", "phrase", "phrase_negated", "laya", "user", "default"]


class BucketSpec(BaseModel):
    name: str
    public: bool
    rls_pattern: str
    file_size_limit_mb: int = 10


class Decision(BaseModel):
    capability_id: str
    value: Any
    confidence: float
    source: DecisionSource
    evidence: str | None


class Candidate(BaseModel):
    """A single capability proposal produced by one extraction mechanism.

    Lives in ``spec.models`` so both the interpreter mechanisms and the
    merge step can reference it without a spec <-> interpreter import cycle.
    """

    capability_id: str
    value: Any
    confidence: float
    source: DecisionSource
    evidence: str | None


class BackendSpec(BaseModel):
    version: Literal["1.0"]
    ontology_version: int
    created_at: datetime

    features: dict[str, bool]
    parameters: dict[str, Any]
    roles: list[str]
    rls_overrides: dict[str, str]

    entities: list[str] = []
    buckets: list[BucketSpec] = []
    edge_functions: list[str] = []

    decisions: list[Decision]
    defaulted: list[str]
    unsupported: list[str]

    project_ref: str | None = None
    deployed_at: datetime | None = None