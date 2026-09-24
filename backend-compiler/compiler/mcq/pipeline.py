"""run_mcq_loop — turn interpreter candidates into a resolved spec + open MCQ
questions (Developer Spec.md §3.4 / §4 / §18.13)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from compiler.interpreter.merge import check_coverage
from compiler.interpreter.negation import SENTENCE_BOUNDARY
from compiler.mcq.graph import order_questions
from compiler.mcq.selector import Question, next_questions
from compiler.mcq.thresholds import AUTO_ACCEPT
from compiler.ontology.loader import Ontology
from compiler.spec.derive import recompute_spec
from compiler.spec.models import BackendSpec, Candidate, Decision, PartialSpec
from compiler.spec.validator import constraint_holds

__all__ = ["FoldResult", "fold_candidates", "run_mcq_loop",
           "coverage_questions", "contradiction_questions"]


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
    seeded_roles = spec is not None and spec.is_decided("roles")
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
            if cand.value:
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
        distinct = {value for value, _ in proposals}
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

    if roles and not seeded_roles:
        if not result.spec.is_decided("roles"):
            result.spec.decide_feature("roles", enabled=True)
        if result.spec.is_enabled("roles"):
            result.spec.decide_parameter("roles.role_names", value=sorted(set(roles)))

    return result


def coverage_questions(text: str, candidates: list[Candidate], ontology: Ontology,
                       resolved: dict[int, str]) -> list[Question]:
    """clarify_unparsed questions for sentences still unmapped (Spec §3.6).
    (`resolved` is membership-checked only; its values are unused in v1.)
    """
    unparsed = check_coverage(text, candidates)
    questions = []
    options = sorted(ontology.features)
    # Re-derive original sentence indexes from the SAME split check_coverage
    # uses (identical boundaries/strip), walking the unparsed list in order.
    # Covered sentences never match an unparsed entry, so their indexes pass
    # through untouched — unparsed.1 == the second sentence even when the
    # first was covered. (An earlier while-resolved counter misaligned gaps
    # from covered sentences; this version cannot.)
    unparsed_iter = iter(unparsed)
    next_unparsed = next(unparsed_iter, None)
    for idx, chunk in enumerate(SENTENCE_BOUNDARY.split(text)):
        sentence = chunk.strip()
        if not sentence:
            continue
        if idx in resolved:
            continue
        if next_unparsed is not None and sentence == next_unparsed:
            questions.append(Question(
                type="clarify_unparsed", unparsed_index=idx,
                options=options, confidence=0.5,
                prompt=f"Which capability does this sentence describe? \"{sentence}\"",
            ))
            next_unparsed = next(unparsed_iter, None)
    return questions


def contradiction_questions(features: dict[str, bool], parameters: dict[str, Any],
                            ontology: Ontology) -> list[Question]:
    """resolve_contradiction questions for hard contradicts constraints whose
    if_ side holds (mirrors the validator trigger semantics)."""
    questions = []
    for constraint in ontology.constraints:
        if constraint.type != "contradicts" or constraint.severity != "hard":
            continue
        if not constraint_holds(constraint.if_, features, parameters):
            continue
        fid = constraint.if_.feature
        questions.append(Question(
            type="resolve_contradiction", feature_id=fid,
            options=[f"Change {constraint.if_.feature}",
                     f"Reconsider {constraint.then.feature if constraint.then else 'conflict'}"],
            confidence=1.0,
            prompt=constraint.message or f"Conflicting choices involving {fid}.",
        ))
    return questions


def _as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        norm = value.strip().lower()
        if norm in {"yes", "true", "1"}:
            return True
        if norm in {"no", "false", "0"}:
            return False
    return None


def _parameter_answer_ok(key: str, value: Any, ontology: Ontology) -> bool:
    """True when a parameters.<key> answer is safe to decide against the
    ontology (known key; value shape/contents match the declared type).
    Guards recompute_spec from KeyError/TypeError on malformed answers."""
    fid, _, pid = key.partition(".")
    feature = ontology.features.get(fid)
    if feature is None:
        return False
    pdef = feature.parameters.get(pid)
    if pdef is None or value is None:
        return False
    if pdef.type == "choice":
        return isinstance(value, str) and value in pdef.options
    if pdef.type == "list[choice]":
        return (isinstance(value, list) and len(value) > 0
                and all(isinstance(item, str) and item in pdef.options
                        for item in value))
    if pdef.type == "list[string]":
        return (isinstance(value, list) and len(value) > 0
                and all(isinstance(item, str) and item for item in value))
    if pdef.type == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            return False
        if pdef.min is not None and value < pdef.min:
            return False
        if pdef.max is not None and value > pdef.max:
            return False
        return True
    return isinstance(value, str) and bool(value)


def run_mcq_loop(candidates: list[Candidate], ontology: Ontology,
                 user_answers: dict[str, Any] | None = None,
                 max_mcqs: int = 10, text: str | None = None,
                 laya=None) -> tuple[BackendSpec, list[Question]]:
    """Resolve interpreter candidates into a BackendSpec, returning the
    ordered list of questions still needing user input. Invalid parameter
    answers (unknown key, wrong type, disallowed choice, None) are ignored."""
    user_answers = user_answers or {}
    spec = PartialSpec()

    # 1) apply user answers directly to the partial spec
    for target, value in user_answers.items():
        if target.startswith("features."):
            fid = target[len("features."):]
            if fid not in ontology.features:
                continue
            b = _as_bool(value)
            if b is not None:
                spec.decide_feature(fid, enabled=b)
        elif target.startswith("parameters."):
            key = target[len("parameters."):]
            if _parameter_answer_ok(key, value, ontology):
                spec.decide_parameter(key, value=value)

    # 2) fold candidates into the same partial spec. The fold's is_decided
    #    guards ensure user answers from step 1 are never overridden.
    folded = fold_candidates(candidates, ontology, spec=spec)

    # 3) unparsed answers (require text)
    unparsed_resolved: dict[int, str] = {}
    if text is not None:
        for target, value in user_answers.items():
            if target.startswith("unparsed."):
                try:
                    idx = int(target[len("unparsed."):])
                except ValueError:
                    continue
                if isinstance(value, str) and value in ontology.features:
                    unparsed_resolved[idx] = value
                    folded.spec.decide_feature(value, enabled=True)

    # 4) cover/open questions
    open_questions = list(folded.negations)
    if text is not None:
        open_questions.extend(coverage_questions(text, candidates, ontology,
                                                 resolved=unparsed_resolved))
    open_questions.extend(next_questions(
        folded.spec, ontology, confidence=folded.feature_confidence))

    features = {fid: fid in folded.spec.enabled_features
                for fid in folded.spec.decided_features}
    contradiction = contradiction_questions(features, dict(folded.spec.parameter_values),
                                            ontology)
    open_questions.extend(contradiction)

    ordered = order_questions(open_questions, ontology)[:max_mcqs]

    # 5) assemble the final spec
    roles = folded.spec.parameter_values.get("roles.role_names", [])
    if not isinstance(roles, list):
        roles = [roles]
    spec_out = BackendSpec(
        version="1.0",
        ontology_version=ontology.version,
        created_at=datetime.now(timezone.utc),
        features=features,
        parameters=dict(folded.spec.parameter_values),
        roles=roles,
        rls_overrides={},
        decisions=[Decision(
            capability_id=c.capability_id, value=c.value,
            confidence=c.confidence, source=c.source, evidence=c.evidence,
        ) for c in candidates],
        defaulted=[],
        unsupported=folded.unsupported,
    )
    spec_out = recompute_spec(spec_out, ontology)
    return spec_out, ordered
