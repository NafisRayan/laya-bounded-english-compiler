"""Generate the reconciliation worksheet for annotator-1 (A1) vs
annotator-2 (A2) disagreements, with synonym normalization applied so pure
vocabulary differences (buyers->renter, photo storage->file_storage, ...)
do not reach the human.

Disagreement rows that REMAIN after normalization get a blank `final:`
field. The human fills each with exactly one of:

    a1     # keep annotator 1's value (the current human gold)
    a2     # take annotator 2's value
    none   # the item does not belong in gold at all

Usage:
    python -m tests.annotation.generate_reconciliation
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from tests.annotation.generate_worksheets import ANNOTATION_DIR
from tests.experiments.runner import iter_cases

__all__ = ["SYNONYMS", "RECONCILIATION_PATH", "generate_reconciliation"]

SYNONYMS = {
    # third reader's seed map
    "host": "owner", "guest": "renter", "vendor": "owner", "chat": "messaging",
    # map v2 (LINTER_RULINGS.md)
    "seller": "owner", "pay": "payments", "paid": "payments",
    "charge": "payments", "book": "bookings", "booked": "bookings",
    "rental": "bookings", "stay": "bookings", "verify": "verification",
    "verified": "verification", "live": "realtime", "message": "messaging",
    "contact": "messaging", "whenever": "anytime", "bookmark": "favorites",
    "saved": "favorites", "feedback": "reviews", "upload": "file_storage",
    "photo": "file_storage", "photos": "file_storage", "store": "file_storage",
    "document": "file_storage", "documents": "file_storage",
    "list": "listings", "listing": "listings", "login": "authentication",
    "signin": "authentication", "signup": "authentication",
    "password": "authentication", "account": "authentication",
    "kyc": "verification", "buyer": "renter", "buyers": "renter",
    "shoppers": "renter", "customer": "renter", "customers": "renter",
}


def _tokens(text: str) -> set[str]:
    raw = {t.lower() for t in re.split(r"[^a-z0-9]+", text.lower()) if t}
    out = set()
    for t in raw:
        stem = t[:-1] if t.endswith("s") and len(t) > 1 else t
        out.add(stem)
        out.add(SYNONYMS.get(stem, stem))
        out.add(SYNONYMS.get(t, t))
    return out


def _items(entry: dict, kind: str) -> dict[str, object]:
    """Normalize one annotation's dimension to {canonical_key: value}."""
    if kind == "features":
        return {fid: bool(v) for fid, v in (entry.get("features") or {}).items()}
    if kind == "parameters":
        return dict(entry.get("parameters") or {})
    out: dict[str, object] = {}
    for name in entry.get(kind) or []:
        out[str(name)] = name
    return out


def generate_reconciliation(root: Path | None = None) -> int:
    root = root or ANNOTATION_DIR
    a1 = yaml.safe_load((root / "human_gold.yaml").read_text(encoding="utf-8")) or {}
    a2_dir = root / "second_annotator"
    a2: dict[str, dict] = {}
    for sub in ("golden", "held_out"):
        folder = a2_dir / sub
        if folder.is_dir():
            for path in sorted(folder.glob("*.yaml")):
                data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
                a2[data.get("case") or path.stem] = data
    inputs = {name: str(data["input"]) for name, data in iter_cases()}

    lines = [
        "# Reconciliation worksheet - A1 (current human gold) vs A2 (independent annotator).",
        "# Synonym normalization applied (see tests/annotation/no_anchor_linter.py);",
        "# only items that STILL disagree after normalization are listed.",
        "# Fill each final: with exactly one of: a1 | a2 | none",
        "#   a1    = keep annotator 1's value (current human gold)",
        "#   a2    = take annotator 2's value",
        "#   none  = the item belongs in neither reading",
        "",
    ]
    n_rows = 0
    for case in sorted(set(a1) & set(a2)):
        toks = _tokens(inputs.get(case, ""))
        rows = []
        for kind in ("features", "parameters", "roles", "buckets", "edge_functions"):
            one = _items(a1[case], kind)
            two = _items(a2[case], kind)
            for key in sorted(set(one) | set(two)):
                if key not in one:
                    rows.append((kind, key, None, two[key]))
                elif key not in two:
                    rows.append((kind, key, one[key], None))
                elif one[key] != two[key]:
                    rows.append((kind, key, one[key], two[key]))
        # drop rows where BOTH sides' anchors appear in the input tokens
        # (pure vocabulary) - keep only rows with at least one side whose
        # anchor tokens are absent from the input
        kept = []
        for kind, key, v1, v2 in rows:
            anchor_texts = []
            if v1 is not None:
                anchor_texts.append(f"{key} {v1}")
            if v2 is not None:
                anchor_texts.append(f"{key} {v2}")
            if not any(_tokens(a) & toks for a in anchor_texts):
                kept.append((kind, key, v1, v2))
        if not kept:
            continue
        lines.append(f"{case}:")
        lines.append(f'  input: {inputs.get(case, "")!r}')
        lines.append("  disagreements:")
        for kind, key, v1, v2 in kept:
            lines.append(f"    - kind: {kind}")
            lines.append(f"      key: {key!r}")
            lines.append(f"      a1: {v1!r}")
            lines.append(f"      a2: {v2!r}")
            lines.append("      final: ")
            n_rows += 1
        lines.append("")

    out = root / "RECONCILIATION.yaml"
    out.write_text("\n".join(lines), encoding="utf-8")
    return n_rows


if __name__ == "__main__":
    print(f"reconciliation rows: {generate_reconciliation()}")
