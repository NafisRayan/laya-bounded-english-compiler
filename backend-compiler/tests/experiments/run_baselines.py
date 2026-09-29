"""Baseline harness CLI: run external baselines over the golden corpus.

Usage:
    python -m tests.experiments.run_baselines [--limit N] [--out PATH]
        [--summary PATH]

Every baseline adapter self-skips when its credentials are absent (no
OPENAI_API_KEY / ANTHROPIC_API_KEY, or an external tool not configured), so
the harness is CI-safe and only produces *measured* rows when keys exist —
the same gate as the e2e tier.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from tests.experiments.baselines import BaselineResult, all_baselines, score_baseline
from tests.experiments.metrics import extract_labels
from tests.experiments.runner import iter_cases, load_test_ontology

RESULTS_DIR = Path(__file__).parent / "results"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--out", default=str(RESULTS_DIR / "baselines.jsonl"))
    parser.add_argument("--summary", default=str(RESULTS_DIR / "baselines_summary.md"))
    args = parser.parse_args(argv)

    ontology = load_test_ontology()
    cases = iter_cases()
    if args.limit:
        cases = cases[: args.limit]

    rows: list[dict] = []
    by_name: dict[str, dict] = {}
    for baseline in all_baselines(ontology):
        by_name[baseline.name] = {"runs": 0, "skipped": 0, "measured": 0}
        for case_name, data in cases:
            labels = extract_labels(data.get("expected_spec") or {})
            if baseline.name == "llm_direct_sql":
                result: BaselineResult = baseline.run(
                    str(data["input"]), case_name=case_name,
                    gold_entities=labels.entities or (),
                )
            else:
                result = baseline.run(str(data["input"]), case_name=case_name)
            result = score_baseline(result, labels, case_name=case_name)
            rows.append(asdict(result))
            by_name[baseline.name]["runs"] += 1
            key = "skipped" if result.skipped else "measured"
            by_name[baseline.name][key] += 1

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, default=str) + "\n")

    lines = [
        "# Baseline harness report (golden corpus)", "",
        "Baseline | runs | skipped | measured | gate",
        "---|---|---|---|---",
    ]
    for name, info in by_name.items():
        lines.append(
            f"{name} | {info['runs']} | {info['skipped']} | {info['measured']} | "
            "credential-gated (OPENAI_API_KEY / ANTHROPIC_API_KEY)")
    Path(args.summary).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())