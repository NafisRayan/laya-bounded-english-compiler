"""LLM-as-annotator sensitivity pass (disclosed, not a human substitute).

Runs each golden-corpus input through a frontier LLM with the *same*
plain-language annotator instructions given to human annotators
(``tests/annotation/external/README-annotator.md``), records its worksheet
answers under ``tests/annotation/llm_annotator/{golden,held_out}/``, and
writes a MANIFEST.md capturing model, date, and yield so the paper can
report it as exactly what it is: one additional annotator that is
independent of the author, not an independent human.

This is a sensitivity check against author bias in the gold
(Paper §7, construct/internal threats), not a replacement for the
human external-annotation round (planned; see annotation-help/ at the
repository root).

Self-skips without credentials — the same gate as the baselines tier.

Usage:
    python -m tests.annotation.llm_annotator [--limit N] [--out tests/annotation/llm_annotator]
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import re
from pathlib import Path

import yaml

from tests._dotenv import load_dotenv

ANNOTATION_DIR = Path(__file__).parent
README = ANNOTATION_DIR / "external" / "README-annotator.md"

SYSTEM_PROMPT = """\
You are an independent annotator for a software-engineering study.
Follow the study instructions exactly. Emit ONLY a YAML object (no prose,
no code fences) with this shape:

case: <case name as given>
features: {{}}        # feature name -> true/false, only when the text speaks
parameters: {{}}      # parameter -> value, only when the text pins a choice
roles: []             # named user types as written
buckets: []           # file-upload purposes
edge_functions: []    # only if the text explicitly describes webhooks
notes: ""             # ambiguities in your own words
"""

_USER_PROMPT = """\
Study instructions (a fellow annotator gave you these; they bind you):

{instructions}

---

Case name: {case}

Backend description (the ONLY thing to annotate from):

{input}

