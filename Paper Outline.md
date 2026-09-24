# Research Paper Outline

Status: draft skeleton. Maps each paper section to its source in `Developer Spec.md`
/ `initial idea.md`, and names the experiment that must exist before that section
can be written.

Target claim set:
- **R1** — A deterministic, ontology-bounded layered compiler achieves higher
  requirement-fidelity with zero silent omission vs. end-to-end LLM generation.
- **R2** — A small calibrated decision model (421M) + targeted MCQ clarification
  reaches viable accuracy/latency/cost vs. LLM-only and rules-only baselines.
- **R3** — ECE-calibrated confidence (thresholded at 0.1) enables safe auto-accept
  of high-confidence decisions without harming spec correctness.

---

## 1. Introduction
- **Source:** `initial idea.md` §alternatives + workflow paragraph; spec §1.
- **Content:** problem (NL → deployable backend), why generative approaches fail
  (nondeterminism, hallucinated RLS, silent omission), one-paragraph contribution
  list (layered compiler, formal IR, MCQ orchestration, calibration).
- **Gap:** need a crisp task definition (input/output formalized) and 3–4 numbered
  contributions. ~1 page.

## 2. Related Work
- **Source:** none exists. Only informal mentions (DbSmash, Supabase generators,
  RLCD/Laya training) scattered in `initial idea.md`.
- **Content:** (a) NL→code/schema generation, (b) program synthesis with IRs,
  (c) human-in-the-loop disambiguation, (d) model calibration / selective
  prediction, (e) text-to-SQL.
- **Gap:** full survey + citations. ~1.5 pages.

## 3. System Design (Methodology)
- **Source:** spec §2 (architecture), §3 (interpreter), §4 (MCQ), §5 (spec/IR),
  §6 (validator), §7 (generator), §8 (deployer), §9 (remediation), §17 (ontology).
- **Content:** pipeline diagram, IR schema, derivation rules, merge tiers
  (v1.5 fix), negation clamping, Laya client (pinned `english`, envelope),
  calibration procedure (§3.5), fragment composition.
- **Gap:** mostly written. Needs a formal problem statement subsection and
  notation for the IR. ~4 pages.

## 4. Experimental Setup
- **Gap: entirely missing. This is the blocking section.**
- **4.1 Dataset / golden set** — spec mentions "30–50 inputs" for calibration and
  fixtures under `tests/fixtures`. Must define: how NL descriptions are collected
  (human-written? templated? LLM-assisted?), size, train/golden/held-out splits,
  distribution across domains, annotation of ground-truth `BackendSpec`.
- **4.2 Baselines** — rejected only qualitatively today; must run:
  1. End-to-end LLM (GPT-4o / Claude) direct-to-SQL.
  2. End-to-end LLM → `BackendSpec` → same generator (isolates IR benefit).
  3. Rules-only (exact maps + phrase rules, no Laya).
  4. Laya-only (no rules).
  5. Commercial/off-the-shelf: DbSmash / Supabase schema generators.
- **4.3 Metrics** — already defined in spec §10.4: capability detection,
  ambiguity detection, negation precision, merge correctness, derivation
  correctness, final-spec correctness, MCQ count, time-to-spec, deployment
  success, idempotency, ECE. Each needs a precise definition + formula.
- **4.4 Protocol** — seeds, #runs, hardware, model versions, statistical test.

## 5. Results
- **Gap: entirely missing. Depends on §4 + building the system.**
- **5.1 Spec fidelity vs. baselines** → R1 (silent-omission rate, hallucinated-
  table rate, exact-match on `BackendSpec`).
- **5.2 Ablations** → R2: rules+Laya vs. rules-only vs. Laya-only; MCQ-on vs.
  MCQ-off; merge-tier with/without v1.5 negated-tier fix; ontology size sweep.
- **5.3 Calibration & selective prediction** → R3: ECE before/after, auto-accept
  coverage vs. correctness curve, effect of threshold 0.75.
- **5.4 End-to-end** — deployment success, idempotency, time-to-spec, MCQ burden,
  cost/latency vs. LLM baseline.

## 6. Discussion
- **Source:** spec §3.6 coverage check, DoD #6/#11, limitations notes (negation
  heuristic boundaries, single-checkpoint calibration).
- **Content:** where the layered design loses to LLMs (long-tail paraphrase),
  MCQ burden tradeoff, calibration generalization across checkpoints/languages.

## 7. Limitations & Ethics
- **Gap: missing.** English-only v1; ontology bounds expressiveness (unsupported
  requirements flagged, not built); generated RLS is a security surface — note
  review-before-deploy; user-data handling in NL descriptions.

## 8. Conclusion
- Short recap of R1–R3 with the actual numbers.

---

## Critical path (order of work)

1. **Build Phase 1–3** (ontology, interpreter, MCQ) — spec §17/§3/§4. Blocks everything.
2. **Author the golden dataset** — decide collection method, N, splits, annotation.
   Start in parallel with build; this is the most likely bottleneck.
3. **Run baselines** (LLM end-to-end, rules-only) on the same dataset — can start
   before full system is done.
4. **Run ablations + calibration study** once interpreter works.
5. **Write §1, §2, §3** while experiments run (source material exists today).
6. **Write §4–§6** once results land.

## Venue fit
- Systems/SE track (ICSE/FSE) — leads with deterministic compilation + IR.
- ML/HCI track (NeurIPS D&B / CHI) — leads with calibration + human-in-loop MCQ.
  Decide venue before writing §2 (related work differs sharply).
