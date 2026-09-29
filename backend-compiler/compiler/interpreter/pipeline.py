"""Interpreter pipeline: run the three mechanisms and merge (Spec §3)."""

from __future__ import annotations

from compiler.interpreter.aliases import exact_match
from compiler.interpreter.merge import merge
from compiler.interpreter.negation import phrase_match_with_negation
from compiler.spec.models import Candidate

__all__ = ["candidates_from_laya_response", "laya_questions", "run_interpreter"]


def candidates_from_laya_response(response: dict) -> list[Candidate]:
    """Convert a Laya envelope's answers into Laya-sourced candidates.

    Candidate confidence comes from `answer_confidence` (the
    ECE-calibrated quantity), never from the bare `noul`/`choice` value.
    """
    candidates: list[Candidate] = []
    for qid, answer in response.get("answers", {}).items():
        if answer["type"] == "noul":
            value = bool(answer["noul"] >= 0.5)
        else:
            value = answer.get("choice")
        candidates.append(Candidate(
            capability_id=qid,
            value=value,
            confidence=answer["answer_confidence"],
            source="laya",
            evidence=None,
        ))
    return candidates


def laya_questions(ontology) -> dict:
    """Build the batched noul questions for Mechanism C (§3.1)."""
    return {
        f"needs_{item}": {
            "type": "noul",
            "instructions": f"Does this backend description require {item}?",
        }
        for item in ontology.items
    }


def run_interpreter(text: str, ontology, laya,
                    mechanisms: str = "ABC") -> list[Candidate]:
    """Run a subset of mechanisms A (exact), B (phrase+negation), C (Laya).

    `mechanisms` is a string of the letters 'A'/'B'/'C'. The default 'ABC'
    runs all three; the ablation harness (§5.2) uses 'A', 'B', 'AB' and 'C'
    to isolate each mechanism's contribution.
    """
    a = exact_match(text) if "A" in mechanisms else []
    b = phrase_match_with_negation(text) if "B" in mechanisms else []
    c = candidates_from_laya_response(
        laya.predict(text, laya_questions(ontology))
    ) if "C" in mechanisms else []
    return merge(a, b, c)