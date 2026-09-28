# Paper Outline Rewrite — Design

**Status:** approved design
**Date:** 2026-09-28
**Venue decision:** Systems/SE track (ICSE/FSE). R1 leads.

## 1. Purpose

Replace `Paper Outline.md` (101-line "draft skeleton") with a research-grade outline:
claims re-scoped to what is defensible, every paper section mapped to a concrete
experiment + metric + dataset with its **current evidence state**, and an
evidence-led critical path for closing every gap. This is a documentation task —
the deliverable is the rewritten outline. No experiments are run, no code is
written, and no evidence is fabricated.

## 2. Deliverable

- **In place:** `Paper Outline.md` is rewritten in place (git history preserves
  the current skeleton). Product artifact, not an agentic doc.
- **Design doc (this file):** `docs/superpowers/specs/2026-09-28-paper-outline-design.md`.
- Technical detail comes from `Developer Spec.md` (v1.10), `initial idea.md`,
  the vendored `laya` README/BENCHMARKS, and the committed ECE calibration
  artifacts. A follow-up implementation plan will enumerate the exact
  outline content per section.

## 3. Re-scoped claim set (verbatim wording for the outline)

- **R1** — A deterministic, ontology-bounded layered compiler attains higher
  requirement fidelity with *zero silent omission* than end-to-end LLM
  generation, for NL-to-backend tasks under an explicit task vocabulary.
- **R2** — *Hybrid* structure + a small decision model (Laya, 421M
  ModernBERT-large) exceeds either mechanism alone on requirement
  interpretation, at acceptable latency/cost.
- **R3** — Closed-form ECE measurement + temperature fitting provide a
  practical, testable in-compiler calibration *gate* for the auto-accept
  decision threshold (0.75).

### Rationale for the re-scoping

- **R3 threshold fix:** the old wording ("thresholded at 0.1") conflated two
  numbers. 0.1 is the ECE *gate* (`Developer Spec.md` §3.5, DoD #11:
  ECE < 0.1 on held-out). 0.75 is the auto-accept *decision* threshold
  (`mcq/thresholds.py`: `CONFIDENCE_AUTO_ACCEPT = 0.75`).
- **R2 deflation:** "viable accuracy vs LLM-only and rules-only" is not
  defensible — the vendored Laya's own benchmarks place base checkpoints
  *below the majority-class baseline* on typed decisions (0.352/0.362 vs
  0.461), and §11 Phase-7 fine-tuning (the thing that would make Laya
  viable) has not been done. R2 becomes a **relative ablation claim**
  (hybrid > either mechanism alone), which the interpreter already supports
  (it runs exact-alias, phrase-rule, and Laya mechanisms in one pipeline).
