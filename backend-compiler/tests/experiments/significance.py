"""Significance tests for the claim-grade ablation rows (§4.4 protocol).

Computed on the de-contaminated human-gold runs (golden 35, real
checkpoint): exact McNemar on paired per-case binary outcomes, Wilcoxon
signed-rank on paired per-case recall, and percentile bootstrap CIs on
pooled recall/precision differences. Case-level McNemar is the case-level
approximation of the per-requirement test §4.4 names; n=35 bounds power —
reported, not hidden.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

RESULTS = Path(__file__).parent / "results"


def load(path: str) -> dict[str, dict]:
    rows = [json.loads(l) for l in (RESULTS / path).read_text(encoding="utf-8").splitlines() if l.strip()]
    return {f"{r['case']}|{r['mechanisms']}|{r['mcq']}": r for r in rows}


def exact_mcnemar(b: int, c: int) -> float:
    """Two-sided exact McNemar p-value on discordant pairs (b, c)."""
    from math import comb

    n = b + c
    if n == 0:
        return 1.0
    tail = sum(comb(n, k) for k in range(min(b, c) + 1))
    return min(1.0, 2 * tail / 2 ** n)


def wilcoxon_signed(pairs: list[tuple[float, float]]) -> tuple[float, float]:
    """Wilcoxon signed-rank (normal approximation with continuity
    correction) over non-zero differences; returns (W, p)."""
    diffs = sorted((b - a) for a, b in pairs)
    diffs = [d for d in diffs if d != 0]
    n = len(diffs)
    if n == 0:
        return 0.0, 1.0
    ranks = {}
    ordered = sorted(abs(d) for d in diffs)
    i = 0
    rank_sum = {}
    while i < len(ordered):
        j = i
        while j + 1 < len(ordered) and ordered[j + 1] == ordered[i]:
            j += 1
        avg_rank = (i + j) / 2 + 1
        rank_sum[ordered[i]] = avg_rank
        i = j + 1
    w_plus = sum(rank_sum[abs(d)] for d in diffs if d > 0)
    mu = n * (n + 1) / 4
    sigma = (n * (n + 1) * (2 * n + 1) / 6) ** 0.5
    from math import erf, sqrt

    if sigma == 0:
        return w_plus, 1.0
    z = (w_plus - mu) / sigma
    p = 2 * (1 - 0.5 * (1 + erf(abs(z) / sqrt(2))))
    return w_plus, p


def bootstrap_ci(pairs_a: list[dict], pairs_b: list[dict], metric: str,
                 n_boot: int = 10_000, seed: int = 20260930) -> tuple[float, float, float]:
    rng = random.Random(seed)
    n = len(pairs_a)
    stats = []
    for _ in range(n_boot):
        idx = [rng.randrange(n) for _ in range(n)]
        a = [pairs_a[i] for i in idx]
        b = [pairs_b[i] for i in idx]
        stats.append(_pooled(a, metric) - _pooled(b, metric))
    stats.sort()
    lo = stats[int(0.025 * n_boot)]
    hi = stats[int(0.975 * n_boot) - 1]
    point = _pooled(pairs_a, metric) - _pooled(pairs_b, metric)
    return point, lo, hi


def _pooled(rows: list[dict], metric: str) -> float:
    if metric == "recall":
        tp = sum(r["true_positives"] for r in rows)
        gold = sum(r["true_positives"] + r["omissions"] for r in rows)
        return tp / gold if gold else 1.0
    if metric == "precision":
        tp = sum(r["true_positives"] for r in rows)
        pred = sum(r["true_positives"] + r["hallucinations"] for r in rows)
        return tp / pred if pred else 1.0
    raise ValueError(metric)


def main() -> int:
    data = load("ablation_real_human.jsonl")
    rules = {k.replace("|AB|True", ""): v for k, v in data.items() if k.endswith("|AB|True")}
    hybrid = {k.replace("|ABC|True", ""): v for k, v in data.items() if k.endswith("|ABC|True")}

    cases = sorted(set(rules) & set(hybrid))
    # McNemar: hallucination-free per case
    b = sum(1 for c in cases if not hybrid[c]["hallucinations"] and rules[c]["hallucinations"])
    c = sum(1 for c in cases if hybrid[c]["hallucinations"] and not rules[c]["hallucinations"])
    p_hall = exact_mcnemar(b, c)
    # recall pairs
    pairs = [(rules[k]["recall"], hybrid[k]["recall"]) for k in cases]
    w, p_rec = wilcoxon_signed(pairs)
    # bootstrap CIs: hybrid minus rules
    ra = [hybrid[k] for k in cases]
    rb = [rules[k] for k in cases]
    r_pt, r_lo, r_hi = bootstrap_ci(ra, rb, "recall")
    p_pt, p_lo, p_hi = bootstrap_ci(ra, rb, "precision")

    print(f"n cases = {len(cases)} (golden, real checkpoint, de-contaminated operator)")
    print("hybrid vs rules MCQ-on:")
    print(f"  recall: hybrid {sum(r['recall'] for r in ra)/len(ra):.3f} vs rules {sum(r['recall'] for r in rb)/len(rb):.3f} macro; "
          f"Wilcoxon W={w:.0f} p={p_rec:.3f}")
    print(f"  hallucination-free cases: hybrid {sum(1 for k in cases if not hybrid[k]['hallucinations'])}/{len(cases)}, "
          f"rules {sum(1 for k in cases if not rules[k]['hallucinations'])}/{len(cases)}; "
          f"exact McNemar b={b} c={c} p={p_hall:.3f}")
    print(f"  pooled recall diff (hybrid-rules): {r_pt:+.3f}  CI95 [{r_lo:+.3f}, {r_hi:+.3f}]")
    print(f"  pooled precision diff: {p_pt:+.3f}  CI95 [{p_lo:+.3f}, {p_hi:+.3f}]")

    # MCQ-off recall lift: hybrid no-MCQ vs rules no-MCQ
    rules_off = {k.replace("|AB|False", ""): v for k, v in data.items() if k.endswith("|AB|False")}
    hybrid_off = {k.replace("|ABC|False", ""): v for k, v in data.items() if k.endswith("|ABC|False")}
    cases_off = sorted(set(rules_off) & set(hybrid_off))
    pairs_off = [(rules_off[k]["recall"], hybrid_off[k]["recall"]) for k in cases_off]
    w2, p2 = wilcoxon_signed(pairs_off)
    ra2 = [hybrid_off[k] for k in cases_off]
    rb2 = [rules_off[k] for k in cases_off]
    r_pt2, r_lo2, r_hi2 = bootstrap_ci(ra2, rb2, "recall")
    print("\nhybrid vs rules MCQ-off (operator-free recall lift):")
    print(f"  pooled recall: hybrid {_pooled(ra2,'recall'):.3f} vs rules {_pooled(rb2,'recall'):.3f}; "
          f"Wilcoxon W={w2:.0f} p={p2:.3f}; diff CI95 [{r_lo2:+.3f}, {r_hi2:+.3f}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
