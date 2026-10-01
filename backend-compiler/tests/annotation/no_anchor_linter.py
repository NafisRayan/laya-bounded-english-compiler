"""No-anchor linter: flag gold items whose tokens never appear in the input.

Built per the third-reader finding: clash-based adjudication cannot see
rows where annotator and engine AGREE on something the sentence never
says. This linter mechanically surfaces those candidates on BOTH golds.

Method (deliberately minimal, no judgment calls):

- tokens   = lowercase alphanumeric runs of the input, trailing 's' stripped
- synonyms = the third reader's seed map, applied to INPUT tokens only:
               hosts/host -> owner, guests/guest -> renter,
               vendors/vendor -> owner, chat/chats -> messaging
- an item is ANCHORED if any token of its anchor text appears in the
  (synonym-expanded) input tokens; otherwise it is a NO_ANCHOR candidate

Anchor text per kind:
- features:        the feature id (underscore-split)
- parameters:      the parameter VALUE (e.g. "owner_approval", "stripe")
- roles:           the role name
- buckets:         the purpose/name
- edge_functions:  the function name

The synonym map is the ONLY smoothing. Everything is reported raw: both
gold files, both splits (marked), anchored and unanchored alike. Ruling
on candidates belongs to the human team, not to this script.

Usage:
    python -m tests.annotation.no_anchor_linter [--annotation-dir DIR]
        [--cases-dir DIR]
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from tests.annotation.build_human_gold import HUMAN_GOLD_PATH
from tests.annotation.generate_worksheets import ANNOTATION_DIR
from tests.experiments.runner import iter_cases

__all__ = ["SYNONYM_MAP", "lint_gold", "main"]

SYNONYM_MAP = {
    "host": "owner",
    "hosts": "owner",
    "guest": "renter",
    "guests": "renter",
    "vendor": "owner",
    "vendors": "owner",
    "chat": "messaging",
    "chats": "messaging",
}

_GOLD_KINDS = ("features", "parameters", "roles", "buckets", "edge_functions")


def _tokens(text: str) -> set[str]:
    raw = (t.lower() for t in re.split(r"[^a-z0-9]+", text.lower()) if t)
    return {t[:-1] if t.endswith("s") and len(t) > 1 else t for t in raw}


def _input_tokens(inputs: dict[str, str], case: str) -> set[str]:
    toks = _tokens(inputs.get(case, ""))
    return toks | {SYNONYM_MAP[t] for t in toks if t in SYNONYM_MAP}


def _anchor_text(kind: str, item) -> str:
    if kind == "parameters":
        key, value = (list(item) if isinstance(item, (list, tuple)) else (item, ""))
        return f"{key} {value}"
    if isinstance(item, dict):
        return str(item.get("purpose") or item.get("name"))
    return str(item)


def _items_for_kind(entry: dict, kind: str) -> list:
    value = entry.get(kind)
    if value is None:
        return []
    if isinstance(value, dict):
        if kind == "features":
            return [f"{fid}:{enabled}" for fid, enabled in value.items()]
        if kind == "parameters":
            return [[k, v] for k, v in value.items()]
        return list(value)
    return list(value)


def lint_gold(gold: dict[str, dict], inputs: dict[str, str],
              splits: dict[str, list[str]]) -> list[dict]:
    rows = []
    for case, entry in sorted(gold.items()):
        split = "held_out" if case in splits.get("held_out", []) else "golden"
        in_toks = _input_tokens(inputs, case)
        for kind in _GOLD_KINDS:
            for item in _items_for_kind(entry, kind):
                # feature rows carry their enabled flag; anchor on the id
                anchor_src = item.split(":")[0] if kind == "features" else item
                toks = _tokens(_anchor_text(kind, anchor_src))
                matched = sorted(toks & in_toks)
                rows.append({
                    "case": case, "split": split, "kind": kind,
                    "item": item, "anchored": bool(matched),
                    "matched_tokens": matched,
                })
    return rows


def _engine_gold() -> dict[str, dict]:
    keep = ("features", "parameters", "roles", "buckets", "edge_functions")
    return {
        name: {k: (data.get("expected_spec") or {}).get(k) for k in keep}
        for name, data in iter_cases()
    }


def main(argv: list[str] | None = None) -> int:
    splits = yaml.safe_load(
        (Path(__file__).parent.parent / "golden" / "splits.yaml")
        .read_text(encoding="utf-8"))
    inputs = {name: str(data["input"]) for name, data in iter_cases()}

    human = yaml.safe_load(HUMAN_GOLD_PATH.read_text(encoding="utf-8"))
    engine = _engine_gold()

    for label, gold in (("human", human), ("engine", engine)):
        rows = lint_gold(gold, inputs, splits)
        report = ANNOTATION_DIR / f"anchor_lint_{label}.txt"
        with report.open("w", encoding="utf-8") as fh:
            for r in rows:
                mark = "ok      " if r["anchored"] else "NO_ANCHOR"
                fh.write(f"[{mark}] [{r['split']}] {r['case']} :: "
                         f"{r['kind']} = {r['item']} "
                         f"(matched: {r['matched_tokens']})\n")
        candidates = [r for r in rows if not r["anchored"]]
        held = [r for r in candidates if r["split"] == "held_out"]
        print(f"--- {label} gold: {len(rows)} items, "
              f"{len(candidates)} NO_ANCHOR candidates "
              f"({len(held)} in held_out) -> {report.name}")
        # mechanical grouping for batch rulings: same (kind, item) across
        # cases is one decision, not N. Grouping only — nothing is dropped.
        from collections import Counter

        grouped = Counter((r["kind"], str(r["item"])) for r in candidates)
        with report.open("a", encoding="utf-8") as fh:
            fh.write("\n### Batch view: rule once per distinct (kind, item)\n")
            for (kind, item), n in grouped.most_common():
                fh.write(f"  {n:3d}x  {kind} = {item}\n")
        for (kind, item), n in grouped.most_common():
            print(f"  {n:3d}x  {kind} = {item}")
    print("\nSynonym map (applied to input tokens only):", SYNONYM_MAP)
    print("Ruling on candidates belongs to the human team; "
          "this script takes no position.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
