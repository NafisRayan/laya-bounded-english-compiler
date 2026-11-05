"""Generate every paper figure from the committed measurement rows.

One command, no credentials, deterministic: every figure in the paper
regenerates from the JSONL evidence in tests/experiments/results/ (the
``every number regenerates'' claim extended to figures). Output: vector
PDF + 300 dpi PNG into the submission figures directory.

Usage:
    python -m tests.experiments.make_figures [--out ../submission/figures]

Figures:
  fig_tradeoff   precision/recall scatter, bubble = omissions (5.1, golden 35)
  fig_ablation   pooled recall/precision, 10 mechanism x MCQ configs (5.2)
  fig_mcq        MCQ burden vs recall curve (5.2)
  fig_reliability 10-bin reliability diagram + ECE (5.3)
  fig_sweep      auto-accept threshold sweep, shipped 0.75 marked (5.3)
  fig_e2e        deployment battery per-session latencies (5.4)
  fig_roles      LLM-annotator sensitivity runs, roles agreement (4.1)
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

RESULTS = Path(__file__).parent / "results"
ANNOTATION = Path(__file__).parent.parent / "annotation"
HERE = Path(__file__).parent

plt.rcParams.update({
    "font.size": 8.5, "axes.titlesize": 9.5, "axes.labelsize": 8.5,
    "legend.fontsize": 7.5, "xtick.labelsize": 7.5, "ytick.labelsize": 7.5,
    "axes.spines.top": False, "axes.spines.right": False,
    "figure.dpi": 300, "savefig.bbox": "tight",
    "axes.grid": True, "grid.alpha": 0.25, "grid.linewidth": 0.4,
})

C = {"blue": "#1f77b4", "orange": "#d62728", "green": "#2ca02c",
     "gray": "#7f7f7f", "purple": "#9467bd", "gold": "#b8860b"}


def rows(name: str) -> list[dict]:
    return [json.loads(l) for l in
            (RESULTS / name).read_text(encoding="utf-8").splitlines() if l.strip()]


def pooled(rs: list[dict]) -> dict:
    tp = sum(r["true_positives"] for r in rs)
    dec = sum(r["decided_features"] for r in rs)
    gold = sum(r["gold_features"] for r in rs)
    return {
        "recall": tp / gold if gold else 0.0,
        "precision": tp / dec if dec else 0.0,
        "omissions": sum(r["omissions"] for r in rs),
        "hallucinations": sum(r["hallucinations"] for r in rs),
        "mcq": sum(r["mcq_count"] for r in rs) / max(len(rs), 1),
    }


def golden_cases() -> set[str]:
    import yaml
    splits = yaml.safe_load(
        (HERE.parent / "golden" / "splits.yaml").read_text(encoding="utf-8"))
    if isinstance(splits, dict) and "golden" in splits:
        return set(splits["golden"])
ABLATION_SOURCE = "ablation_real_human.jsonl"


def fig_tradeoff(out: Path) -> None:
    gold = golden_cases()
    ab = [r for r in rows(ABLATION_SOURCE) if r["case"] in gold]
    by_cfg = defaultdict(list)
    for r in ab:
        by_cfg[(r["mechanisms"], r["mcq"])].append(r)
    systems = [
        ("Rules + MCQ (oracle)", by_cfg[("AB", True)], C["gray"]),
        ("Hybrid + MCQ (oracle)", by_cfg[("ABC", True)], C["purple"]),
        ("Rules, no MCQ", by_cfg[("AB", False)], C["blue"]),
        ("Hybrid, no MCQ", by_cfg[("ABC", False)], C["green"]),
    ]
    bl_raw = [r for r in rows("baselines_human.jsonl")
              if r["baseline"] == "llm_backend_spec" and not r.get("skipped")
              and r.get("metrics")]
    bl = [r["metrics"] for r in bl_raw
          if r["metrics"].get("precision") is not None
          and r["metrics"].get("gold_features") and r["case"] in gold]
    systems.append(("LLM->spec baseline", bl, C["orange"]))
    place = {"Rules + MCQ (oracle)": (12, -10, "left"),
             "Hybrid + MCQ (oracle)": (-12, 6, "right"),
             "Rules, no MCQ": (7, -2, "left"),
             "Hybrid, no MCQ": (7, -2, "left"),
             "LLM->spec baseline": (-7, 6, "right")}
    fig, ax = plt.subplots(figsize=(4.0, 3.3))
    for name, rs, color in systems:
        p = pooled(rs)
        ax.scatter(p["precision"], p["recall"], s=46, color=color,
                   alpha=0.9, edgecolor="black", linewidth=0.5, zorder=3,
                   clip_on=False)
        dx, dy, ha = place[name]
        arrow = name.endswith("(oracle)")
        ax.annotate(f"{name}\nomissions={p['omissions']}",
                    (p["precision"], p["recall"]), textcoords="offset points",
                    xytext=(dx, dy), fontsize=6.5, color=color, ha=ha,
                    arrowprops=(dict(arrowstyle="-", lw=0.5, color=color,
                                     shrinkA=0, shrinkB=3) if arrow else None))
    ax.set_xlabel("pooled precision")
    ax.set_ylabel("pooled recall")
    ax.set_xlim(0.55, 1.18)
    ax.set_ylim(0.60, 1.10)
    ax.set_title("Unaided trade-off vs oracle bound (golden 35)", pad=8)
    fig.savefig(out / "fig_tradeoff.pdf")
    fig.savefig(out / "fig_tradeoff.png")
    plt.close(fig)


def fig_ablation(out: Path) -> None:
    ab = rows(ABLATION_SOURCE)
    by_cfg = defaultdict(list)
    for r in ab:
        by_cfg[(r["mechanisms"], r["mcq"])].append(r)
    order = ["A", "B", "AB", "C", "ABC"]
    labels, rec, prec = [], [], []
    for m in order:
        for mcq in (True, False):
            p = pooled(by_cfg[(m, mcq)])
            labels.append(f"{m}\n{'MCQ' if mcq else '—'}")
            rec.append(p["recall"])
            prec.append(p["precision"])
    x = range(len(labels))
    fig, ax = plt.subplots(figsize=(5.2, 2.7))
    bars_r = ax.bar([i - 0.2 for i in x], rec, width=0.38, label="pooled recall",
                    color=C["blue"], alpha=0.9)
    bars_p = ax.bar([i + 0.2 for i in x], prec, width=0.38, label="pooled precision",
                    color=C["orange"], alpha=0.9)
    for bars in (bars_r, bars_p):
        for b in bars:
            h = b.get_height()
            ax.text(b.get_x() + b.get_width() / 2, h + 0.015, f"{h:.2f}",
                    ha="center", va="bottom", fontsize=5.8, rotation=90)
    ax.set_xticks(list(x))
    ax.set_xticklabels([l.replace("\nMCQ", " on").replace("\n—", " off")
                        for l in labels])
    ax.set_ylim(0, 1.34)
    ax.set_ylabel("score")
    ax.set_title("Mechanism x MCQ ablation (real ckpt, cleaned human gold)",
                 pad=22)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, 1.10), ncol=2,
              frameon=False)
    fig.savefig(out / "fig_ablation.pdf")
    fig.savefig(out / "fig_ablation.png")
    plt.close(fig)


def fig_mcq(out: Path) -> None:
    ab = rows(ABLATION_SOURCE)
    by_cfg = defaultdict(list)
    for r in ab:
        by_cfg[(r["mechanisms"], r["mcq"])].append(r)
    fig, ax = plt.subplots(figsize=(3.4, 2.8))
    pts = []
    for (m, mcq), rs in by_cfg.items():
        if not mcq:
            p = pooled(rs)
            pts.append((p["mcq"], p["recall"], m))
    blue_off = {"A": (5, 3), "B": (6, -12), "AB": (6, 5), "C": (5, 3),
                "ABC": (5, -11)}
    for q, r_, m in sorted(pts):
        ax.scatter(q, r_, s=50, color=C["blue"], alpha=0.85, zorder=3,
                   label="no MCQ" if m == "A" else None)
        ax.annotate(m, (q, r_), textcoords="offset points",
                    xytext=blue_off.get(m, (5, 3)), fontsize=7)
    green_off = {"AB": (-36, -2), "ABC": (-14, -12)}
    for m in ("AB", "ABC"):
        p = pooled(by_cfg[(m, True)])
        ax.scatter(p["mcq"], p["recall"], s=50, color=C["green"],
                   marker="s", alpha=0.85, zorder=3,
                   label="with MCQ" if m == "AB" else None)
        ax.annotate(f"{m}", (p["mcq"], p["recall"]),
                    textcoords="offset points", xytext=green_off[m],
                    fontsize=6.5, color=C["green"])
    ax.set_xlabel("mean MCQ questions per input")
    ax.set_ylabel("pooled recall")
    ax.set_title("The price of coverage: questions vs recall")
    ax.legend(loc="lower right", frameon=False)
    fig.savefig(out / "fig_mcq.pdf")
    fig.savefig(out / "fig_mcq.png")
    plt.close(fig)


def fig_reliability(out: Path) -> None:
    pairs = rows("calibration_pairs_human.jsonl")
    conf = [p["answer_confidence"] for p in pairs]
    lab = [p["label"] for p in pairs]
    n_bins = 10
    edges = [i / n_bins for i in range(n_bins + 1)]
    import bisect
    bin_sum = [0.0] * n_bins
    bin_cnt = [0] * n_bins
    for c, l in zip(conf, lab):
        b = min(bisect.bisect_right(edges, c) - 1, n_bins - 1)
        b = max(b, 0)
        bin_sum[b] += l
        bin_cnt[b] += 1
    centers = [(edges[i] + edges[i + 1]) / 2 for i in range(n_bins)]
    acc = [bin_sum[i] / bin_cnt[i] if bin_cnt[i] else None for i in range(n_bins)]
    frac = [bin_cnt[i] / len(pairs) for i in range(n_bins)]
    ece = sum(f * abs(a - c) for f, a, c in
              zip(frac, acc, centers) if a is not None)
    fig, ax = plt.subplots(figsize=(3.2, 3.0))
    ax.plot([0, 1], [0, 1], color=C["gray"], lw=0.8, ls="--", label="perfect")
    xs = [c for c, a in zip(centers, acc) if a is not None]
    ys = [a for a in acc if a is not None]
    ws = [max(f, 0.004) * 4 for f, a in zip(frac, acc) if a is not None]
    ax.plot(xs, ys, color=C["blue"], lw=1.2, marker="o", ms=4,
            label="model", zorder=3)
    for x, y, w in zip(xs, ys, ws):
        ax.scatter([x], [y], s=w * 220, color=C["blue"], alpha=0.15, zorder=2)
    ax.set_xlabel("answer_confidence")
    ax.set_ylabel("empirical accuracy")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_title(f"Reliability diagram (n={len(pairs)} items)\nECE = {ece:.4f} (10 bins)")
    ax.legend(loc="upper left", frameon=False)
    fig.savefig(out / "fig_reliability.pdf")
    fig.savefig(out / "fig_reliability.png")
    plt.close(fig)


def fig_sweep(out: Path) -> None:
    text = (RESULTS / "calibration_summary_human.md").read_text(encoding="utf-8")
    thr, cov, acc = [], [], []
    for line in text.splitlines():
        parts = [p.strip() for p in line.strip().strip("|").split("|")]
        if len(parts) == 3 and parts[0].replace(".", "").isdigit():
            t = float(parts[0])
            c = float(parts[1].split()[0])
            a = float(parts[2].split()[0])
            thr.append(t)
            cov.append(c)
            acc.append(a)
    fig, ax = plt.subplots(figsize=(3.4, 2.8))
    ax.plot(thr, cov, color=C["blue"], marker="o", ms=3.5, lw=1.2,
            label="coverage (questions skipped)")
    ax.plot(thr, acc, color=C["orange"], marker="s", ms=3.5, lw=1.2,
            label="accuracy among auto-accepted")
    ax.axvline(0.75, color=C["gray"], lw=0.8, ls="--")
    ax.annotate("shipped 0.75", (0.755, 0.985), fontsize=7,
                color=C["gray"], ha="left")
    ax.set_xlabel("auto-accept threshold")
    ax.set_ylabel("fraction")
    ax.set_ylim(0.4, 1.02)
    ax.set_title("Auto-accept buys questions by selling correctness")
    ax.legend(loc="lower left", frameon=False)
    fig.savefig(out / "fig_sweep.pdf")
    fig.savefig(out / "fig_sweep.png")
    plt.close(fig)


def fig_e2e(out: Path) -> None:
    sessions = rows("e2e_battery.jsonl")
    fig, ax = plt.subplots(figsize=(4.6, 2.9))
    names = [f"S{s['session']}" for s in sessions]
    create = [s["create"]["seconds"] for s in sessions]
    ops = [sum(o["seconds"] for o in s["ops"]) for s in sessions]
    tear = [s["teardown"]["seconds"] for s in sessions]
    y = range(len(sessions))
    ax.barh(y, create, color=C["gray"], label="project create", height=0.62)
    ax.barh(y, ops, left=create, color=C["blue"], label="deploy ops", height=0.62)
    ax.barh(y, tear, left=[c + o for c, o in zip(create, ops)],
            color=C["gold"], label="teardown", height=0.62)
    ok = all(s["create"]["success"] and all(o["success"] for o in s["ops"])
             and s["teardown"]["success"] for s in sessions)
    ax.set_yticks(list(y))
    ax.set_yticklabels(names)
    ax.invert_yaxis()
    ax.set_xlabel("wall-clock seconds")
    n_ops = sum(len(s["ops"]) for s in sessions)
    ax.set_title(f"Deployment battery: {len(sessions)} sessions, "
                 f"{n_ops} ops, all first-attempt"
                 + (" success" if ok else ""))
    ax.legend(loc="lower right", frameon=False)
    fig.savefig(out / "fig_e2e.pdf")
    fig.savefig(out / "fig_e2e.png")
    plt.close(fig)


def _roles_agreement(run: str, gold: dict) -> tuple[float, float]:
    import yaml
    exact = presence = n = 0
    base = ANNOTATION / run
    files = {}
    for sub in ("golden", "held_out"):
        d = base / sub
        if d.is_dir():
            for f in d.glob("*.yaml"):
                data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
                files[f.stem] = list(data.get("roles") or [])
    for case, entry in gold.items():
        got = files.get(case)
        if got is None:
            continue
        n += 1
        g = list(entry.get("roles") or [])
        presence += bool(g) == bool(got)
        exact += sorted(map(str, g)) == sorted(map(str, got))
    return exact / n, presence / n


def fig_roles(out: Path) -> None:
    import yaml
    gold = yaml.safe_load(
        (ANNOTATION / "human_gold.yaml").read_text(encoding="utf-8"))
    runs = [("v1\ngeneric rule", "llm_annotator"),
            ("v2\ncapability rule", "llm_annotator_v2"),
            ("v3\nexplicit rubric", "llm_annotator_v3")]
    labels, exacts, pres = [], [], []
    for label, run in runs:
        e, p = _roles_agreement(run, gold)
        labels.append(label)
        exacts.append(e)
        pres.append(p)
    x = range(len(labels))
    fig, ax = plt.subplots(figsize=(3.4, 2.8))
    ax.bar([i - 0.19 for i in x], exacts, width=0.36, color=C["green"],
           label="exact roles-list match")
    ax.bar([i + 0.19 for i in x], pres, width=0.36, color=C["blue"],
           alpha=0.75, label="roles presence agreement")
    for i, (e, p) in enumerate(zip(exacts, pres)):
        ax.text(i - 0.19, e + 0.02, f"{e:.2f}", ha="center", fontsize=7)
        ax.text(i + 0.19, p + 0.02, f"{p:.2f}", ha="center", fontsize=7)
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels)
    ax.set_ylim(0, 1.12)
    ax.set_ylabel("agreement with author gold")
    ax.set_title("Roles are definitional, not judgmental:\nrubric moves match 0.44 -> 0.96")
    ax.legend(loc="upper left", frameon=False)
    fig.savefig(out / "fig_roles.pdf")
    fig.savefig(out / "fig_roles.png")
    plt.close(fig)


FIGURES = [fig_tradeoff, fig_ablation, fig_mcq, fig_reliability,
           fig_sweep, fig_e2e, fig_roles]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path,
                        default=Path(__file__).resolve().parents[3]
                        / "submission" / "figures")
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    for fn in FIGURES:
        fn(args.out)
        print(f"  {fn.__name__} -> {args.out / (fn.__name__.removeprefix('fig_') + '.pdf')}")
    print(f"done: {len(FIGURES)} figures -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
