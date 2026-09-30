"""Generate the adjudication worksheet from DISAGREEMENTS.json (protocol
§Adjudication).

One row per disagreement, grouped by case, with the case's input text beside
it and a blank ``verdict`` field. Fill each verdict with exactly one of:

    engine-wrong        # the gold expectation misreads the input
    annotator-misread   # the worksheet disagrees with a clear input
    both-defensible     # the input genuinely supports both readings

Usage:
    python -m tests.annotation.generate_adjudication
"""

from __future__ import annotations

import json
from pathlib import Path

from tests.annotation.generate_worksheets import ANNOTATION_DIR

__all__ = ["DISAGREEMENTS_PATH", "ADJUDICATION_PATH", "generate_adjudication"]

DISAGREEMENTS_PATH = ANNOTATION_DIR / "DISAGREEMENTS.json"
ADJUDICATION_PATH = ANNOTATION_DIR / "ADJUDICATION.yaml"

VERDICTS = ("engine-wrong", "annotator-misread", "both-defensible")


def generate_adjudication(root: Path | None = None) -> int:
    root = root or ANNOTATION_DIR
    data = json.loads((root / "DISAGREEMENTS.json").read_text(encoding="utf-8"))
    inputs = {}
    for set_name in ("golden", "held_out"):
        for p in sorted((root / set_name).glob("*.yaml")):
            import yaml
            inputs[p.stem] = yaml.safe_load(p.read_text(encoding="utf-8")).get("input", "")

    lines = [
        "# Adjudication worksheet - one verdict per disagreement.",
        f"# Verdicts: {' | '.join(VERDICTS)}",
        "",
    ]
    by_case: dict[str, list[dict]] = {}
    for d in data["disagreements"]:
        by_case.setdefault(d["case"], []).append(d)

    for case in sorted(by_case):
        lines += [f"{case}:", f'  input: {inputs.get(case, "")!r}', "  disagreements:"]
        for d in by_case[case]:
            lines += [
                f"    - kind: {d['kind']}",
                f"      item: {d['item']!r}",
                f"      side: {d['side']}",
                "      verdict: ",
            ]
        lines.append("")

    (root / "ADJUDICATION.yaml").write_text("\n".join(lines), encoding="utf-8")
    return len(data["disagreements"])


if __name__ == "__main__":
    raise SystemExit(generate_adjudication())
