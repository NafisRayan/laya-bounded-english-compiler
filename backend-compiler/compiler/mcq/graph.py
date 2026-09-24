"""Question ordering (Developer Spec.md §4.3)."""

from __future__ import annotations

from compiler.mcq.selector import Question
from compiler.mcq.thresholds import MCQ_MIN
from compiler.ontology.loader import Ontology

__all__ = ["order_questions"]


def _feature_depths(ontology: Ontology) -> dict[str, int]:
    depths: dict[str, int] = {}

    def depth(fid: str, stack: frozenset[str]) -> int:
        if fid in depths:
            return depths[fid]
        if fid in stack:  # cycle guard: validator flags cycles separately
            return 0
        requires = ontology.features[fid].requires
        d = 0 if not requires else 1 + max(depth(r, stack | {fid}) for r in requires)
        depths[fid] = d
        return d

    for fid in ontology.features:
        depth(fid, frozenset())
    return depths


def _rank(q: Question) -> int:
    if q.type == "resolve_contradiction":
        return 0
    if q.type == "resolve_negation":
        return 1
    if q.type == "clarify_unparsed":
        return 2
    if q.type == "confirm_feature":
        return 3 if q.confidence < MCQ_MIN else 4
    if q.type == "choose_parameter":
        return 5
    if q.type == "confirm_weak":  # unranked in §4.3; sorts last
        return 6
    return 7


def order_questions(questions: list[Question],
                    ontology: Ontology | None = None) -> list[Question]:
    """Order questions by type priority, then dependency depth (if ontology
    given), then ids. Stable — preserves caller order within a tie."""
    depths = _feature_depths(ontology) if ontology else {}
    return sorted(
        questions,
        key=lambda q: (
            _rank(q),
            depths.get(q.feature_id or "", 0),
            q.feature_id or "",
            q.parameter_id or "",
        ),
    )
