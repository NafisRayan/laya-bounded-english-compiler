"""Real-Laya calibration measurement over the golden corpus (Paper §5.3).

Runs Mechanism C's actual noul questions with the pinned `english` checkpoint
(the real `laya` Router, not a persona mock) on every golden case and records,
per feature-item answer, whether the model's decision matches the case's gold
expectation::

    predicted = answer["noul"] >= 0.5            # the engine's decision rule
    truth     = expected_spec.features.get(item, False)
    label     = int(predicted == truth)

The ``(answer_confidence, label)`` pairs land in
``results/calibration_pairs.jsonl`` in exactly the schema of
``tests/fixtures/golden_calibration/*.json`` (bare list of
``{"answer_confidence", "label"}`` entries), and the summary reports the raw
ECE, the fitted temperature, the fitted ECE, and the auto-accept
coverage-vs-correctness sweep around the shipped 0.75 threshold.

Entity items are skipped: ``fold_candidates`` ignores entity candidates, so
their confidences never feed the auto-accept gate and they have no direct
gold label (entities are derived from features by ``recompute_spec``).

Usage:
    python -m tests.experiments.run_calibration [--device cpu] [--limit N]
        [--out PATH] [--summary PATH]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from compiler.interpreter.calibration import (
    apply_temperature,
    expected_calibration_error,
    fit_temperature,
)
from compiler.interpreter.laya_client import LayaClient
from compiler.interpreter.pipeline import laya_questions
from tests.experiments.runner import iter_cases, load_test_ontology

RESULTS_DIR = Path(__file__).parent / "results"

#: Auto-accept sweep anchors, including the shipped 0.75 CONFIDENCE_AUTO_ACCEPT.
SWEEP_THRESHOLDS = [round(0.50 + 0.05 * i, 2) for i in range(10)]


def collect_pairs(client, cases: list[tuple[str, dict]], ontology,
                  gold_by_case: dict | None = None) -> list[dict]:
    """One pair per (case, feature-item) noul answer; entity items skipped.

    ``gold_by_case`` overrides the truth source with the adjudicated human
    gold (case -> {features: {fid: bool}}) for claim-grade runs.
    """
    questions = laya_questions(ontology)
    pairs: list[dict] = []
    for case_name, data in cases:
        source = ((gold_by_case or {}).get(case_name)
                  or (data.get("expected_spec") or {}))
        gold_features = {
            fid: bool(enabled)
            for fid, enabled in (source.get("features") or {}).items()
        }
        response = client.predict(str(data["input"]), questions)
        for qid, answer in response.get("answers", {}).items():
            item = qid[len("needs_"):]
            if item not in ontology.features:
                continue
            predicted = bool(answer["noul"] >= 0.5)
            truth = gold_features.get(item, False)
            pairs.append({
                "case": case_name,
                "item": item,
                "noul": answer["noul"],
                "answer_confidence": answer["answer_confidence"],
                "predicted": predicted,
                "truth": truth,
                "label": int(predicted == truth),
            })
    return pairs


def sweep_thresholds(probs: list[float], labels: list[int],
                     thresholds: list[float]) -> list[dict]:
    """Coverage (share of decisions auto-accepted) and accuracy among them,
    per threshold. Coverage is monotonically non-increasing in T."""
    rows = []
    for t in thresholds:
        idx = [j for j, p in enumerate(probs) if p >= t]
        rows.append({
            "threshold": t,
            "n": len(idx),
            "coverage": len(idx) / len(probs) if probs else 0.0,
            "accuracy": (sum(labels[j] for j in idx) / len(idx)) if idx else None,
        })
    return rows


def write_summary(path: Path, pairs: list[dict], n_cases: int, ece_raw: float,
                  temperature: float, ece_fit: float, rows: list[dict]) -> None:
    """Write the human-readable calibration report (pragma: no cover — the
    real run exercises it; unit tests cover the math around it)."""
    accuracy = sum(p["label"] for p in pairs) / len(pairs)
    lines = [
        "# Real-Laya calibration report (golden corpus, pinned english checkpoint)",
        "",
        f"Pairs: {len(pairs)} (one per case x feature item; entity items skipped) "
        f"across {n_cases} cases.",
        f"Decision accuracy at the engine's rule (noul >= 0.5): {accuracy:.3f}",
        "",
        "| Quantity | Value |",
        "|---|---|",
        f"| Raw ECE (10 bins, shipped answer_confidence) | {ece_raw:.4f} |",
        f"| Gate (ECE < 0.1) | {'PASS' if ece_raw < 0.1 else 'FAIL'} |",
        f"| Fitted temperature | {temperature:.2f} |",
        f"| ECE after fit | {ece_fit:.4f} |",
        "",
        "## Auto-accept sweep (threshold on answer_confidence)",
        "",
        "| Threshold | Coverage | Accuracy among auto-accepted |",
        "|---|---|---|",
    ]
    for r in rows:
        acc = "n/a" if r["accuracy"] is None else f"{r['accuracy']:.3f}"
        lines.append(f"| {r['threshold']:.2f} | {r['coverage']:.3f} ({r['n']}) | {acc} |")
    lines += [
        "",
        "Honesty note: labels derive from the engine-pinned golden expectations",
        "(regression truth), not from independent human annotation; the pairs are",
        "in-sample for the same corpus R2 scores. 0.75 is the shipped",
        "CONFIDENCE_AUTO_ACCEPT.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - real-network entry point
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--device", default=None,
                        help="torch device for the Router (default LAYA_DEVICE or cpu)")
    parser.add_argument("--limit", type=int, default=None, help="only the first N cases")
    parser.add_argument("--gold", default="engine", choices=["engine", "human"],
                        help="truth labels: engine-pinned gold or the adjudicated human gold")
    parser.add_argument("--out", type=Path, default=RESULTS_DIR / "calibration_pairs.jsonl")
    parser.add_argument("--summary", type=Path,
                        default=RESULTS_DIR / "calibration_summary.md")
    args = parser.parse_args(argv)

    ontology = load_test_ontology()
    cases = iter_cases()
    if args.limit:
        cases = cases[: args.limit]

    client = LayaClient(device=args.device)
    gold_by_case = None
    if args.gold == "human":
        import yaml

        from tests.annotation.build_human_gold import HUMAN_GOLD_PATH

        gold_by_case = yaml.safe_load(HUMAN_GOLD_PATH.read_text(encoding="utf-8"))
    pairs = collect_pairs(client, cases, ontology, gold_by_case=gold_by_case)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as fh:
        for pair in pairs:
            fh.write(json.dumps(pair) + "\n")

    probs = [p["answer_confidence"] for p in pairs]
    labels = [p["label"] for p in pairs]
    ece_raw = expected_calibration_error(probs, labels, n_bins=10)
    temperature = fit_temperature(probs, labels)
    ece_fit = expected_calibration_error(
        [apply_temperature(p, temperature) for p in probs], labels, n_bins=10)
    rows = sweep_thresholds(probs, labels, SWEEP_THRESHOLDS)

    write_summary(args.summary, pairs, len(cases), ece_raw, temperature, ece_fit, rows)
    accuracy = sum(labels) / len(labels)
    print(f"pairs={len(pairs)} cases={len(cases)} accuracy={accuracy:.3f} "
          f"ECE={ece_raw:.4f} T={temperature:.2f} ECE_fit={ece_fit:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
