"""run_mcq_loop — turn interpreter candidates into a resolved spec + open MCQ
questions (Developer Spec.md §3.4 / §4 / §18.13)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from compiler.mcq.selector import Question
from compiler.mcq.thresholds import AUTO_ACCEPT
from compiler.ontology.loader import Ontology
from compiler.spec.models import Candidate, PartialSpec

__all__ = ["FoldResult", "fold_candidates", "run_mcq_loop"]


@dataclass
class FoldResult:
    spec: PartialSpec = field(default_factory=PartialSpec)
    feature_confidence: dict[str, float] = field(default_factory=dict)
    negations: list[Question] = field(default_factory=list)
    unsupported: list[str] = field(default_factory=list)


def _classify(capability_id: str, ontology: Ontology):
    """Return ('feature', fid), ('parameter', 'fid.pid'), ('role', role)
    or ('entity', name) / ('unknown', raw)."""
    if capability_id.startswith("needs_"):
        name = capability_id[len("needs_"):]
        if name in ontology.features:
            return "feature", (name,)
        if name in ontology.entities:
            return "entity", (name,)
        return "unknown", (capability_id,)
    if capability_id.endswith(".enabled"):
        fid = capability_id[: -len(".enabled")]
        if fid in ontology.features:
            return "feature", (fid,)
        return "unknown", (capability_id,)
    if "." in capability_id:
        fid, _, pid = capability_id.partition(".")
        feature = ontology.features.get(fid)
        if feature is not None and pid in feature.parameters:
            return "parameter", (capability_id,)
        if fid == "roles" and capability_id.startswith("roles."):
            return "role", (capability_id[len("roles."):],)
        return "unknown", (capability_id,)
    return "unknown", (capability_id,)


def fold_candidates(candidates: list[Candidate], ontology: Ontology,
                    spec: PartialSpec | None = None) -> FoldResult:
    """Apply interpreter candidates to a PartialSpec by confidence threshold.

    Auto-decides feature/parameter targets with a single high-confidence
    (>= AUTO_ACCEPT) value; records negation conflicts, per-feature
    confidence for ordering bands, and unsupported capability ids.

    `spec` seeds the partial state (user answers already applied). Already
    decided targets are never overridden, and no negation question is
    surfaced for a feature the user has already decided.
    """
    result = FoldResult(spec=spec or PartialSpec())
    feature_values: dict[str, list[tuple[Any, float]]] = {}
    param_values: dict[str, list[tuple[Any, float]]] = {}
    roles: list[str] = []

    for cand in candidates:
        kind, payload = _classify(cand.capability_id, ontology)
        if kind == "feature":
            feature_values.setdefault(payload[0], []).append((cand.value, cand.confidence))
        elif kind == "parameter":
            param_values.setdefault(payload[0], []).append((cand.value, cand.confidence))
        elif kind == "role":
            roles.append(payload[0])
        elif kind == "unknown":
            result.unsupported.append(cand.capability_id)
        # "entity" candidates are ignored: entities are derived from
        # activated features by recompute_spec.

    for fid, proposals in feature_values.items():
        best = max(proposals, key=lambda p: p[1])
        result.feature_confidence[fid] = best[1]
        if result.spec.is_decided(fid):
            continue
        distinct = {repr(v) for v, _ in proposals}
        if len(distinct) > 1:
            result.negations.append(Question(
                type="resolve_negation", feature_id=fid,
                options=["yes", "no"], confidence=best[1],
                prompt=f"Conflicting signals for {fid}. Enable it?",
            ))
            continue
        value, conf = best
        if conf >= AUTO_ACCEPT:
            result.spec.decide_feature(fid, enabled=bool(value))

    for key, proposals in param_values.items():
        if key in result.spec.decided_parameters:
            continue
        best = max(proposals, key=lambda p: p[1])
        if best[1] >= AUTO_ACCEPT:
            fid = key.partition(".")[0]
            if result.spec.is_enabled(fid):
                result.spec.decide_parameter(key, value=best[0])

    if roles and not result.spec.is_decided("roles"):
        result.spec.decide_feature("roles", enabled=True)
        result.spec.decide_parameter("roles.role_names", value=sorted(set(roles)))

    return result