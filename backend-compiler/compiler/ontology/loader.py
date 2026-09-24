"""Ontology models and loader.

The ontology is the bounded vocabulary the compiler can generate: entities,
features, roles, RLS patterns and cross-cutting constraints. It is versioned
under ``compiler/ontology/versions/<n>/`` as one YAML file per section, or a
single merged YAML bundle (as used by test fixtures).

Loading merges every top-level section across files; a key that appears in
more than one file must carry the same value in each, otherwise the loader
raises (this catches accidental overrides between section files).

Underlying section schema is defined in ``Developer Spec.md`` §2 and §17.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "ConstraintDef",
    "ConstraintCond",
    "EntityDef",
    "FeatureDef",
    "Ontology",
    "OntologyLoadError",
    "ParameterDef",
    "load_ontology",
]


class OntologyLoadError(ValueError):
    pass


class ParameterDef(BaseModel):
    type: str
    options: list[str] = Field(default_factory=list)
    min: int | None = None
    max: int | None = None


class FeatureDef(BaseModel):
    requires: list[str] = Field(default_factory=list)
    activates_entities: list[str] = Field(default_factory=list)
    activates_edge_functions: list[str] = Field(default_factory=list)
    parameters: dict[str, ParameterDef] = Field(default_factory=dict)


class EntityDef(BaseModel):
    managed_by: str | None = None
    fields: dict[str, dict[str, Any]] = Field(default_factory=dict)
    auto_create_on: str | None = None
    indexes: list[dict[str, Any]] = Field(default_factory=list)


class ConstraintCond(BaseModel):
    feature: str
    parameter: str | None = None
    value: Any = None
    contains: str | None = None


ConstraintType = Literal["requires", "contradicts", "weakens"]


class ConstraintDef(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    type: ConstraintType
    if_: ConstraintCond = Field(alias="if")
    then: ConstraintCond | None = None
    message: str | None = None
    reason: str | None = None
    severity: Literal["hard", "soft"] = "hard"


class Ontology(BaseModel):
    version: int
    entities: dict[str, EntityDef] = Field(default_factory=dict)
    features: dict[str, FeatureDef] = Field(default_factory=dict)
    roles: dict[str, dict[str, Any]] = Field(default_factory=dict)
    rls_patterns: dict[str, dict[str, Any]] = Field(default_factory=dict)
    constraints: list[ConstraintDef] = Field(default_factory=list)

    @property
    def items(self) -> list[str]:
        """Classification targets for the interpreter's noul questions.

        Union of feature ids and entity names; a `needs_<item>` question is
        generated per item (Developer Spec.md §3.1 Mechanism C).
        """
        return sorted(set(self.features) | set(self.entities))


def _load_yaml_sections(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)
    if doc is None:
        return {}
    if not isinstance(doc, dict):
        raise OntologyLoadError(f"Expected a mapping of sections in {path}, got {type(doc).__name__}")
    return doc


def _merge_sections(sections: list[dict[str, Any]]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for sec in sections:
        for key, value in sec.items():
            if key in merged and merged[key] != value:
                raise OntologyLoadError(
                    f"Section key {key!r} appears with conflicting values across ontology files"
                )
            merged.setdefault(key, value)
    return merged


def load_ontology(path: str | Path) -> Ontology:
    """Load an ontology from a directory of section YAML files or one bundle file.

    - Directory: every ``*.yaml`` is loaded and its top-level sections merged
      (``compiler/ontology/versions/v1/`` layout).
    - File: a single YAML document containing all top-level sections.
    """
    p = Path(path)
    if p.is_dir():
        files = sorted(p.glob("*.yaml"))
        if not files:
            raise OntologyLoadError(f"no *.yaml files under {p}")
        sections = [_load_yaml_sections(f) for f in files]
        data = _merge_sections(sections)
    elif p.is_file():
        data = _load_yaml_sections(p)
    else:
        raise OntologyLoadError(f"path does not exist: {p}")

    try:
        return Ontology(**data)
    except Exception as exc:  # pydantic ValidationError and friends
        raise OntologyLoadError(f"failed to build Ontology from {p}: {exc}") from exc