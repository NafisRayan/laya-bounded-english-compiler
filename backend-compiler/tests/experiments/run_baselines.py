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


def labels_for(case_name: str, data: dict, human_gold, ontology):
    """Scoring labels from the engine gold or the adjudicated human gold.

    Human gold never pins entities (they are derived from features), so for
    baseline artifact scoring they are re-derived from the enabled features'
    ``activates_entities`` — the same derivation ``recompute_spec`` applies.
    """
    if human_gold is None:
        return extract_labels(data.get("expected_spec") or {})
    entry = human_gold.get(case_name) or {}
    labels = extract_labels(entry)
    ents: set[str] = set()
    for fid, enabled in (entry.get("features") or {}).items():
        fdef = ontology.features.get(fid)
        if enabled and fdef:
            ents |= set(fdef.activates_entities)
    labels.entities = sorted(ents) if ents else None
    return labels


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--out", default=None)
    parser.add_argument("--summary", default=None)
    parser.add_argument("--gold", default="engine", choices=["engine", "human"],
                        help="scoring gold: engine-pinned expected_spec or the "
                             "adjudicated human gold (tests/annotation)")
    args = parser.parse_args(argv)

    suffix = "_human" if args.gold == "human" else ""
    out_path = Path(args.out or RESULTS_DIR / f"baselines{suffix}.jsonl")
    summary_path = Path(args.summary or RESULTS_DIR / f"baselines{suffix}_summary.md")

    ontology = load_test_ontology()
    cases = iter_cases()
    if args.limit:
        cases = cases[: args.limit]

    human_gold = None
    if args.gold == "human":
        import yaml

        from tests.annotation.build_human_gold import HUMAN_GOLD_PATH

        human_gold = yaml.safe_load(HUMAN_GOLD_PATH.read_text(encoding="utf-8"))

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
                labels = labels_for(case_name, data, human_gold, ontology)
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
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())