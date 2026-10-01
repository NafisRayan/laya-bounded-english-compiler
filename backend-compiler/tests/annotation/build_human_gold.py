"""Merge annotated worksheets + adjudication verdicts into the human gold
set (docs/annotation-protocol.md, §Adjudication).

Verdict application per disagreement row:

- ``annotator-misread``  -> the ENGINE side wins for that item (the
  worksheet value is removed, or the engine value is restored).
- ``engine-wrong`` / ``both-defensible`` -> the ANNOTATOR side stands
  (which for rows the annotator never wrote means the item stays out).

Entities are not represented: they are derived from features by
``recompute_spec``, and the protocol never asked the annotator to pin them.

Usage:
    python -m tests.annotation.build_human_gold
"""

from __future__ import annotations

from pathlib import Path

import yaml

from tests.annotation.generate_adjudication import ADJUDICATION_PATH
from tests.annotation.generate_worksheets import ANNOTATION_DIR
from tests.experiments.runner import iter_cases

__all__ = ["HUMAN_GOLD_PATH", "build_human_gold"]

HUMAN_GOLD_PATH = ANNOTATION_DIR / "human_gold.yaml"


def _apply_verdict(human: dict, engine: dict, row: dict) -> None:
    kind, item, side, verdict = (row["kind"], row["item"], row["side"],
                                 row["verdict"])
    if verdict != "annotator-misread":
        return  # annotator side stands; nothing to change

    only = side == "annotation-only"
    if kind == "features":
        if only:
            human["features"].pop(item, None)
        else:
            human["features"][item] = bool(engine["features"][item])
    elif kind == "parameters":
        # rows carry the full (key, value) pair from the label diff
        key, value = item[0], item[1]
        if only:
            human["parameters"].pop(key, None)
        else:
            if isinstance(value, list):
                value = [tuple(v) if isinstance(v, list) else v for v in value]
            human["parameters"][key] = value
    elif kind == "roles":
        if only:
            human["roles"] = [r for r in human["roles"] if r != item]
        else:
            human["roles"] = sorted(set(human["roles"]) | {item})
    elif kind == "edge_functions":
        if only:
            human["edge_functions"] = [e for e in human["edge_functions"]
                                       if e != item]
        else:
            human["edge_functions"] = sorted(set(human["edge_functions"]) | {item})
    elif kind == "buckets":
        if only:
            human["buckets"] = [b for b in human["buckets"] if b != item]
        else:
            human["buckets"] = sorted(set(human["buckets"]) | {item})


def build_human_gold(root: Path | None = None) -> dict:
    root = root or ANNOTATION_DIR
    adjudication = yaml.safe_load(ADJUDICATION_PATH.read_text(encoding="utf-8"))
    engine_by_case = {name: data for name, data in iter_cases()}

    human: dict[str, dict] = {}
    for set_name in ("golden", "held_out"):
        for path in sorted((root / set_name).glob("*.yaml")):
            case = path.stem
            worksheet = yaml.safe_load(path.read_text(encoding="utf-8"))
            entry = {
                "features": dict(worksheet.get("features") or {}),
                "parameters": dict(worksheet.get("parameters") or {}),
                "roles": list(worksheet.get("roles") or []),
                "buckets": list(worksheet.get("buckets") or []),
                "edge_functions": list(worksheet.get("edge_functions") or []),
            }
            engine_spec = (engine_by_case[case].get("expected_spec") or {})
            for row in (adjudication.get(case, {}).get("disagreements") or []):
                _apply_verdict(entry, engine_spec, row)
            human[case] = entry

    (root / "human_gold.yaml").write_text(
        yaml.safe_dump(human, sort_keys=True), encoding="utf-8")
    return human


if __name__ == "__main__":
    gold = build_human_gold()
    print(f"wrote human gold for {len(gold)} cases -> {HUMAN_GOLD_PATH}")
