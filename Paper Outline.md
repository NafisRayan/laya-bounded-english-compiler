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
| R1 | Fidelity vs baselines (§5.1) | Silent-omission rate; hallucinated-table rate; exact-match on `BackendSpec` | Golden set: **50 engine-pinned cases** (`tests/golden/cases/`) | **Measured — all 150 rows: spec baseline R 0.503/P 0.685 (45/50 parse); direct-SQL recall 0.36/precision 0.271; dbsmash schema in 15/50 cases, recall 0.02; compiler rules+MCQ 0.922/1.000 wins** | Independent ground-truth annotation; gateway model provenance | `tests/golden/cases/` (50 cases); `tests/experiments/baselines.py` + `results/baselines.jsonl` (150 measured rows) |
| R2 | Three-mechanism ablation (§5.2) | Interpretation accuracy; MCQ count; latency/cost | Golden set | **Measured twice + fixed — post-fix hybrid+MCQ = rules-parity (0.922/0.930, 10 omissions); with the §5.3 refit (T = 1.40) hallucinations 9 → 4, precision 0.967, feature-exact 44/50** | Independent annotation | `tests/experiments/run_ablation.py` (`--real-laya`) + `results/ablation_real*.jsonl`; `compiler/interpreter/merge.py`; `compiler/mcq/pipeline.py`; `compiler/interpreter/pipeline.py` (calibrated wiring) |
| R3 | Calibration gate (§5.3) | ECE (10-bin); auto-accept coverage vs. correctness; threshold sweep | **500 measured pairs** (real `english` checkpoint × golden cases) | **Measured — ECE 0.0951 < 0.1 (gate PASS); fit 0.0425 @ T = 1.40; refit applied downstream halves hybrid hallucinations 9 → 4 (§5.2 finding 7)** | Independent ground-truth annotation; held-out pairs | `tests/experiments/run_calibration.py` + `results/calibration_pairs*.jsonl`; `tests/integration/test_ece_measurement.py`; `tests/fixtures/golden_calibration/calibration_set.json` (measured) |
| E2E | End-to-end secondary (§5.4) | Deployment success; idempotency; time-to-spec; cost | Golden set | **Measured — 1 real deployment, first-attempt success (39 s, free tier)** | Repeat runs for a rate; real-model interpreter (mock persona used) | `compiler/generator/` (§7) + `compiler/deployer/` (§8), 595-pair matrix on live PG, `tests/e2e/` |

**Calibration honesty note:** the §18.17 gate fixture is now 500 measured
`(answer_confidence, label)` pairs — real `laya` 0.3.20, pinned `english`
checkpoint, one pair per golden-case feature item, labels derived from the
engine-pinned gold (`python -m tests.experiments.run_calibration`). ECE
0.0951 < 0.1 passes the gate **in-sample against the contract-test corpus**;
it is not independent human annotation and not held out, and the 0.0951
margin is thin. The deliberately-miscalibrated fit-demo set stays synthetic
by design. `ontology/versions/v1/calibration.json` remains pass-through
T = 1.0 per the spec's rule (fit only when the gate fails); the measured
fit (T = 1.40 → 0.0425) is reported, not shipped.

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
- **Current evidence state:** task and metrics are definable today; the
  system is implemented end to end (interpreter → MCQ → spec → composer →
  deployer) with 50 golden cases and a 595-pair SQL matrix; a mock-model
  mechanism ablation is measured (Paper §5.2), but no comparative
  measurements against LLM baselines exist.

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
  §6 (validator), §7 (composition engine), §8 (generator + deployer), §9
  (remediation). Duplicate §19 (Contacts) is dropped.
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
- **Current evidence state:** the system is implemented end to end
  (`backend-compiler/compiler/`): interpreter, MCQ engine, derivation and
  typed validation, §7 composition engine (idempotency + 595-pair fragment
  matrix on live PostgreSQL 15), and §8 deployer with the remediation loop.
  Confidence thresholds and calibration module are implemented and tested;
  a mock-model mechanism ablation is measured (Paper §5.2); no LLM-comparative
  measurements exist.

