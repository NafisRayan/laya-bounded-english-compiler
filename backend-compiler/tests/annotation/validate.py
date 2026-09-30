"""Annotation worksheet validation and blind scoring (protocol §Adjudication).

Two modes, deliberately separate so a `--check` pass never reveals gold:

    python -m tests.annotation.validate --check          # schema-only
    python -m tests.annotation.validate --score          # after you finish

`--check` verifies every worksheet parses and only contains known keys and
ontology-valid values (features/parameters must exist in the test ontology;
choices must be legal). `--score` additionally compares against the
engine-pinned gold per case and prints the disagreement list that
DISAGREEMENTS.md is made of. `--score --set held_out` scores the held-out
fifteen.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from tests.annotation.generate_worksheets import ANNOTATION_DIR
from tests.experiments.metrics import extract_labels
from tests.experiments.runner import iter_cases, load_test_ontology

__all__ = ["load_worksheets", "check_worksheet", "score_worksheets"]

KNOWN_KEYS = {"case", "input", "features", "parameters", "roles",
              "buckets", "edge_functions", "notes"}


def load_worksheets(root: Path, set_name: str) -> dict[str, dict]:
    out = {}
    for path in sorted((root / set_name).glob("*.yaml")):
        out[path.stem] = yaml.safe_load(path.read_text(encoding="utf-8"))
    return out


def check_worksheet(case: str, data: dict, ontology, errors: list[str]) -> None:
    unknown = set(data) - KNOWN_KEYS
    if unknown:
        errors.append(f"{case}: unknown keys {sorted(unknown)}")
    if not isinstance(data.get("features", {}), dict):
        errors.append(f"{case}: features must be a mapping")
    for fid, enabled in (data.get("features") or {}).items():
        if fid not in ontology.features:
            errors.append(f"{case}: unknown feature {fid!r}")
        if not isinstance(enabled, bool):
            errors.append(f"{case}: features.{fid} must be true/false")
    for key, value in (data.get("parameters") or {}).items():
        fid, _, pid = key.partition(".")
        pdef = ontology.features.get(fid, None)
        pdef = pdef.parameters.get(pid) if pdef else None
        if pdef is None:
            errors.append(f"{case}: unknown parameter {key!r}")
        elif pdef.type == "choice" and value not in pdef.options:
            errors.append(f"{case}: {key}={value!r} not in {pdef.options}")
    for name in (data.get("roles") or []):
        if name not in ontology.roles:
            errors.append(f"{case}: unknown role {name!r}")
    for name in (data.get("buckets") or []):
        if name not in ontology.buckets:
            errors.append(f"{case}: unknown bucket {name!r}")


def score_worksheets(root: Path, set_name: str) -> dict:
    ontology = load_test_ontology()
    gold_by_case = {name: data for name, data in iter_cases()}
    problems: list[str] = []
    disagreements: list[dict] = []
    worksheets = load_worksheets(root, set_name)
    if not worksheets:
        problems.append(f"no worksheets found under {root / set_name}")
    for case, data in sorted(worksheets.items()):
        check_worksheet(case, data, ontology, problems)
        if case not in gold_by_case:
            problems.append(f"{case}: no golden case with this name")
            continue
        mine = extract_labels(data)
        theirs = extract_labels(gold_by_case[case].get("expected_spec") or {})
        comparable = {
            "features": {f for f, enabled in (mine.feature_map or {}).items() if enabled},
            "parameters": set((mine.parameters or {}).items()),
            "roles": set(mine.roles or ()),
            "entities": set(mine.entities or ()),
            "buckets": {b.get("purpose") or b.get("name") for b in (mine.buckets or [])},
            "edge_functions": set(mine.edge_functions or ()),
        }
        gold_comparable = {
            "features": {f for f, enabled in (theirs.feature_map or {}).items() if enabled},
            "parameters": set((theirs.parameters or {}).items()),
            "roles": set(theirs.roles or ()),
            "entities": set(theirs.entities or ()),
            "buckets": {b.get("purpose") or b.get("name") for b in (theirs.buckets or [])},
            "edge_functions": set(theirs.edge_functions or ()),
        }
        for kind, a in comparable.items():
            b = gold_comparable[kind]
            for item in sorted(a - b):
                disagreements.append({"case": case, "kind": kind, "item": item,
                                      "side": "annotation-only"})
            for item in sorted(b - a):
                disagreements.append({"case": case, "kind": kind, "item": item,
                                      "side": "engine-only"})
    return {"n": len(worksheets), "problems": problems,
            "disagreements": disagreements}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true",
                        help="validate worksheet structure without scoring")
    parser.add_argument("--score", action="store_true",
                        help="score against engine-pinned gold")
    parser.add_argument("--set", default="golden", choices=["golden", "held_out"])
    parser.add_argument("--root", type=Path, default=ANNOTATION_DIR)
    parser.add_argument("--json", action="store_true", help="machine output")
    args = parser.parse_args(argv)

    if args.score:
        result = score_worksheets(args.root, args.set)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"worksheets: {result['n']}")
            for p in result["problems"]:
                print("PROBLEM:", p)
            print(f"disagreements: {len(result['disagreements'])}")
            for d in result["disagreements"]:
                print(f"  {d['case']}: {d['kind']} {d['item']!r} ({d['side']})")
        return 1 if result["problems"] else 0

    ontology = load_test_ontology()
    problems: list[str] = []
    worksheets = load_worksheets(args.root, args.set)
    if not worksheets:
        problems.append(f"no worksheets found under {args.root / args.set}")
    for case, data in sorted(worksheets.items()):
        check_worksheet(case, data, ontology, problems)
    for p in problems:
        print("PROBLEM:", p)
    print(f"{len(worksheets)} worksheets checked, {len(problems)} problems")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
