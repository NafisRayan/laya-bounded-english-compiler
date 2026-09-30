import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")

from tests.experiments.baselines import DbSmashBaseline  # noqa: E402
from tests.experiments.metrics import extract_labels  # noqa: E402
from tests.experiments.runner import iter_cases  # noqa: E402

gold_by_case = {}
for name, data in iter_cases():
    ents = set(extract_labels(data.get("expected_spec") or {}).entities or ())
    gold_by_case[name] = ents

p = Path("tests/experiments/results/baselines.jsonl")
rows = [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
out = []
for r in rows:
    if r["baseline"] == "dbsmash" and not r["skipped"]:
        r["extra"] = DbSmashBaseline.score_generator_tables(
            r.get("raw_output", ""), gold_by_case.get(r["case"], set()))
    out.append(json.dumps(r, default=str))
p.write_text("\n".join(out) + "\n", encoding="utf-8")

d = [json.loads(line) for line in out
     if '"dbsmash"' in line and '"skipped": false' in line]
th = sum(r["extra"]["tables_hit"] for r in d)
gt = sum(r["extra"]["gold_tables"] for r in d)
tf = sum(r["extra"]["tables_found"] for r in d)
n_any = sum(1 for r in d if r["extra"]["tables_found"] > 0)
print("dbsmash measured:", len(d), "| cases producing tables:", n_any)
print("pooled table recall:", th, "/", gt, "=", round(th / gt, 3) if gt else None)
print("tables generated:", tf, "| table precision:", round(th / tf, 3) if tf else None)
