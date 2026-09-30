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

from tests._dotenv import load_dotenv
from tests.experiments.baselines import BaselineResult, all_baselines, score_baseline
from tests.experiments.metrics import extract_labels
from tests.experiments.runner import iter_cases, load_test_ontology

load_dotenv()

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

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    def read_rows() -> list[dict]:
        rows: list[dict] = []
        if not out_path.exists():
            return rows
        for line in out_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # partial line from an interrupted run
        return rows

    done = {(row["baseline"], row["case"]) for row in read_rows()}

    with out_path.open("a", encoding="utf-8") as fh:
        for baseline in all_baselines(ontology):
            for case_name, data in cases:
                if (baseline.name, case_name) in done:
                    continue
                labels = extract_labels(data.get("expected_spec") or {})
                if baseline.name in ("llm_direct_sql", "dbsmash"):
                    result: BaselineResult = baseline.run(
                        str(data["input"]), case_name=case_name,
                        gold_entities=labels.entities or (),
                    )
                else:
                    result = baseline.run(str(data["input"]), case_name=case_name)
                result = score_baseline(result, labels, case_name=case_name)
                fh.write(json.dumps(asdict(result), default=str) + "\n")
                fh.flush()
                status = "MEASURED" if not result.skipped else "skip"
                print(f"{baseline.name:16s} {case_name:45s} {status}", flush=True)
                if result.skip_reason:
                    print(f"    - {result.skip_reason}", flush=True)

    by_name: dict[str, dict] = {}
    for row in read_rows():
        name = row["baseline"]
        info = by_name.setdefault(name, {"runs": 0, "skipped": 0, "measured": 0})
        info["runs"] += 1
        info["skipped" if row["skipped"] else "measured"] += 1

    lines = [
        "# Baseline harness report (golden corpus)", "",
        "Baseline | runs | skipped | measured | gate",
        "---|---|---|---|---",
    ]
    for name, info in by_name.items():
        lines.append(
            f"{name} | {info['runs']} | {info['skipped']} | {info['measured']} | "
            "credential-gated (GEMINI_API_KEY / OPENAI_API_KEY / ANTHROPIC_API_KEY)")
    Path(args.summary).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())