- **R1 stays the lead claim** (SE hook: silent omission + hallucinated RLS
  is a security risk) but gains an explicit scope boundary ("under an
  explicit task vocabulary") — the ontology bounds expressiveness by design,
  so the claim must not over-reach the vocabulary.

### Honesty annotations required by the re-scope

- ECE = 0.045 is a **hand-authored synthetic fixture**, not a model
  measurement (design doc `2026-09-25-ece-calibration-design.md`: "pinned
  synthetic calibration set ... pending a real, installable Laya"). The
  outline must say so wherever the number appears.
- `calibration.json` (0.07 / 0.09, `needs_fit: false`) carries illustrative
  numbers that do not match the harness (0.045). The ledger single-sources
  the harness value and flags the reconciliation.
- R1 and the LLM/rules baselines have **zero** measurements today; the
  golden set is 11 regression cases with a mock client, not a research
  dataset.

## 4. Outline structure (claims-first backbone)

Sequence and cross-cutting artifacts for the rewritten file:

1. **Header / status** — versioned, dated, tagged "research-grade outline —
   re-scoped claims, per-section evidence state, evidence-led critical path".
   Preserve the convention of mapping each section to its source
   (`Developer Spec.md` / `initial idea.md`).
2. **Target claim set** — the three re-scoped R1–R3 verbatim, + one-line
   "what changed vs v1" note (R2 now an ablation; R3 gate-vs-threshold split).
3. **Evidence Ledger** — the core audit artifact. Table with columns:
   claim | experiment | metric(s) | dataset | status (built/pending/blocked)
   | blocking gap | repo artifact. Rows covering R1, R2, R3, and the
   secondary end-to-end evaluation.
4. **§1 Introduction** — task definition (formal I/O: NL description →
   `BackendSpec` → deployed Supabase project), failure modes (silent
   omission, hallucinated RLS as security risk), numbered contribution list
   mapped to claims. SE-track hook.
5. **§2 Related Work** — five clusters (NL→schema/code generation, program
   synthesis w/ IRs, human-in-the-loop disambiguation, calibration/selective
   prediction, text-to-SQL / backend generators incl. DbSmash). Each cluster
   flagged "citation hunt required"; scoped to the SE framing.
6. **§3 System Design** — formal problem statement + IR notation; pipeline
   diagram description; three interpreter mechanisms + merge tiers; negation
   clamping; MCQ loop; validator; calibration procedure (§3.5); fragment
   composition + deployer. Correct cross-refs: ontology = §2 (not §17);
   drop §19 duplicate reference.
7. **§4 Experimental Setup (the blocking section, now concrete)** —
   - 4.1 Task & dataset: golden set (target 30–50, today 11 golden YAML with
     `MockLayaClient`); splits (train/golden/held-out); ground-truth
     `BackendSpec` annotation; collection method decided later between
     human-written / templated / LLM-assisted.
   - 4.2 Baselines: (1) e2e LLM direct-to-SQL, (2) LLM → `BackendSpec` →
     same generator, (3) rules-only, (4) Laya-only, (5) DbSmash /
     off-the-shelf generator. All tagged **NOT BUILT**; (3)/(4) noted as
     free (mechanisms already in `pipeline.py`).
   - 4.3 Metrics: precise definitions + formulas — silent-omission rate,
     hallucinated-table rate, exact-match on `BackendSpec`, negation
     precision, merge correctness, MCQ count, time-to-spec, deployment
     success, idempotency, ECE (10-bin, equal width).
   - 4.4 Protocol: seeds, #runs, hardware, model versions, statistical test,
     primary endpoint decision hierarchy, cost + latency measurement.
8. **§5 Results (claims-first)** — 5.1 → R1 fidelity vs baselines; 5.2 → R2
   three-way ablation (+ MCQ-on/off as sub-row); 5.3 → R3 ECE before/after +
   auto-accept coverage-vs-correctness curve + threshold sweep re 0.75;
   5.4 end-to-end secondary (deployment, idempotency, time-to-spec, cost).
   **Every subsection ends with a "Current evidence state" line.**
9. **§6 Discussion** — where layered loses to LLMs (long-tail paraphrase),
   MCQ burden tradeoff, deference-to-threshold, calibration generalization
   pending real Laya.
10. **§7 Limitations & Ethics** — English-only v1; ontology bounds
    expressiveness; generated RLS as security surface (review-before-deploy);
    user-data handling in NL inputs.
11. **§8 Conclusion** — recap of re-scoped claims with the numbers that exist
    (ECE 0.045 synthetic; 0.45 → 0.104711 temp-fit demo) and the two
    remaining blockers (golden dataset + baselines; real-Laya calibration).
12. **Risk register** — per claim, what could kill it:
    - R1: golden-authoring bias; baseline variance; task too narrow once the
      vocabulary boundary is explicit.
    - R2: hybrid may not beat rules-only on the bounded vocabulary (base
      model is sub-majority); MCQ burden erodes the latency win.
    - R3: real held-out Laya ECE ≥ 0.1 (triggering `needs_fit`), or
      auto-accept coverage collapses at threshold 0.75.
13. **Critical path (evidence-led)** — (1) golden dataset authoring
    (bottleneck); (2) free three-mechanism ablation on existing cases;
    (3) LLM baseline backend; (4) real-Laya calibration (blocked on
    installable Laya / Phase-7 fine-tune decision); (5) write §1–§3 now;
    (6) §4–§6 after runs.
14. **Venue note** — fixed to Systems/SE (ICSE/FSE); Related Work scoped
    accordingly; one-line note that calibration work could spin to an
    ML-track artifact (D&B) later.

## 5. Fact-fix checklist (folded into the outline)

- [x] R3 split: ECE gate 0.1 vs auto-accept threshold 0.75.
- [ ] Correct `§17 (ontology)` cross-ref → `§2`.
- [ ] Drop `§19` (duplicate Contacts) from any reference list.
- [ ] `calibration.json` illustrative 0.07/0.09 reconciled in the ledger
      against the harness value (0.045 synthetic).
- [ ] Laya checkpoint pinned `english` (421M ModernBERT-large); note the
      project forbids `laya-typed-decisions` (DoD #22).
- [ ] ECE gate tests: `test_ece_on_shipped_answer_confidence_is_acceptable`
      (0.045 < 0.1) and `test_fit_temperature_improves_miscalibrated_set`
      (0.45 → 0.1047) as the committed R3 evidence.

## 6. Success criteria

- Outline is self-consistent (no internal contradictions like the old
  0.1/0.75 conflation).
- Every section states its evidence state; nothing claims measured
  results that do not exist.
- All repo facts used are verified (numbers, cross-refs, artifact paths).
- Section content is specific enough that the implementation plan can
  write each file section without further research.

## 7. Out of scope

- Writing paper prose, abstracts, or LaTeX.
- Building the golden dataset, running baselines, or installing real Laya.
- Selecting the final bibliography (only cluster scoping + flagging).

## 8. Procedure notes

Follows the superpowers workflow: design (this file) → self-review →
user review → `writing-plans` → single-task implementation (rewrite the
outline) → self-review of the outline → optional whole-implementation
review → commit `Paper Outline.md`.