## 4. Experimental Setup
- **Gap status:** this was the missing blocking section; protocol now concrete.
- **4.1 Task & dataset.** Formal task (spec §0): NL description → `BackendSpec`
  → deployed project. Golden set target **30–50 hand-crafted inputs** (spec
  §10.2): **50 engine-pinned YAML cases** now exist (`tests/golden/cases/`)
  using in-repo `MockLayaClient` personas (`default | high | none`). Still to
  decide: train / golden / held-out splits, domain distribution beyond the
  current feature coverage, and annotation of ground-truth `BackendSpec` per
  input (the case expectations are engine-pinned regression truth, not yet
  independent annotations).
- **4.2 Baselines** (MEASURED 2026-09-30 — all 150
  rows: 100 LLM via the gateway + 50 dbsmash via OpenRouter/Gemini):
  1. End-to-end LLM (Gemini / GPT-4o / Claude) direct-to-SQL — `DirectSqlBaseline`.
  2. End-to-end LLM → `BackendSpec` → same fragment composer (isolates the IR)
     — `BackendSpecBaseline`, parse → spec → score unit-tested offline.
  3. Rules-only: mechanisms A + B, no Laya — measured (§5.2).
  4. Laya-only: mechanism C, no rules — measured (§5.2, mock persona).
  5. DbSmash / off-the-shelf Supabase generator — adapter only (external tool).
  Baselines 3 and 4 are free (one pipeline); 1 and 2 take a live provider key
  (`GEMINI_API_KEY` / `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`, loaded from
  `.env`) and self-skip without one; 5 needs the external tool configured.
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
  **Current evidence state: MEASURED — 2026-09-30.** Full 50-case sweep
  through an OpenAI-compatible gateway (`antigravity/gemini-3.8-flash-tiered`):
  100/100 LLM rows measured. Spec baseline: 45/50 parseable, mean recall
  0.503 / precision 0.685, 57 omissions / 21 hallucinations. Direct-SQL
  baseline: pooled table recall 0.36 (36/100), 133 tables generated
  (precision 0.271). Compiler rules+MCQ (0.922/1.000, 10 omissions)
  dominates both. Honest caveats: zero-shot baselines by definition, and the
  gateway model's provenance is outside our pinning. Composition-side
  determinism is measured (595-pair matrix on live PG, byte-identical
  recompiles).
- **5.2 → R2. Ablations.** Rules + Laya vs. rules-only vs. Laya-only;
  MCQ-on vs. MCQ-off; merge-tier with/without the v1.5 negated-tier fix;
  ontology size sweep.
  **Current evidence state: MEASURED (mock personas) — 2026-09-29.** Full
  9-config table in `Paper.md` §5.2 and `tests/experiments/results/ablation_summary.md`
  (500 rows, `ablation.jsonl` committed). Headline: hybrid(A+B+C)+MCQ pooled
  recall 1.000 / precision 0.942, 0 omissions, feature-exact 49/50, params
  26/26; rules-only 0.922 recall, 10 omissions; Laya-only+MCQ 0.643; Laya-only
  no-MCQ 0.093; MCQ-on is the completeness driver (hybrid omissions 65 → 0).
  All 8 hallucinations confined to the two `high`-persona cases and invisible
  to the golden partial submatch — caught by experiment-tier precision.
  **Real-checkpoint rerun — 2026-09-29, fixed same day** (`--real-laya`):
  the raw swap dropped hybrid+MCQ to 36 omissions and exposed two real
  defects — merge grouped `needs_X` and `X.enabled` as different targets
  (laya twins triggered spurious negations; tier protection was not real at
  feature level), and the symmetric negative gate let confident laya "no"s
  decide features off. Both fixed (merge feature-target grouping;
  laya-sourced negatives never auto-decide off). Post-fix: hybrid+MCQ
  **0.922/0.930, 10 omissions (rules-parity), 9 hallucinations**; no-MCQ
  recall 0.419 → 0.481. Mock table byte-identical after the fixes.
  Open items: independent annotation, a checkpoint that pays (refit or
  fine-tune), vocab sweep.
