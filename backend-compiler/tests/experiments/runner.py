"""Run the mechanism x MCQ ablation grid over the golden corpus.

Each golden case (``tests/golden/cases/*.yaml``) is run through the SAME
pipeline as ``test_golden`` but with a mechanism subset and the clarification
loop toggled:

- mechanisms: 'A' exact aliases, 'B' phrase rules (+negation), 'C' Laya
  (mock persona), and the combinations 'AB' (rules-only), 'ABC' (hybrid).
- MCQ on: `user_answers` from the case are applied, exactly as the golden
  suite does, and the loop may surface questions.
- MCQ off: interpretation alone — no user answers, no questions surfaced
  (max_mcqs raised so the returned list is the full residual burden).

MCQ-off answers the R2/R1 question "how far does interpretation alone get",
and its returned question count IS the interactive burden — the questions
run_mcq_loop would put to the user.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import yaml

from compiler.interpreter.pipeline import run_interpreter
from compiler.mcq.pipeline import run_mcq_loop
from compiler.ontology.loader import Ontology, load_ontology
from tests.experiments.metrics import RunMetrics, extract_labels, score
from tests.experiments.personas import build_persona

__all__ = [
    "CASES_DIR",
    "ONTOLOGY_FIXTURE",
    "MECHANISM_LABELS",
    "iter_cases",
    "run_case",
]

CASES_DIR = Path(__file__).parent.parent / "golden" / "cases"
ONTOLOGY_FIXTURE = Path(__file__).parent.parent / "fixtures" / "ontology.yaml"

MECHANISM_LABELS = {
    "A": "A only",
    "B": "B only",
    "AB": "A+B (rules)",
    "C": "C only (Laya)",
    "ABC": "A+B+C (hybrid)",
}


def load_test_ontology() -> Ontology:
    return load_ontology(ONTOLOGY_FIXTURE)


def iter_cases() -> list[tuple[str, dict[str, Any]]]:
    out: list[tuple[str, dict[str, Any]]] = []
    for path in sorted(CASES_DIR.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        out.append((path.stem, data))
    return out


def run_case(case_name: str, data: dict[str, Any], ontology: Ontology,
             mechanisms: str, mcq_on: bool) -> RunMetrics:
    persona_name = str(data.get("laya", "default"))
    persona = build_persona(persona_name)
    labels = extract_labels(data.get("expected_spec") or {})

    candidates = run_interpreter(str(data["input"]), ontology, laya=persona,
                                 mechanisms=mechanisms)

    start = time.perf_counter()
    if mcq_on:
        spec, questions = run_mcq_loop(
            candidates, ontology,
            user_answers=data.get("user_answers") or {},
            text=str(data["input"]), laya=persona,
            max_mcqs=int(data.get("max_mcqs", 10)),
        )
    else:
        spec, questions = run_mcq_loop(
            candidates, ontology, user_answers={},
            text=str(data["input"]), laya=persona,
            max_mcqs=100_000,
        )
    elapsed_ms = (time.perf_counter() - start) * 1000.0

    metrics = score(spec, labels, case=case_name, mechanisms=mechanisms,
                    mcq=mcq_on, persona=persona_name)
    metrics.ms = elapsed_ms
    metrics.mcq_count = len(questions)
    return metrics