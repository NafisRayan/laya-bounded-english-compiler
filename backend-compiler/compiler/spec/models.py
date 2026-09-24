"""BackendSpec intermediate representation models."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

__all__ = ["BackendSpec", "BucketSpec", "Candidate", "Decision", "PartialSpec"]

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

    ``__init__`` additionally accepts positional arguments because the
    spec's tests construct candidates positionally
    (e.g. ``Candidate("payments.enabled", True, 0.85, "phrase", "s1")``).
    """

    capability_id: str
    value: Any
    confidence: float
    source: DecisionSource
    evidence: str | None

    def __init__(self, capability_id=None, value=None, confidence=None,
                 source=None, evidence=None, **kwargs):
        super().__init__(
            capability_id=capability_id,
            value=value,
            confidence=confidence,
            source=source,
            evidence=evidence,
            **kwargs,
        )


class PartialSpec(BaseModel):
    """Spec under construction (Developer Spec.md §4.1 / §18.10).

    `decided_features` accepts either a set of feature ids or a dict
    {feature_id: bool} (the dict form is what §18.10 uses); it normalizes to
    a set of keys. Enabling truth lives in `enabled_features`. Parameter
    decisions are recorded in `decided_parameters`; their values (when known)
    in `parameter_values`.
    """

    decided_features: set[str] | dict[str, bool] = Field(default_factory=set)
    enabled_features: set[str] = Field(default_factory=set)
    decided_parameters: set[str] = Field(default_factory=set)
    parameter_values: dict[str, Any] = Field(default_factory=dict)

    @field_validator("decided_features", mode="before")
    @classmethod
    def _normalize_decided_features(cls, v):
        if isinstance(v, dict):
            return set(v)
        return v

    def decide_feature(self, feature_id: str, enabled: bool) -> None:
        self.decided_features.add(feature_id)
        if enabled:
            self.enabled_features.add(feature_id)
        else:
            self.enabled_features.discard(feature_id)

    def decide_parameter(self, parameter_id: str, value: Any = None) -> None:
        self.decided_parameters.add(parameter_id)
        if value is not None:
            self.parameter_values[parameter_id] = value

    def is_decided(self, feature_id: str) -> bool:
        return feature_id in self.decided_features

    def is_enabled(self, feature_id: str) -> bool:
        return feature_id in self.enabled_features

    def parameter_value(self, parameter_id: str) -> Any:
        return self.parameter_values.get(parameter_id)


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