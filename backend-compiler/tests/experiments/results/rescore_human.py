import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")

import yaml  # noqa: E402

from tests.experiments.baselines import (  # noqa: E402
    BaselineResult,
    DbSmashBaseline,
    parse_backend_spec,
    score_baseline,
    table_names_from_sql,
)
from tests.experiments.run_baselines import labels_for  # noqa: E402
from tests.experiments.runner import load_test_ontology  # noqa: E402

ontology = load_test_ontology()
human = yaml.safe_load(Path("tests/annotation/human_gold.yaml").read_text(encoding="utf-8"))
rows = [json.loads(line) for line in Path("tests/experiments/results/baselines.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
out = []
for r in rows:
    if r["skipped"]:
        out.append(json.dumps(r))
        continue
    labels = labels_for(r["case"], {}, human, ontology)
    if r["baseline"] == "llm_backend_spec":
        spec = parse_backend_spec(r.get("raw_output", ""), ontology, case_name=r["case"])
        br = BaselineResult(baseline=r["baseline"], case=r["case"], skipped=False,
                            spec=spec, raw_output=r.get("raw_output", ""))
        br = score_baseline(br, labels, case_name=r["case"])
        r["metrics"] = br.metrics.__dict__ if br.metrics else None
        r["spec"] = None
    elif r["baseline"] in ("llm_direct_sql", "dbsmash"):
        raw = r.get("raw_output", "")
        if r["baseline"] == "dbsmash":
            r["extra"] = DbSmashBaseline.score_generator_tables(raw, labels.entities or [])
        else:
            tables = {t.lower() for t in table_names_from_sql(raw)}
            gold = {g.lower() for g in (labels.entities or [])}
            r["extra"] = {"tables_found": len(tables), "gold_tables": len(gold),
                          "tables_hit": len(tables & gold)}
    out.append(json.dumps(r, default=str))
Path("tests/experiments/results/baselines_human.jsonl").write_text(
    "\n".join(out) + "\n", encoding="utf-8")

parsed = [json.loads(o) for o in out]
ms = [r["metrics"] for r in parsed
      if r["baseline"] == "llm_backend_spec" and not r["skipped"] and r.get("metrics")]
print("backend_spec n=", len(ms),
      "mean recall=", round(sum(m["recall"] for m in ms) / len(ms), 3),
      "mean precision=", round(sum(m["precision"] for m in ms) / len(ms), 3),
      "omissions=", sum(m["omissions"] for m in ms),
      "halluc=", sum(m["hallucinations"] for m in ms))
for base in ("llm_direct_sql", "dbsmash"):
    rs = [r for r in parsed if r["baseline"] == base and not r["skipped"]]
    th = sum(r["extra"]["tables_hit"] for r in rs)
    gt = sum(r["extra"]["gold_tables"] for r in rs)
    tf = sum(r["extra"]["tables_found"] for r in rs)
    print(f"{base}: hit/gold={th}/{gt} ({round(th/gt, 3) if gt else 0}), "
          f"found={tf}, precision={round(th/tf, 3) if tf else 0}")
