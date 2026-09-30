"""Merge & conflict resolution across extraction mechanisms (Spec §3.3).

Three priority tiers, highest-first: exact > phrase/phrase_negated (shared
tier) > laya.
"""

from __future__ import annotations

from collections import defaultdict

from compiler.interpreter.aliases import exact_match
from compiler.interpreter.negation import SENTENCE_BOUNDARY
from compiler.interpreter.rules import phrase_match
from compiler.spec.models import Candidate

__all__ = ["check_coverage", "merge"]


def _feature_target(capability_id: str) -> str:
    """The fold-level feature a candidate targets, so that `needs_payments`
    (laya) and `payments.enabled` (rules) group into one tier contest instead
    of twinning through to the fold, where the laya copy triggers a spurious
    negation conflict."""
    raw = capability_id
    if raw.startswith("needs_"):
        raw = raw[len("needs_"):]
    if raw.endswith(".enabled"):
        raw = raw[: -len(".enabled")]
    return raw


def merge(candidates_a, candidates_b, candidates_c) -> list[Candidate]:
    by_cap: dict[str, list[Candidate]] = defaultdict(list)
    for c in candidates_a + candidates_b + candidates_c:
        by_cap[_feature_target(c.capability_id)].append(c)

    merged: list[Candidate] = []
    for cands in by_cap.values():
        for tier in (("exact",), ("phrase", "phrase_negated"), ("laya",)):
            same_tier = [c for c in cands if c.source in tier]
            if same_tier:
                values = {c.value for c in same_tier}
                if len(values) > 1:
                    merged.extend(same_tier)
                else:
                    merged.append(max(same_tier, key=lambda c: c.confidence))
                break
    return merged


def check_coverage(text: str, mapped: list[Candidate]) -> list[str]:
    """Return sentences that map to no candidate (Spec §3.6).

    A sentence is covered if any mapped candidate's evidence is a substring
    of it, or if it re-matches the exact/phrase mechanisms directly.
    """
    unparsed: list[str] = []
    for chunk in SENTENCE_BOUNDARY.split(text):
        sentence = chunk.strip()
        if not sentence:
            continue
        covered = any(c.evidence and c.evidence in sentence for c in mapped)
        if not covered:
            covered = bool(exact_match(sentence) or phrase_match(sentence))
        if not covered:
            unparsed.append(sentence)
    return unparsed