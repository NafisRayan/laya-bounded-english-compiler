"""Annotation worksheet generation (docs/annotation-protocol.md).

Writes one blank worksheet per golden case under tests/annotation/, with the
input text and the answer schema, and NOTHING from the engine's expectations
— the annotator must not see `expected_spec`.

Usage:
    python -m tests.annotation.generate_worksheets [--out tests/annotation]
"""

from __future__ import annotations

import argparse
from pathlib import Path

from tests.experiments.runner import iter_cases
from tests.experiments.splits import load_splits

__all__ = ["ANNOTATION_DIR", "WORKSHEET_TEMPLATE", "generate_worksheets"]

ANNOTATION_DIR = Path(__file__).parent.parent / "annotation"

WORKSHEET_TEMPLATE = """\
# Annotation worksheet — {case} ({set_name} set)
# Protocol: docs/annotation-protocol.md. Fill ONLY from the input text.
# Omit a feature if the input is silent on it; do not guess.
case: {case}
input: {input!r}
features: {{}}
parameters: {{}}
roles: []
buckets: []
edge_functions: []
notes: ""
"""


def generate_worksheets(out_dir: Path | None = None) -> tuple[int, int]:
    splits = load_splits()
    out = out_dir or ANNOTATION_DIR
    counts = {}
    for set_name, cases in (("held_out", splits["held_out"]),
                            ("golden", splits["golden"])):
        target = out / set_name
        target.mkdir(parents=True, exist_ok=True)
        by_name = {name: data for name, data in iter_cases()}
        for case in cases:
            data = by_name[case]
            worksheet = WORKSHEET_TEMPLATE.format(
                case=case, set_name=set_name, input=str(data["input"]))
            (target / f"{case}.yaml").write_text(worksheet, encoding="utf-8")
        counts[set_name] = len(cases)
    return counts["golden"], counts["held_out"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=ANNOTATION_DIR)
    args = parser.parse_args(argv)
    golden, held = generate_worksheets(args.out)
    print(f"wrote {golden} golden + {held} held_out worksheets under {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
