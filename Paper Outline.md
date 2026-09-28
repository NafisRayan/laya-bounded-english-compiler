# Research Paper Outline

Status: research-grade outline (v2, 2026-09-28). Re-scoped claim set and a
per-section evidence ledger based on a repository audit (design:
`docs/superpowers/specs/2026-09-28-paper-outline-design.md`). Venue: Systems/SE
(ICSE/FSE). Sections name their source in `Developer Spec.md` /
`initial idea.md`, their concrete experiment, and their **current evidence
state**; sections that are not yet measured say so.

Target claim set (re-scoped 2026-09-28):

- **R1** — A deterministic, ontology-bounded layered compiler attains higher
  requirement fidelity with *zero silent omission* than end-to-end LLM
  generation, for NL-to-backend tasks under an explicit task vocabulary.
- **R2** — *Hybrid* structure + a small decision model (Laya, 421M
  ModernBERT-large) exceeds either mechanism alone on requirement
  interpretation, at acceptable latency/cost.
- **R3** — Closed-form ECE measurement + temperature fitting provide a
  practical, testable in-compiler calibration *gate* for the auto-accept
  decision threshold (0.75).

*What changed vs v1:* R2 dropped "viable accuracy vs LLM-only and rules-only"
(untenable — the vendor's own benchmarks place the *base* `english` checkpoint
(0.361/0.362) and `laya-multilingual` (0.352) below the majority-class baseline
on typed-decision tasks (0.461, `laya/BENCHMARKS.md`; 0.362 is the vendor prose
figure, the table row reads 0.361), and Phase-7 fine-tuning has not run) and is
now a relative ablation claim. R3 no longer says "thresholded at 0.1": 0.1 is
the ECE *gate* (`Developer Spec.md` §3.5, DoD #11) and 0.75 is the auto-accept
*decision* threshold (`compiler/mcq/thresholds.py`). R1 is scoped to an explicit
task vocabulary because the ontology bounds expressiveness by construction.

---

## Evidence ledger

Claim → experiment → metric → dataset → status → blocking gap → repo artifact.
"Built" means the harness/evidence exists; it does not mean a model measurement.
Repo paths are relative to `backend-compiler/`; vendored `laya/` lives outside
the repo, at `../../laya/`.

| Claim | Experiment (§) | Metric(s) | Dataset | Status | Blocking gap | Repo artifact |
|---|---|---|---|---|---|---|
| R1 | Fidelity vs baselines (§5.1) | Silent-omission rate; hallucinated-table rate; exact-match on `BackendSpec` | Golden set (target 30–50, spec §10.2) | **Pending** | Dataset authoring; baseline harness | `tests/golden/cases/` (11 cases, mock client) |
| R2 | Three-mechanism ablation (§5.2) | Interpretation accuracy; MCQ count; latency/cost | Golden set | **Pending** (mechanics exist) | Run harness; fine-grained labels | `compiler/interpreter/pipeline.py` (mech. A/B/C) |
| R3 | Calibration gate (§5.3) | ECE (10-bin); auto-accept coverage vs. correctness; threshold sweep | Pinned fixtures (synthetic) | **Built (synthetic) — gate not passed** / blocked for real | Installable real Laya; held-out `(answer_confidence, label)` pairs | `tests/integration/test_ece_measurement.py`; `tests/fixtures/golden_calibration/` |
| E2E | End-to-end secondary (§5.4) | Deployment success; idempotency; time-to-spec; cost | Golden set | **Blocked** | §7 generator + §8 deployer not built (§7 = Phase 2 composition, §8 = Phase 3 deployer) | `compiler/` (no `generator/` or `deployer/` package) |

**Calibration honesty note:** the ledger's R3 rows rest on a hand-authored
pinned fixture whose per-bin accuracies were *chosen* to land under the 0.1 gate
(`docs/superpowers/specs/2026-09-25-ece-calibration-design.md`). ECE 0.045 is a
unit test of the ECE formula and temperature fitter, **not** a measurement of the
model's calibration. The committed `ontology/versions/v1/calibration.json`
(0.07 / 0.09, `needs_fit: false`) carries illustrative placeholder values that do
not match the harness (0.045); reconcile when the real model is measurable.

---

## 1. Introduction
- **Source:** `initial idea.md` §alternatives + workflow; spec §0–§1.
- **Content:** Task definition — input is a 1–500 word natural-language
  description of a backend; output is a `BackendSpec` (typed IR over a fixed
  ontology) compiled into a working Supabase project (DDL, RLS policies, auth
  config, storage buckets, edge functions), via fragment composition and the
  Management API. Why generative approaches fail here: end-to-end LLM
  generation is nondeterministic (same prompt → different schemas), can
  hallucinate tables/policies that do not exist, is hard to audit or
  reproduce, and silent omission is the worst failure mode — the requirement
  never enters the spec (`initial idea.md:9`). A malformed generated RLS
  policy is a security risk, not just a bug (`initial idea.md:5`).
- **Contributions (numbered):** (1) a deterministic, ontology-bounded layered
  compiler with a never-silently-omit invariant (R1); (2) hybrid
  exact-alias + phrase-rule + small-model interpretation gated by targeted
  MCQ clarification (R2); (3) a closed-form ECE measurement + temperature-fit
  procedure as an in-compiler calibration gate for auto-accept (R3); (4) an
  evaluation protocol and baselines for NL-to-backend fidelity (§4).
- **Current evidence state:** task and metrics are definable today; no
  measurements exist.

## 2. Related Work
- **Source:** not yet surveyed — five clusters, all flagged
  **citation hunt required**:
  1. NL → schema / backend generation and text-to-SQL.
  2. Program synthesis with intermediate representations (IR tradeoffs).
  3. Human-in-the-loop disambiguation (clarifying-question systems).
  4. Model calibration and selective prediction (ECE, temperature scaling,
     coverage-aware deferral).
  5. Backend/schema generator tooling (DbSmash; Supabase ecosystem
     generators — informal in-repo mentions only in `initial idea.md`).
- **Current evidence state:** empty. Venue (Systems/SE) decides which
  clusters are central; target §2 length ~1.5 pages; blocks nothing
  experimental.

## 3. System Design (Methodology)
- **Source:** spec §2 (ontology, NOT §17 — a cross-ref bug in the old draft,
  fixed), §3 (interpreter + confidence + calibration), §4 (MCQ), §5 (spec/IR),
  §6 (validator), §7 (generator), §8 (deployer), §9 (remediation). Duplicate
  §19 (Contacts) is dropped.
- **Content:** Formal problem statement (task in §1) plus IR notation —
  `BackendSpec` carries features, parameters, entities, roles, storage
  buckets, edge functions, and RLS policy fragments.
  Pipeline (workflow, `initial idea.md:19`; the spec §1.1 canonical diagram
  lists the same stages with derivation split out): `interpret → classify →
  clarify → specify → validate → approve → compile → deploy → remediate →
  retry`.
  Interpreter mechanisms (spec §3.1): error **A** exact alias matches; error
  **B** phrase rules with character-span negation clamped at sentence
  boundaries; error **C** Laya typed-decision classification against the fixed
  ontology — merged by a tiered conflict resolver (`merge`; v1.5 negated-tier
  fix). Candidate confidence comes from Laya's `answer_confidence`, the
  ECE-calibrated quantity (`pipeline.py`), never the bare raw value. Gates
  (§3.4): ≥ 0.75 auto-accept, 0.35–0.75 ambiguous, 0.20–0.35 weak, < 0.20
  unsupported. MCQ loop (§4) surfaces the *residual* ambiguity — negation
  conflicts, contradictions, undecided features/params, and unparsed
  sentences — ordered by a dependency graph, capped at `max_mcqs`.
  Unparsed text becomes `clarify_unparsed`, the structural mechanism that
  prevents silent omission. Spec completion by derivation
  (`spec/derive.py`); typed validation (`spec/validator.py`); fragment
  composer assembles pre-tested SQL/Jinja2 via topological sort; deployer
  creates the Supabase project once and reuses it across the bounded
  remediation loop (max 3). Calibration procedure (§3.5): consume
  `answer_confidence`; fit temperature only if measured ECE ≥ 0.1 on the
  golden set; `calibrated = sigmoid(logit(clip(p, 1e-6, 1−1e-6)) / T)` with
  re-calibration triggers enumerated.
- **Current evidence state:** system implemented up to validation
  (`backend-compiler/compiler/`); §7 generator and §8 deployer are not built.
  Confidence thresholds and calibration module are implemented and tested.

## 4. Experimental Setup
- **Gap status:** this was the missing blocking section; protocol now concrete.
- **4.1 Task & dataset.** Formal task (spec §0): NL description → `BackendSpec`
  → deployed project. Golden set target **30–50 hand-crafted inputs** (spec
  §10.2); today there are **11 golden YAML cases** (`tests/golden/cases/`)
  using an in-repo `MockLayaClient` persona (`default | high | none`) — a
  regression corpus, not a research dataset. Need to decide: collection method
  (human-written / templated / LLM-assisted), train / golden / held-out
  splits, domain distribution, and annotation of ground-truth `BackendSpec`
  per input.
- **4.2 Baselines** (all **NOT BUILT** today):
  1. End-to-end LLM (e.g. GPT-4o / Claude) direct-to-SQL.
  2. End-to-end LLM → `BackendSpec` → same fragment composer (isolates the IR).
  3. Rules-only: mechanisms A + B, no Laya.
  4. Laya-only: mechanism C, no rules.
  5. DbSmash / off-the-shelf Supabase generator.
  Baselines 3 and 4 are essentially free — all three mechanisms already run in
  one pipeline (`pipeline.py`), so the ablation is pure run-harness work.
  Baseline 2 requires only the LLM→`BackendSpec` adapter; baselines 1 and 5
  need sandboxed Supabase projects plus cost.
- **4.3 Metrics** (precise definitions; formulas where cheap):
  - Silent-omission rate = requirements in the NL input absent from the final
    `BackendSpec` ÷ total requirements (golden-annotated).
  - Hallucinated-table rate = schema objects/features in the spec with no
    supporting requirement ÷ objects in the spec.
  - Exact-match = final `BackendSpec` equality with ground truth on the full
    representation.
  - Negation precision = correct negations ÷ negations detected.
  - Merge correctness = conflict-resolution outputs respect the v1.5 tier
    semantics (`exact` > `phrase`/`phrase_negated`) per spec §10.4, DoD #18.
  - MCQ count (DoD: ≤ 10 complex, ≤ 3 simple); time-to-spec; first-attempt
    deployment success (DoD ≥ 80%, ≥ 95% with remediation); idempotency
    (re-run → identical spec, DoD 100%); ECE (10 equal-width bins, Σ over
    non-empty bins of bin share × |mean confidence − mean accuracy|,
    `compiler/interpreter/calibration.py`).
- **4.4 Protocol.** Seeds (≥ 3 for stochastic baselines), #runs, hardware,
  pinned model versions (LLM checkpoint ids; Laya `english`, 421M
  ModernBERT-large, context 512). Statistical test: McNemar on paired
  per-requirement omission; Wilcoxon signed-rank for continuous metrics.
  Primary endpoint by claim: silent-omission rate (R1); hybrid-vs-single
  delta (R2); ECE < 0.1 **and** auto-accept coverage-vs-correctness (R3).
  Cost and latency (per-answer ms, §4.4 vs LLM per-request) measured on the
  same golden set. `laya-typed-decisions` is unavailable by decision
  (DoD #22 — wrong question-id schema).

## 5. Results
- **5.1 → R1. Spec fidelity vs. baselines.** Silent-omission rate,
  hallucinated-table rate, exact-match, per baseline.
  **Current evidence state:** none — baselines not built; golden set is the 11
  regression cases only.
- **5.2 → R2. Ablations.** Rules + Laya vs. rules-only vs. Laya-only;
  MCQ-on vs. MCQ-off; merge-tier with/without the v1.5 negated-tier fix;
  ontology size sweep.
  **Current evidence state:** mechanisms exist and are unit/golden-tested
  (with a mock client); no comparative runs on a research dataset.
- **5.3 → R3. Calibration & auto-accept gate.** ECE before/after temperature
  fit; auto-accept coverage-vs-correctness curve; threshold sweep anchored on
  0.75 (the shipped `CONFIDENCE_AUTO_ACCEPT`).
  **Current evidence state:** synthetic only, and it does not yet pass the
  gate. ECE 0.045 < 0.1 (`test_ece_on_shipped_answer_confidence_is_acceptable`,
  40-entry fixture) passes, but the temperature-fit demo
  (`test_fit_temperature_improves_miscalibrated_set`) stops at 0.45 → 0.1047
  (20-entry set) — still above the 0.1 gate, with best T = 10.0 sitting at the
  grid-search bound (`compiler/interpreter/calibration.py`), not a converged
  optimum; the vendor further clamps persisted temperatures to [0.5, 5.0], so
  T = 10.0 is not enforceable. The demo therefore shows the fit *improves* a
  deliberately miscalibrated set, not that it passes the gate on this fixture.
  Replace with measured `(answer_confidence, label)` pairs in the same JSON
  schema (design doc `2026-09-25-ece-calibration-design.md`).
- **5.4 End-to-end (secondary).** Deployment success, idempotency, time-to-spec,
  MCQ burden, cost/latency vs. LLM baseline.
  **Current evidence state:** blocked — the §7 generator (Phase 2) and §8
  deployer (Phase 3) are not built.

## 6. Discussion
- **Source:** spec §3.6 coverage check, DoD #6/#11; limitations of negation
  heuristic and single-checkpoint assumptions.
- **Content:** Where the layered design loses to LLMs (long-tail paraphrase
  outside the ontology vocabulary). MCQ burden vs. correctness tradeoff.
  Deference semantics — auto-accept at 0.75 vs. always-ask; what the
  coverage-vs-correctness curve must show. Calibration generalization across
  checkpoints/languages — vendor README reports a per-language macro ECE
  spread for the English checkpoint, and the same vendor data shows a
  temperature refit moving shipped ECE 0.466 → 0.081 (`laya/README.md`): the
  mechanism of R3 demonstrated on a real model, pending in-repo reproduction.

## 7. Limitations & Ethics
- English-only v1; ontology bounds expressiveness — unsupported requirements
  are *flagged*, not built. Generated RLS policies are a security surface:
  every output runs through the validator plus a human review-before-deploy
  gate (`approve`). User-supplied NL descriptions may contain sensitive data —
  state handling and no-retention defaults. The base `english` checkpoint's
  weak standalone typed-decision accuracy (vendor benchmarks) is disclosed and
  bounded by the hybrid design; claims are scoped accordingly.

## 8. Conclusion
- Recap R1–R3 in re-scoped form. Numbers that exist today: ECE 0.045
  (synthetic fixture) and the temperature-fit demo 0.45 → 0.1047 — the latter
  still above the 0.1 gate, so R3 is not yet demonstrated; the validation/MCQ
  system. Three blockers remain before results are claimable: (i) golden
  dataset + baseline harness, (ii) real-Laya calibration pairs, (iii) the §7
  generator (Phase 2) and §8 deployer (Phase 3) — no end-to-end numbers exist.

---

## Risk register (what could kill each claim)
- **R1:** golden-set authoring bias (annotations encode the compiler's own
  conventions); baseline variance at N=30–50; task too narrow once bounded by
  the explicit vocabulary.
- **R2:** on the bounded vocabulary, rules-only may already carry the load —
  hybrid might not beat it, given the base checkpoint is below the
  majority-class baseline on typed decisions (vendor benchmark); MCQ burden
  could erode the latency win.
- **R3:** real held-out Laya ECE on the pinned `english` checkpoint is
  *expected* to be ≥ 0.1 — the vendor measures 0.175 (typed-decisions,
  `laya/BENCHMARKS.md`) and ~0.466 mean ECE as shipped — so `needs_fit` is
  the expected path, not a tail risk. Open questions: can the in-repo fit
  (temperatures clamped to [0.5, 5.0]) reproduce the vendor's refit
  0.466 → 0.081 (`laya/README.md`)? The fit routine currently has no
  production path; auto-accept coverage may collapse at threshold 0.75.
- **E2E:** no deployment evidence until the §7 generator (Phase 2) and §8
  deployer (Phase 3) ship — deployment success, idempotency, and time-to-spec
  all block on them, so the paper must not imply end-to-end results.

## Critical path (evidence-led order)
1. **Author the golden dataset** (30–50) — collection method, splits,
   ground-truth annotation. The most likely bottleneck; start immediately.
2. **Run the free three-mechanism ablation** (rules/Laya/hybrid) plus MCQ-on/off
   on the existing 11 golden cases — mechanics exist today.
3. **Build the baseline harness** (LLM e2e, LLM→`BackendSpec`, DbSmash) on the
   golden set — begins before the full system ships.
4. **Real-Laya calibration** (blocked until Laya is installable or Phase-7
   fine-tuning decision is made); regenerate the fixture in the same schema.
   This step owns R3's primary endpoint: ECE < 0.1 **and** the auto-accept
   coverage-vs-correctness curve, plus the 0.75 threshold sweep.
5. **Write §1–§3 now** — source material exists (spec §1–§6, `initial idea.md`).
6. **Write §4–§6 once runs land**; keep the ledger in sync as statuses flip
   from Pending → Done.

## Venue fit
- Systems/SE (ICSE/FSE) — leads with deterministic compilation, the typed IR,
  and R1; this outline targets that track.
- The calibration work (§5.3) can later spin into an ML-track artifact
  (NeurIPS D&B / CHI) without restructuring the main line.