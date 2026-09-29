"""Ablation CLI: mechanism x MCQ grid over the golden corpus.

Usage:
    python -m tests.experiments.run_ablation [--out PATH] [--summary PATH]
        [--mechanisms "A,B,AB,C,ABC"] [--mcq on,off]

Writes a JSONL of per-run ``RunMetrics`` and a markdown summary suitable for
the §5.2 results table. Deterministic: successive runs over the same corpus
produce identical rows (the mock personas are tape-like).
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from tests.experiments.runner import (
    MECHANISM_LABELS,
    iter_cases,
    load_test_ontology,
    run_case,
)

RESULTS_DIR = Path(__file__).parent / "results"


def summarize(rows: list[dict]) -> dict:
    configs: dict[str, list[dict]] = {}
    for r in rows:
        key = f"{r['mechanisms']}|{r['mcq']}"
        configs.setdefault(key, []).append(r)

    out: dict[str, dict] = {}
    for key, group in configs.items():
        n = len(group)
        ms = sorted(r["ms"] for r in group)
        pooled_gold = sum(r["gold_features"] for r in group)
        pooled_pred = sum(r["decided_features"] for r in group)
        pooled_tp = sum(r["true_positives"] for r in group)
        out[key] = {
            "mechanisms": group[0]["mechanisms"],
            "mcq": bool(group[0]["mcq"]),
            "label": MECHANISM_LABELS[group[0]["mechanisms"]] + (
                " + MCQ" if group[0]["mcq"] else " (no MCQ)"),
            "n": n,
            "feature_recall_mean": sum(r["recall"] for r in group) / n,
            "feature_precision_mean": sum(r["precision"] for r in group) / n,
            "feature_recall_pooled": pooled_tp / pooled_gold if pooled_gold else 1.0,
            "feature_precision_pooled": pooled_tp / pooled_pred if pooled_pred else 1.0,
            "feature_exact": sum(1 for r in group
                                 if r["omissions"] == 0 and r["hallucinations"] == 0),
            "omissions_total": sum(r["omissions"] for r in group),
            "hallucinations_total": sum(r["hallucinations"] for r in group),
            "all_match": sum(1 for r in group if r["all_match"]),
            "params_match": sum(1 for r in group if r["params_match"]),
            "params_pinned": sum(1 for r in group if r["params_match"] is not None),
            "roles_match": sum(1 for r in group if r["roles_match"]),
            "roles_pinned": sum(1 for r in group if r["roles_match"] is not None),
            "entities_match": sum(1 for r in group if r["entities_match"]),
            "entities_pinned": sum(1 for r in group if r["entities_match"] is not None),
            "mcq_count_mean": sum(r["mcq_count"] for r in group) / n,
            "ms_mean": sum(r["ms"] for r in group) / n,
            "ms_median": ms[len(ms) // 2],
            "personas": sorted({r["persona"] for r in group}),
        }
    return out


def render_markdown(summary: dict) -> str:
    order = ["A", "B", "AB", "C", "ABC"]
    lines = [
        "# Ablation results (50 golden cases, mock Laya personas)",
        "",
        "Config | n | macro recall | macro precision | pooled recall | "
        "pooled precision | omissions | hallucinations | feature-exact | "
        "all-match | params (pinned) | MCQ count (mean) | ms (mean)",
        "---|---|---|---|---|---|---|---|---|---|---|---|---",
    ]
    for mech in order:
        for mcq in (True, False):
            key = f"{mech}|{mcq}"
            s = summary[key]
            p = f"{s['params_match']}/{s['params_pinned']}"
            lines.append(
                f"{s['label']} | {s['n']} | {s['feature_recall_mean']:.3f} | "
                f"{s['feature_precision_mean']:.3f} | "
                f"{s['feature_recall_pooled']:.3f} | "
                f"{s['feature_precision_pooled']:.3f} | "
                f"{s['omissions_total']} | {s['hallucinations_total']} | "
                f"{s['feature_exact']} | {s['all_match']} | {p} | "
                f"{s['mcq_count_mean']:.2f} | {s['ms_mean']:.1f}")
    lines.append("")
    lines.append("Personas used: **none** (43), **default** (5), **high** (2).")
    lines.append(
        "MCQ-off 'MCQ count' is the full residual question burden "
        "(untruncated): what the clarification loop would put to the user.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(RESULTS_DIR / "ablation.jsonl"))
    parser.add_argument("--summary", default=str(RESULTS_DIR / "ablation_summary.md"))
    parser.add_argument("--mechanisms", default="A,B,AB,C,ABC")
    parser.add_argument("--mcq", default="on,off")
    args = parser.parse_args(argv)

    mechs = [m.strip() for m in args.mechanisms.split(",") if m.strip()]
    mcq_modes = [m.strip() == "on" for m in args.mcq.split(",") if m.strip()]

    ontology = load_test_ontology()
    cases = iter_cases()

    rows = []
    for case_name, data in cases:
        for mech in mechs:
            for mcq_on in mcq_modes:
                metrics = run_case(case_name, data, ontology, mech, mcq_on)
                rows.append(asdict(metrics))

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")

    summary = summarize(rows)
    summary_path = Path(args.summary)
    summary_path.write_text(render_markdown(summary), encoding="utf-8")

    print(f"wrote {len(rows)} rows -> {out_path}")
    print(summary_path.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())