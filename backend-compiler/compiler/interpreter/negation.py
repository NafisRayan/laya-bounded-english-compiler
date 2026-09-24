"""Negation detection with sentence-boundary clamping (Spec §3.2)."""

from __future__ import annotations

import re

from compiler.interpreter.rules import PHRASE_RULES
from compiler.spec.models import Candidate

__all__ = [
    "NEGATION_EXCEPTIONS",
    "NEGATION_PATTERNS",
    "NEGATION_WINDOW_CHARS",
    "SENTENCE_BOUNDARY",
    "is_negated",
    "phrase_match_with_negation",
]

NEGATION_PATTERNS = [
    r"\b(?:no|not|never|without|avoid|skip|except|none)\b",
    r"\b(?:don't|doesn't|won't|can't|cannot|isn't|aren't|wasn't|weren't)\b",
    r"\b(?:do not|does not|will not|can not|is not|are not|was not|were not)\b",
    r"\b(?:no need(?: for)?|don't need|do not need|don't want|do not want)\b",
    r"\b(?:shouldn't|should not|wouldn't|would not)\b",
]

NEGATION_EXCEPTIONS = [
    r"\bno matter\b",
    r"\bno doubt\b",
    r"\bnot only\b",
    r"\bnot to mention\b",
    r"\bneedless to say\b",
]

NEGATION_WINDOW_CHARS = 40
SENTENCE_BOUNDARY = re.compile(r"[.?!]\s+")


def _mask_exceptions(text: str) -> str:
    masked = text
    for exc in NEGATION_EXCEPTIONS:
        for m in re.finditer(exc, masked, flags=re.IGNORECASE):
            masked = masked[:m.start()] + (" " * (m.end() - m.start())) + masked[m.end():]
    return masked


def _clamp_window(text: str, start: int, end: int,
                  window_chars: int) -> tuple[int, int]:
    # NOTE: left begins at 0, NOT at `start`. The spec's §3.2 snippet
    # initializes `left = start`, which kills the backward window whenever
    # no sentence boundary precedes the match — failing its own §18.3 tests
    # (e.g. "please don't charge users with Stripe" must see "don't").
    left = 0
    for m in SENTENCE_BOUNDARY.finditer(text, 0, start):
        left = m.end()
    left = max(left, start - window_chars)

    right_match = SENTENCE_BOUNDARY.search(text, end)
    right = right_match.start() if right_match else len(text)
    right = min(right, end + window_chars)
    return left, right


def is_negated(text: str, match_start: int, match_end: int,
               window_chars: int = NEGATION_WINDOW_CHARS) -> bool:
    masked = _mask_exceptions(text.lower())
    win_start, win_end = _clamp_window(masked, match_start, match_end, window_chars)
    window = masked[win_start:win_end]
    for pattern in NEGATION_PATTERNS:
        if re.search(pattern, window):
            return True
    return False


def phrase_match_with_negation(text: str) -> list[Candidate]:
    candidates = []
    for pattern, capability_id, positive_value, confidence in PHRASE_RULES:
        for m in re.finditer(pattern, text, flags=re.IGNORECASE):
            negated = is_negated(text, m.start(), m.end())
            value = (not positive_value) if negated else positive_value
            source = "phrase_negated" if negated else "phrase"
            candidates.append(Candidate(
                capability_id=capability_id,
                value=value,
                confidence=confidence,
                source=source,
                evidence=text[m.start():m.end()],
            ))
    return candidates