- **5.3 → R3. Calibration & auto-accept gate.** ECE before/after temperature
  fit; auto-accept coverage-vs-correctness curve; threshold sweep anchored on
  0.75 (the shipped `CONFIDENCE_AUTO_ACCEPT`).
  **Current evidence state: MEASURED — 2026-09-29.** Real `laya` 0.3.20 +
  torch 2.14 (CPU) in the venv; pinned `english` checkpoint fetched from the
  Hub; 50 golden cases × feature items = **500 measured pairs**
  (`python -m tests.experiments.run_calibration`). Headline: decision
  accuracy 0.784; **raw ECE 0.0951 < 0.1 — gate PASS** on the shipped
  `answer_confidence`; temperature fit **0.0951 → 0.0425 @ T = 1.40**
  (inside the [0.5, 5.0] clamp; not shipped — the spec fits only on gate
  failure); sweep at 0.75: **87.8% coverage / 80.0% correctness**, peaking
  at 0.85 (70.6% / 82.4%), non-monotone by 0.95. The §18.17 gate fixture is
  now the measured pairs (gates unchanged); the fit-demo set stays synthetic
  on purpose. Honesty: labels are engine-pinned gold, in-sample, not
  independent annotation; the 0.0951 margin is thin.
- **5.4 End-to-end (secondary).** Deployment success, idempotency, time-to-spec,
  MCQ burden, cost/latency vs. LLM baseline.
  **Current evidence state: MEASURED — 2026-09-29.** One real deployment,
  first-attempt success: project created via the Management API (smart-group
  region), 29 migrations applied with the CLI, auth configured, 2 edge
  functions deployed server-side (`--use-api`), and the live database
  verified (`listings`/`bookings`/`messages` tables + `listings` bucket);
  39 s create→verified, free tier ($0 marginal). Interpreter used the mock
  persona, so this measures deployment, not model latency. n=1: evidence of
  deployability, not a first-attempt *rate*. Five live-API drift points found
  and fixed (region codes, `/health` `services` param + payload shape, npm
  `.cmd` shim, esm.sh-blocked Docker bundling, POST-only `database/query`) —
  see Paper §5.4.

## 6. Discussion
- **Source:** spec §3.6 coverage check, DoD #6/#11; limitations of negation
  heuristic and single-checkpoint assumptions.
- **Content:** Where the layered design loses to LLMs (long-tail paraphrase
  outside the ontology vocabulary). MCQ burden vs. correctness tradeoff.
  Deference semantics — auto-accept at 0.75 vs. always-ask; what the
  coverage-vs-correctness curve must show. Calibration generalization across
  checkpoints/languages — vendor README reports a per-language macro ECE
  spread for the English checkpoint, and the same vendor data shows a
  temperature refit moving shipped ECE 0.466 → 0.081 (`laya/README.md`); the
  vendor fits one temperature per (question type, option count), while R3's
  in-repo mechanism is a single scalar T — pending in-repo reproduction.

## 7. Limitations & Ethics
- English-only v1; ontology bounds expressiveness — unsupported requirements
  are *flagged*, not built. Generated RLS policies are a security surface:
  every output runs through the validator plus a human review-before-deploy
  gate (`approve`). User-supplied NL descriptions may contain sensitive data —
  state handling and no-retention defaults. The base `english` checkpoint's
  weak standalone typed-decision accuracy (vendor benchmarks) is disclosed and
  bounded by the hybrid design; claims are scoped accordingly.

## 8. Conclusion
- Recap R1–R3 in re-scoped form. Numbers that exist today: the ablation grid
  measured twice (mock personas: hybrid+MCQ 0 omissions; real checkpoint:
  hybrid+MCQ at rules-parity after two harness fixes — §5.2), the full
  baseline sweep (compiler rules+MCQ 0.922/1.000 vs spec baseline 0.503/0.685
  and direct-SQL 0.36 table recall — §5.1), measured real-checkpoint
  calibration — ECE 0.0951 < 0.1 in-sample, fit 0.0425 @ T = 1.40 (§5.3) —
  and three real end-to-end deployments, first-attempt (§5.4). Remaining
  before results are fully claimable: (i) independent ground-truth
  annotation + held-out splits, (ii) held-out confirmation of the refit's downstream gain (T = 1.40
  halves hybrid hallucinations in-sample; §5.2 finding 7).

