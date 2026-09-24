"""Mechanism A — exact alias mappings (Developer Spec.md §3.1)."""

from __future__ import annotations

import re

from compiler.spec.models import Candidate

__all__ = ["EXACT_MAP", "exact_match"]

EXACT_MAP = {
    "stripe": ("payments.provider", "stripe", 1.0),
    "google auth": ("authentication.method", "oauth_google", 1.0),
    "magic link": ("authentication.method", "magic_link", 1.0),
    "github auth": ("authentication.method", "oauth_github", 1.0),
    "email password": ("authentication.method", "email_password", 1.0),
}


def exact_match(text: str) -> list[Candidate]:
    """Word-boundary, case-insensitive lookup of EXACT_MAP aliases.

    Evidence is the normalized alias (lowercase key), so two inputs that
    differ only in case produce identical Candidate objects.
    """
    lowered = text.lower()
    candidates = []
    for alias, (capability_id, value, confidence) in EXACT_MAP.items():
        if re.search(rf"\b{re.escape(alias)}\b", lowered):
            candidates.append(Candidate(
                capability_id=capability_id,
                value=value,
                confidence=confidence,
                source="exact",
                evidence=alias,
            ))
    return candidates