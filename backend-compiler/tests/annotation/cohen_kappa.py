"""Cohen's kappa between annotator 1 (human_gold.yaml) and annotator 2.

Annotator 2 fills the blind worksheets produced by ``generate_worksheets``
under ``tests/annotation/second_annotator/{golden,held_out}`` using the
schema of docs/annotation-protocol.md. This tool compares them to annotator
1's gold on four dimensions: features, roles, buckets, edge_functions.

Operationalization
------------------
- features: one binary item per (case, feature) where the feature appears in
  EITHER annotation. Label = the annotation's boolean value; a feature absent
  from one annotation counts as False for that annotator (unmentioned = not
  enabled). Kappa is computed over the pooled item set.
- roles / buckets / edge_functions: set-valued. One binary item per
  (case, element) in either annotation's set; label = presence. Pooled
  kappa.

Decision rule (agreed): features kappa >= 0.61 -> gold validated;
< 0.61 -> case-by-case reconciliation.

Bands: >=0.80 strong, 0.61-0.80 substantial, 0.41-0.60 moderate, <0.41 failed.

Usage:
    python -m tests.annotation.cohen_kappa [--annotator2 tests/annotation/second_annotator]
"""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml

ANNOTATION_DIR = Path(__file__).parent
HUMAN_GOLD = ANNOTATION_DIR / "human_gold.yaml"

BANDS = [(0.80, "strong"), (0.61, "substantial"), (0.41, "moderate")]


def band(kappa: float) -> str:
    for lo, name in BANDS:
        if kappa >= lo:
            return name
    return "failed"


def load_annotator2(dirpath: Path) -> dict[str, dict]:
    """Read filled worksheets from {golden,held_out}/*.yaml, keyed by case."""
    entries: dict[str, dict] = {}
    for sub in ("golden", "held_out"):
        folder = dirpath / sub
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*.yaml")):
            entry = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            name = entry.get("case") or path.stem
            entries[name] = entry
    return entries


def is_unfilled(entry: dict) -> bool:
    return not (entry.get("features") or entry.get("parameters")
                or entry.get("roles") or entry.get("buckets")
                or entry.get("edge_functions"))


def cohen_kappa(items: list[tuple[bool, bool]]) -> tuple[float, float, int]:
    """Cohen's kappa over paired binary ratings. Returns (kappa, po, n)."""
    n = len(items)
    if n == 0:
        return float("nan"), float("nan"), 0
    a_yes = sum(1 for a, _ in items if a)
    b_yes = sum(1 for _, b in items if b)
    po = sum(1 for a, b in items if a == b) / n
    pe = (a_yes / n) * (b_yes / n) + ((n - a_yes) / n) * ((n - b_yes) / n)
    if pe == 1.0:
        return (1.0 if po == 1.0 else float("nan"), po, n)
    return (po - pe) / (1 - pe), po, n


def dimension_items(gold: dict[str, dict], a2: dict[str, dict],
                    dimension: str) -> list[tuple[bool, bool]]:
    """Pooled binary items for one dimension over shared cases."""
    items: list[tuple[bool, bool]] = []
    for case, one in gold.items():
        two = a2.get(case)
        if two is None or is_unfilled(two):
            continue
        if dimension == "features":
            keys = set(one.get("features") or {}) | set(two.get("features") or {})
            items.extend(
                (bool((one.get("features") or {}).get(k, False)),
                 bool((two.get("features") or {}).get(k, False)))
                for k in sorted(keys))
        else:
            set1 = set(one.get(dimension) or [])
            set2 = set(two.get(dimension) or [])
            items.extend((k in set1, k in set2) for k in sorted(set1 | set2))
    return items


def compute(annotator2_dir: Path) -> dict:
    gold = yaml.safe_load(HUMAN_GOLD.read_text(encoding="utf-8")) or {}
    a2 = load_annotator2(annotator2_dir)
    unfilled = sorted(c for c, e in a2.items() if is_unfilled(e))
    shared = [c for c in gold if c in a2 and not is_unfilled(a2[c])]
    missing = sorted(set(gold) - set(a2))

    report: dict = {
        "cases_gold": len(gold),
        "cases_annotator2": len(a2),
        "cases_compared": len(shared),
        "cases_unfilled_by_annotator2": unfilled,
        "cases_missing_from_annotator2": missing,
        "dimensions": {},
    }
    for dim in ("features", "roles", "buckets", "edge_functions"):
        items = dimension_items(gold, a2, dim)
        kappa, po, n = cohen_kappa(items)
        report["dimensions"][dim] = {
            "n_items": n, "raw_agreement": round(po, 4),
            "kappa": round(kappa, 4), "band": band(kappa),
        }
    fk = report["dimensions"]["features"]["kappa"]
    report["decision"] = (
        "gold validated (features kappa >= 0.61); keep everything"
        if fk >= 0.61 else
        "features kappa < 0.61: reconcile disagreements case-by-case; "
        "reconciled gold becomes final")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--annotator2", type=Path,
                        default=ANNOTATION_DIR / "second_annotator",
                        help="directory of annotator-2 worksheets")
    args = parser.parse_args(argv)
    report = compute(args.annotator2)
    print(yaml.safe_dump(report, sort_keys=False, allow_unicode=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
