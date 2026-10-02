"""Apply RECONCILIATION.yaml rulings to produce the final human gold.

- verdict `a1` (or a2 absent-side kept)  -> human gold stands: no change
- verdict `a2` with a value -> take annotator 2's value for the item
- verdict `a2` with a2 absent (None) -> remove the item from human gold
Rows ruled `none` were not generated (the ruling vocabulary is a1/a2/none
where none means remove - handled by the a2-absent case above only if the
user explicitly wrote it; explicit `none` verdicts remove the item too).
"""

import sys
from pathlib import Path

sys.path.insert(0, ".")

import yaml  # noqa: E402

from tests.annotation.build_human_gold import HUMAN_GOLD_PATH  # noqa: E402

RECON = Path("tests/annotation/RECONCILIATION.yaml")
A2_DIR = Path("tests/annotation/second_annotator")

rec = yaml.safe_load(RECON.read_text(encoding="utf-8"))
gold = yaml.safe_load(HUMAN_GOLD_PATH.read_text(encoding="utf-8"))

a2: dict[str, dict] = {}
for sub in ("golden", "held_out"):
    folder = A2_DIR / sub
    for path in sorted(folder.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        a2[data.get("case") or path.stem] = data

applied = 0
for case, block in rec.items():
    entry = gold[case]
    two = a2.get(case, {})
    for row in block.get("disagreements", []):
        verdict = row.get("final")
        if verdict not in ("a1", "a2", "none"):
            raise SystemExit(f"illegal verdict {verdict!r} in {case}")
        kind, key, v1, v2 = row["kind"], row["key"], row["a1"], row["a2"]
        if verdict in ("a1", "none"):
            if verdict == "none":
                # item belongs in neither reading: remove from human gold
                if kind == "features":
                    entry["features"].pop(key, None)
                elif kind == "parameters":
                    entry["parameters"].pop(key, None)
                elif kind in ("roles", "edge_functions"):
                    entry[kind] = [x for x in entry[kind] if x != key]
                elif kind == "buckets":
                    entry["buckets"] = [x for x in entry["buckets"] if x != key]
                applied += 1
            continue
        # verdict == a2: take annotator 2's value
        if kind == "features":
            if v2 is None:
                entry["features"].pop(key, None)
            else:
                entry["features"][key] = bool(v2)
        elif kind == "parameters":
            if v2 is None:
                entry["parameters"].pop(key, None)
            else:
                entry["parameters"][key] = v2
        elif kind in ("roles", "edge_functions"):
            if v2 is None:
                entry[kind] = [x for x in entry[kind] if x != key]
            else:
                entry[kind] = sorted(set(entry[kind]) | {key})
        elif kind == "buckets":
            if v2 is None:
                entry["buckets"] = [x for x in entry["buckets"] if x != key]
            else:
                entry["buckets"] = sorted(set(entry["buckets"]) | {key})
        applied += 1

HUMAN_GOLD_PATH.write_text(yaml.safe_dump(gold, sort_keys=True), encoding="utf-8")
print(f"applied {applied} rulings -> final human gold ({len(gold)} cases)")
