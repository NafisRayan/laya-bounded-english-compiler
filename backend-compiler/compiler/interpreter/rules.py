"""Mechanism B — phrase patterns (Developer Spec.md §3.1).

Positive matching only; negation-aware matching lives in
``compiler.interpreter.negation.phrase_match_with_negation``.
"""

from __future__ import annotations

import re

from compiler.spec.models import Candidate

__all__ = ["PHRASE_RULES", "phrase_match"]

PHRASE_RULES = [
    # NOTE: second group is (each other|user|owner|renter)s? — plural-safe.
    # The spec's \b(owner|renter)\b cannot match "owners"/"renters", yet its
    # own §18.7 test asserts "owners can talk to renters" -> messaging.
    (r"\b(message|chat|dm|contact|talk to)\b.*\b(each other|user|owner|renter)s?\b",
     "messaging.enabled", True, 0.9),
    (r"\b(book|reserve|rent)\b.*\b(equipment|item|listing|property)\b",
     "bookings.enabled", True, 0.9),
    (r"\b((?:pay|payment)s?|charge|checkout|stripe)\b",
     "payments.enabled", True, 0.85),
    (r"\b(review|rate|rating|feedback)\b",
     "reviews.enabled", True, 0.85),
    (r"\b(upload|photo|image|file|document|avatar)\b",
     "file_storage.enabled", True, 0.8),
    (r"\b(verify|verification|kyc|id check|government id)\b",
     "verification.enabled", True, 0.8),
    (r"\b(admin|moderator|staff)\b",
     "roles.admin", True, 0.85),
    (r"\b(favorite|save for later|saved items|bookmark)\b",
     "favorites.enabled", True, 0.8),
]


def phrase_match(text: str) -> list[Candidate]:
    candidates = []
    for pattern, capability_id, positive_value, confidence in PHRASE_RULES:
        for m in re.finditer(pattern, text, flags=re.IGNORECASE):
            candidates.append(Candidate(
                capability_id=capability_id,
                value=positive_value,
                confidence=confidence,
                source="phrase",
                evidence=text[m.start():m.end()],
            ))
    return candidates