Emit the YAML object now. Remember: silent feature = omit entirely;
explicitly forbidden feature = false; never infer from plausibility.
"""

FEATURE_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def _parse_yaml_answer(text: str) -> dict:
    """Best-effort YAML extraction: strip fences, take the first mapping."""
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:ya?ml)?\s*|\s*```$", "", cleaned, flags=re.S)
    match = re.search(r"(?s)^.*?(\{.*\}|case:.*|features:.*)$", cleaned)
    candidate = match.group(1) if match else cleaned
    data = yaml.safe_load(candidate)
    if not isinstance(data, dict):
        raise ValueError(f"answer is not a YAML mapping: {text[:120]!r}")
    return data


def _coerce(data: dict, case: str) -> tuple[dict, list[str]]:
    """Coerce one answer to the worksheet schema; return (answer, warnings)."""
    warnings: list[str] = []
    features = data.get("features") or {}
    if not isinstance(features, dict):
        warnings.append("features not a mapping; dropped")
        features = {}
    for name, value in list(features.items()):
        if not FEATURE_RE.match(str(name)):
            warnings.append(f"odd feature name kept as-is: {name}")
        if not isinstance(value, bool):
            features[name] = str(value).lower() in ("true", "yes", "1")
            warnings.append(f"coerced non-bool feature {name}")
    parameters = data.get("parameters") or {}
    if not isinstance(parameters, dict):
        warnings.append("parameters not a mapping; dropped")
        parameters = {}
    parameters = {str(k): str(v) for k, v in parameters.items()}
    roles = [str(r) for r in (data.get("roles") or [])]
    buckets = [str(b) for b in (data.get("buckets") or [])]
    edges = [str(e) for e in (data.get("edge_functions") or [])]
    answer = {
        "case": case,
        "features": features,
        "parameters": parameters,
        "roles": roles,
        "buckets": buckets,
        "edge_functions": edges,
        "notes": str(data.get("notes") or ""),
    }
    return answer, warnings


def run(out_dir: Path, limit: int | None = None,
        skip_existing: bool = False) -> int:
    from tests.experiments.baselines import default_completer
    from tests.experiments.runner import iter_cases
    from tests.experiments.splits import load_splits

    completer = default_completer()
    if completer is None:
        print("SKIP: no LLM credentials (OPENAI_BASE_URL+OPENAI_API_KEY / "
              "GEMINI_API_KEY / OPENAI_API_KEY / ANTHROPIC_API_KEY)")
        return 0

    instructions = README.read_text(encoding="utf-8")
    rubric_path = README.parent / "ROLES_RUBRIC.md"
    if rubric_path.exists():
        instructions += ("\n\n---\n\nROLES_RUBRIC.md (normative, referenced "
                         "above — follow it exactly):\n\n"
                         + rubric_path.read_text(encoding="utf-8"))
    instruction_sha = hashlib.sha256(instructions.encode()).hexdigest()[:16]
    splits = load_splits()
    by_name = {name: data for name, data in iter_cases()}
    order = list(splits["held_out"]) + list(splits["golden"])
    if limit:
        order = order[:limit]

    manifest = {
        "date": _dt.date.today().isoformat(),
        "annotator": "LLM (disclosed; not human)",
        "completer": type(completer).__name__,
        "model_env": {k: os.environ.get(k) for k in
                      ("OPENAI_MODEL", "GEMINI_MODEL") if os.environ.get(k)},
        "instructions": "tests/annotation/external/README-annotator.md",
        "instruction_sha256_16": instruction_sha,
        "cases": len(order),
        "failures": [],
        "warnings": {},
    }

    done = 0
    for case in order:
        target = out_dir / ("held_out" if case in splits["held_out"] else "golden") / f"{case}.yaml"
        target.parent.mkdir(parents=True, exist_ok=True)
        if skip_existing and target.exists():
            done += 1
            continue
        user = _USER_PROMPT.format(
            instructions=instructions, case=case,
            input=str(by_name[case]["input"]))
        try:
            raw = completer.complete(SYSTEM_PROMPT, user)
            answer, warnings = _coerce(_parse_yaml_answer(raw), case)
            if warnings:
                manifest["warnings"][case] = warnings
            target.write_text(
                yaml.safe_dump(answer, sort_keys=False), encoding="utf-8")
            done += 1
            print(f"[{done}/{len(order)}] {case}"
                  f" ({len(answer['features'])} features)")
        except Exception as exc:  # noqa: BLE001 - record and continue
            manifest["failures"].append({"case": case, "error": str(exc)[:200]})
            print(f"[FAIL] {case}: {exc}")

    (out_dir / "MANIFEST.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8")
    _write_manifest_md(out_dir, manifest)
    print(f"wrote {done}/{len(order)} annotations + MANIFEST under {out_dir}")
    return 0 if not manifest["failures"] else 1


def _write_manifest_md(out_dir: Path, manifest: dict) -> None:
    lines = [
        "# LLM-annotator run manifest (disclosed)",
        "",
        f"- Date: {manifest['date']}",
        f"- Annotator: {manifest['annotator']} via `{manifest['completer']}`",
        f"- Model: `{manifest['model_env']}`",
        f"- Instructions: `{manifest['instructions']}` "
        f"(sha256[:16] `{manifest['instruction_sha256_16']}`, identical text "
        "as issued to human annotators)",
        f"- Cases: {manifest['cases']} ({len(manifest['failures'])} failures)",
    ]
    if manifest["warnings"]:
        lines.append(f"- Coercion warnings: {len(manifest['warnings'])} cases")
    lines += [
        "",
        "This is a sensitivity datapoint against author bias in the gold,",
        "NOT a substitute for independent human annotation. The paper must",
        "label it exactly as an LLM annotator. Score with:",
        "",
        "    python -m tests.annotation.cohen_kappa "
        "--annotator2 tests/annotation/llm_annotator",
        "",
    ]
    (out_dir / "MANIFEST.md").write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--limit", type=int, default=None,
                        help="annotate only the first N cases (smoke run)")
    parser.add_argument("--resume", action="store_true",
                        help="skip cases whose output file already exists")
    parser.add_argument("--out", type=Path,
                        default=ANNOTATION_DIR / "llm_annotator")
    args = parser.parse_args(argv)
    load_dotenv()
    return run(args.out, args.limit, skip_existing=args.resume)


if __name__ == "__main__":
    raise SystemExit(main())