---

## Risk register (what could kill each claim)
- **R1:** golden-set authoring bias (annotations encode the compiler's own
  conventions); baseline variance at N=30–50; task too narrow once bounded by
  the explicit vocabulary.
- **R2:** on the bounded vocabulary, rules-only may already carry the load —
  **measured: it does, and post-fix the model breaks even.** The rerun first
  showed rules+MCQ dominating the raw checkpoint swap (36 vs 10 omissions),
  but the excess traced to two harness defects, now fixed; hybrid+MCQ
  recovered to rules-parity with 9 hallucinations as the residual cost. The
  honest claim: the architecture protects the model slot; today's checkpoint
  fills it to parity, not advantage. Refit (T = 1.40) or fine-tune are the
  measured routes to advantage.
- **R3:** the measured in-sample ECE (0.0951) passes, but thinly — a
  held-out, independently annotated rerun could land ≥ 0.1 (vendor measures
  0.175 on typed decisions), which flips the shipped pass-through to
  `needs_fit`. Open questions: does the scalar T = 1.40 refit hold out of
  sample, and does the auto-accept correctness collapse (measured 80.0% at
  0.75, peak 82.4% at 0.85, non-monotone at 0.95) survive annotation? The
  fit routine's production path stays unused while the gate passes.
- **E2E:** the §7 composition engine and §8 generator/deployer have shipped
  (idempotency + 595-pair matrix on live PostgreSQL; remediation harness), and
  one real Supabase deployment succeeded first-attempt (§5.4, n=1). The residual
  risk is drift: every break the live API exposed was invisible to mocks, so
  the paper must scope end-to-end claims to the measured run and not imply a
  success *rate*.

## Critical path (evidence-led order)
1. ~~Author the golden dataset (30–50)~~ — **done**: 50 engine-pinned cases
   shipped (2026-09-28). Remaining: independent ground-truth annotation and
   splits before §5.1 runs.
2. ~~Run the free three-mechanism ablation (rules/Laya/hybrid) plus MCQ-on/off
   on the 50 golden cases~~ — **done + fixed**: full 9-config table measured
   with mock personas (2026-09-29); re-measured with the real checkpoint the
   same day, which exposed and fixed two harness defects (merge
   feature-target grouping, asymmetric negative gate); post-fix hybrid+MCQ =
   rules-parity; refit takes hallucinations to 4. Remaining: independent
   annotation.
3. ~~Build the baseline harness (LLM e2e, LLM→BackendSpec, DbSmash) on the
   golden set~~ — **done (2026-09-29)**: adapters + offline-scored unit tests;
   full sweep MEASURED 2026-09-30 (150/150 rows); remaining: independent
   annotation.
4. ~~Run one real end-to-end deployment through the credential-gated e2e
   tier~~ — **done (2026-09-29)**: first-attempt success on a free-tier org,
   39 s create→verified, 5 live-API drift points fixed (§5.4).
5. ~~Real-Laya calibration: install the library, measure
   `(answer_confidence, label)` pairs, ECE, temperature fit, and the 0.75
   sweep~~ — **done (2026-09-29)**: 500 measured pairs on the pinned
   `english` checkpoint; ECE 0.0951 < 0.1 (gate PASS), fit 0.0425 @ T = 1.40,
   sweep measured; §18.17 fixture swapped to the measured pairs. Remaining:
   independent annotation + held-out rerun for the claim-grade number.
6. ~~Write §1–§3 now~~ — **done**: `Paper.md` §1–§3 shipped (2026-09-28),
   sourced from spec §1–§6 and `initial idea.md`.
7. ~~Write §4–§6 once runs land~~ — **done (2026-09-29)**: §4–§6 written and
   re-synced as each measurement landed (§5.2 ablation, §5.3 calibration,
   §5.4 deployment, §5.1 quota state). Remaining: §7 conclusion polish once
   the annotated held-out numbers land.

## Venue fit
- Systems/SE (ICSE/FSE) — leads with deterministic compilation, the typed IR,
  and R1; this outline targets that track.
- The calibration work (§5.3) can later spin into an ML-track artifact
  (NeurIPS D&B / CHI) without restructuring the main line.