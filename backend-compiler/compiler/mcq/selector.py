"""Question model and the per-state question selector (Spec §4.1/§4.2)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from compiler.ontology.loader import Ontology
from compiler.spec.models import PartialSpec

__all__ = ["Question", "QuestionType", "next_questions"]

QuestionType = Literal[
    "confirm_feature",
    "choose_parameter",
    "resolve_contradiction",
    "resolve_negation",
    "clarify_unparsed",
    "confirm_weak",
]


class Question(BaseModel):
    type: QuestionType
    feature_id: str | None = None
    parameter_id: str | None = None
    unparsed_index: int | None = None
    options: list[str] = Field(default_factory=list)
    confidence: float = 0.5
    prompt: str = ""

    @property
    def target(self) -> str:
        if self.type == "clarify_unparsed":
            return f"unparsed.{self.unparsed_index}"
        if self.parameter_id is not None:
            return f"parameters.{self.feature_id}.{self.parameter_id}"
        return f"features.{self.feature_id}"


def next_questions(spec: PartialSpec, ontology: Ontology,
                   confidence: dict[str, float] | None = None) -> list[Question]:
    """Features/parameters needing confirmation (Developer Spec.md §4.1)."""
    confidence = confidence or {}
    questions = []
    for feature_id, feature in ontology.features.items():
        if not spec.is_decided(feature_id):
            if all(dep in spec.enabled_features for dep in feature.requires):
                questions.append(Question(
                    type="confirm_feature",
                    feature_id=feature_id,
                    options=["yes", "no"],
                    confidence=confidence.get(feature_id, 0.5),
                    prompt=f"Enable {feature_id}?",
                ))
        elif spec.is_enabled(feature_id):
            for param_name, param in feature.parameters.items():
                key = f"{feature_id}.{param_name}"
                if key not in spec.decided_parameters:
                    questions.append(Question(
                        type="choose_parameter",
                        feature_id=feature_id,
                        parameter_id=param_name,
                        options=list(param.options),
                        confidence=confidence.get(key, 0.5),
                        prompt=f"Choose {key}",
                    ))
    return questions