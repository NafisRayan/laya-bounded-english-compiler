# From English to a Working Backend: A Deterministic, Ontology-Bounded Compiler for NL-to-Backend Tasks

*Draft — §1–§3 (critical-path step 5). §4–§8 are stubs pending measured runs
(see `Paper Outline.md` for the per-section plan and evidence ledger).*

---

## 1. Introduction

Building the backend of a web application — database schema, row-level
security, authentication, file storage, realtime channels, and edge functions
— is a well-bounded engineering task that is nonetheless inaccessible to many
people who can describe it precisely in a paragraph of English. This paper
studies the task of compiling that paragraph into a working Supabase project:
the input is a 1–500 word natural-language description of a backend, and the
output is a validated, typed intermediate specification (`BackendSpec`) that is
compiled into pre-tested SQL migrations, RLS policies, auth configuration,
storage buckets, and edge functions, then deployed programmatically through
the Supabase Management API and CLI.

The obvious approach — prompting a large language model to emit the schema and
policies directly — fails in ways that matter for this task. End-to-end
generation is nondeterministic: the same prompt can yield different schemas on
different runs, so the build cannot be audited or reproduced. It hallucinates
tables and policies that no requirement asked for. Most importantly, its worst
failure mode is silent: a requirement that the model simply drops never
appears in the output, and nothing marks the omission. A malformed generated
RLS policy is not a cosmetic bug but a security risk — the difference between
"owner can read their rows" and "everyone can read everyone's rows" is one
prompt drift away.

We instead treat NL-to-backend as a *compilation* problem over an explicit,
versioned task vocabulary. A fixed ontology enumerates the features,
parameters, entities, roles, and storage buckets the platform knows how to
build; the ontology bounds expressiveness by construction, and requirements
outside the vocabulary are *flagged as unsupported* rather than guessed.
Three interpretation mechanisms — exact alias matching, character-span phrase
rules with sentence-clamped negation detection, and a small (421M-parameter)
typed-decision model — propose typed decisions against the ontology; a tiered
conflict resolver merges them; a bounded multiple-choice clarification loop
surfaces exactly the residual ambiguity, including any sentence the
interpreter could not map to a capability, which is the structural mechanism
that prevents silent omission. A deterministic fragment composer then assembles
pre-tested SQL fragments via topological sort and conflict detection, and a
deployer creates the cloud project once and reuses it across a bounded
remediation loop.

This paper's contributions are:

1. **A deterministic, ontology-bounded layered compiler** for NL-to-backend
   tasks with a never-silently-omit invariant: every input sentence either
   resolves to a capability, is answered by the user through a targeted
   question, or is flagged (R1).
2. **A hybrid interpretation design** that combines exact aliases, phrase
   rules with span-limited negation handling, and a small typed-decision
   model, gated by targeted MCQ clarification — with the small model used
   strictly as a *classifier against a fixed option set*, never as a
   generator (R2).
3. **A closed-form calibration gate**: measured ECE on the model's shipped
   `answer_confidence`, with temperature fitting applied only when the gate
   (ECE ≥ 0.1) demands it, feeding the compiler's 0.75 auto-accept threshold
   (R3).
4. **An evaluation protocol** for NL-to-backend fidelity — silent-omission
   rate, hallucinated-table rate, exact-match on the typed IR, negation
   precision, MCQ burden, and deployment success — with baselines that
   isolate the IR, the rules, and the model (§4).

**Evidence state.** The system is implemented end to end
(`backend-compiler/compiler/`: interpreter, MCQ engine, spec derivation and
validation, fragment composition, deployer), with 1,100+ tests including a
595-pair fragment matrix applied against a live PostgreSQL 15 and a 50-case
golden corpus. No *comparative* measurements against baselines exist yet; §4
defines the protocol and §5 is empty by design.

## 2. Related Work

*The survey has not yet been conducted; this section fixes the five clusters
the paper must cover and what each comparison must show. Citations are
placeholders pending the hunt (outline, §2).*

**NL to schema and text-to-SQL.** A large literature maps natural language to
database schemas and queries, from early schema-mapping systems through
neural text-to-SQL [\cite:text2sql-survey]. These systems validate the premise
that constrained, schema-aware decoding outperforms free-form generation for
structured outputs, but they target query answering over an existing schema
rather than the synthesis of a complete backend — schema *plus* security
policy *plus* platform configuration — and none, to our knowledge, treat
requirement omission as a first-class metric. DbSmash and similar Supabase
generators [\cite:dbsmash, \cite:supabase-generators] are the closest tools:
LLM-based, one-shot, and non-interactive, with no validated intermediate
specification the user can review before deployment. Our baseline §4.2.5
measures exactly this gap.

**Program synthesis with intermediate representations.** Using a typed IR as
the synthesis target — rather than emitting the artifact directly — is a
recurrent finding in program synthesis [\cite:synthesis-ir]. The compiler here
follows that shape: `BackendSpec` is the inspectable, versionable artifact;
SQL is a deterministic function of it. The interesting trade-off, which the
ontology-size sweep (§5.2) probes, is that a *closed* IR guarantees
auditability at the cost of expressiveness.

**Human-in-the-loop disambiguation.** Clarifying-question systems and
mixed-initiative UI research [\cite:clarification-ml, \cite:mixed-initiative]
establish that targeted questions out-perform both silence and
over-questioning. Our MCQ engine contributes a dependency-graph ordering over
*capability-level* questions (feature confirms, parameter choices, negation
and contradiction resolutions, and unparsed-sentence clarifications) with a
hard cap on question budget — a concrete instantiation the calibration
literature's coverage-aware deferral [\cite:selective-prediction] usually
leaves abstract.

**Model calibration and selective prediction.** ECE
[\cite:ece-naeini], temperature scaling [\cite:guo-2017], and
coverage–correctness trade-offs [\cite:selective-prediction] are standard
post-hoc calibration tools. This paper's R3 is narrower and more
engineering-oriented: an *in-compiler gate* that measures ECE on the model's
shipped calibrated confidence, fits a temperature only when the gate trips,
and connects the result to a fixed 0.75 auto-accept decision threshold. The
vendor's own data motivates the gate: the base checkpoint's shipped ECE is
far above 0.1, and a per-(question-type, option-count) temperature refit
moves measured ECE from ≈0.47 to ≈0.08 — our reproduction attempts a single
scalar version of that fit inside the repo.

**Deterministic infrastructure generation.** Infrastructure-as-code and
schema-migration tooling ([\cite:iac]; e.g. Terraform, Prisma Migrate) is
deterministic by construction but consumes formal input. The present system
sits between that line and the LLM line: NL enters, but everything downstream
of interpretation is deterministic, idempotent, and replayable — the
composition engine's re-application semantics (§3.5) are verified by an
exhaustive pairwise fragment matrix against a live PostgreSQL.

## 3. System Design

### 3.1 Problem statement and IR

The task is a partial function `compile : NL → BackendSpec`, where `NL` is a
natural-language description of 1–500 words and `BackendSpec` is a typed
intermediate representation over a fixed ontology. The ontology (versioned
YAML, v1) declares ten features (authentication, roles, bookings, messaging,
payments, reviews, file storage, verification, realtime, favorites), their
typed parameters (e.g. `bookings.mode ∈ {instant, owner_approval,
request_then_approval, time_slot}`), eleven entities with fields, foreign
keys, and indexes, six roles (guest, user, owner, renter, admin, verifier),
hard `requires` and `contradicts` constraints
(e.g. instant booking contradicts owner verification; reviews require
bookings), and per-feature derivations of storage buckets and edge functions.
`BackendSpec` carries decided features, parameter values, roles, derived
entities, bucket definitions (name, visibility, RLS pattern, size limit),
edge functions, and the decision provenance (which mechanism decided what,
with what confidence and evidence). Compilation then decomposes:
`BackendSpec → migrations` is the fragment composer; `migrations → project`
is the deployer. Both are deterministic.

### 3.2 Pipeline

The workflow is
`interpret → classify → clarify → specify → validate → approve → compile →
deploy → remediate → retry`. Interpretation produces *candidates* — typed
decisions over ontology capabilities. Classification assigns each candidate a
confidence taken from the decision model's ECE-calibrated
`answer_confidence` (never the raw score; §3.6). Clarification (§3.4) resolves
whatever interpretation left undecided. Specification derives the full spec
from decided features (§3.5). Validation checks it against the ontology's
constraint graph (§3.5). Approval is the human review gate: nothing deploys
without it. Compilation, deployment, and remediation are §3.5–§3.6.

### 3.3 Interpreter: three mechanisms and a tiered merge

**Mechanism A — exact aliases.** A hand-authored alias table maps unambiguous
surface forms (`stripe`, `email password`, `magic link`, `google auth`,
`github auth`) to capability values with confidence 1.0. Aliases are exact
matches, so they cannot misfire on morphological variants.

**Mechanism B — phrase rules with negation spans.** Regex phrase rules map
verb-object patterns to feature enablements (`book/reserve/rent` +
`item/listing/property` → bookings; `message/chat/contact` + `each
other/user/owner/renter` → messaging; and so on for payments, reviews, file
storage, verification, favorites, and admin-role mentions). Each match is
checked for negation cues (`no`, `not`, `don't`, `without`, `avoid`, `skip`,
…) within a ±40-character window *clamped at sentence boundaries* — a match
inside a negated span becomes a proposal of `false` rather than being
dropped, so "there is no review system" decides reviews *off* deterministically
instead of silently doing nothing. Sentence clamping keeps a trailing "but we
won't do X" from negating the feature asserted in the previous sentence.

**Mechanism C — typed-decision model.** Laya (421M ModernBERT-large, English
checkpoint, 512-token context) scores yes/no (`needs_X`) questions over the
union of feature and entity names against the running partial state. It is
used strictly as a classifier over a fixed option set — it cannot invent a
label — which is what bounds its failure mode: an unsure model produces a
low-confidence candidate that the clarification loop converts into a
question, not a hallucinated feature.

**Tiered merge.** Per capability, candidates merge by tier: `exact` >
(`phrase` ∣ `phrase_negated`) > `model`. Within a tier, agreeing values
collapse to the maximum-confidence candidate; disagreeing values are *all*
kept and surface as a negation-resolution question rather than being
arbitrated silently. A v1.5 fix places negated phrase matches in the same
tier as positive phrases so that "we do use stripe" (positive) and "there are
no payments" (negated) conflict visibly instead of the negative winning by
accident.

**Confidence gates.** A decided candidate with confidence ≥ 0.75 is
auto-accepted; 0.35–0.75 is ambiguous (asks); 0.20–0.35 is weak; below 0.20
is unsupported (recorded and shown, never built). The 0.75 auto-accept
threshold is the knob R3's calibration work defends (§3.6).

### 3.4 Clarification: the MCQ loop

Residual ambiguity becomes a bounded multiple-choice session. The engine
generates six question kinds: feature confirmation, parameter choice,
negation resolution, contradiction resolution, *unparsed-sentence
clarification*, and (ordering-reserved) weak confirmation. Every input
sentence must be covered by some candidate's evidence span; a sentence that
maps to nothing becomes `clarify_unparsed` offering the ontology's feature
list as answers — this is the never-silently-omit invariant's structural
guarantee: the user is *asked about the sentence the machine could not read*,
and their answer decides the feature. Questions are ordered by a dependency
graph (contradictions first, then negations, then unparsed coverage, then
confirms ordered by confidence, then parameter choices), pruned by feature
dependencies (a feature whose dependencies are not enabled is never
confirmed), and capped (`max_mcqs`, ≤ 10 for complex inputs, ≤ 3 for simple
ones per the specification's DoD). Contradiction questions are emitted from
the ontology's hard `contradicts` constraints against the decided state; the
instant-bookings/owner-verification conflict is the v1 example. Users may
also answer ahead of time; pre-answered targets are decided and never asked.

### 3.5 Specification: derivation, validation, composition

**Derivation.** `recompute_spec` derives entities (from features'
`activates_entities`, gated for realtime by whether any table-backed channel
is actually subscribed), storage buckets (from the file-storage purpose:
avatars/listings public, documents private, mixed all three, plus a private
verification bucket when verification is on), and edge functions (with a
stripe webhook only when Stripe is the provider, and a notification dispatcher
only when a table-backed realtime channel exists). Derivation is total and
deterministic; the validator (below) re-derives and rejects any mismatch, so
the spec's derived views cannot drift from its decisions.

**Validation.** A typed validator checks hard `contradicts` and `requires`
constraints, unknown features and parameters, invalid parameter values and
lengths, undefined roles, RLS overrides naming entities the spec does not
create, circular feature dependencies, and derivation mismatches. Soft
constraints (e.g. anytime-messaging weakens authenticated identities)
produce warnings that do not block. An invalid spec cannot reach approval.

**Fragment composition.** The composer reduces a valid spec to a list of SQL
migrations. Fragments come in three kinds: generated from the ontology
(`table_<entity>` with foreign-key ordering edges; per-entity role-group RLS
policies), and hand-authored static fragments (role-helper functions, storage
buckets, realtime publication guards, a verification-status trigger).
Composition is: select fragments per spec feature → topologically sort by
`requires` (stable Kahn; byte-identical output for identical input) → run
six conflict detectors (duplicate fragment ids, duplicate object names, RLS
policy-name collisions, trigger collisions, foreign-key cycles, duplicate
buckets) → emit `{ordinal}_{fragment_id}.sql`. Generated SQL is idempotent —
`CREATE … IF NOT EXISTS`, drop-before-create policies and triggers,
`ON CONFLICT DO NOTHING` bucket inserts — so re-applying a composition to a
live database is a no-op. Edge functions are deliberately *not* migrations;
they ship as Deno templates scaffolded by the deployer. Two properties are
verified continuously: compiling the same spec twice yields byte-identical
migrations (§18.14), and *every pair* of the 35 fragments — 595 combinations —
composes to SQL that applies cleanly twice against a live PostgreSQL 15
(§18.18), which is what makes the pairwise ablation in §5.2 trustworthy at
the SQL layer.

### 3.6 Deployment, remediation, and the calibration gate

**Deployer.** The deployer creates the Supabase project through the
Management API once, waits for service health, links the CLI, writes the
composed migrations (clearing stale files between attempts), applies them
with `db push --include-all`, patches auth configuration per the spec, and
scaffolds and ships edge-function templates. Failures are classified by an
ordered phrase-group taxonomy into nine categories (duplicate object, RLS
conflict, FK ordering, missing extension, permission, transient, quota,
syntax, unknown). The remediation loop *reuses the created project* across
at most three attempts: transient errors retry with exponential backoff;
structured errors surface a remediation multiple-choice (per §9.3); empty
remediation escalates to the operator. The final result always carries the
project ref and the last error category, so a half-deployed project is never
orphaned silently.

**Calibration gate.** The compiler consumes the model's shipped
`answer_confidence` and never fits a temperature by default. A pinned test
measures 10-bin ECE — Σ over non-empty bins of bin share × |mean confidence
− mean accuracy| — on a held-out `(answer_confidence, label)` set; only when
measured ECE ≥ 0.1 does the fitter run, applying
`calibrated = sigmoid(logit(clip(p, 1e-6, 1−1e-6)) / T)`. The gate exists
because the vendor's shipped calibration for the base checkpoint is far from
the 0.1 target, and because the auto-accept threshold (0.75) is only
meaningful if the confidences it thresholds are honest. The in-repo fitter is
a single scalar T (clamped to [0.5, 5.0] when persisted, matching the
vendor's convention); the vendor fits per (question type, option count), and
whether the scalar refit reproduces their measured 0.47 → 0.08 improvement is
an open experimental question (§5.3, R3). **Honesty note:** the currently
committed calibration fixtures are synthetic — they unit-test the ECE formula
and the fitter, they are not a measurement of the model.

### 3.7 Evidence state

Implemented and tested end to end with mock-model doubles: interpretation
(mechanisms A/B/C, merge, negation), the MCQ engine, derivation, validation,
composition (idempotency + 595-pair matrix on live PostgreSQL), and the
deployer (§18.15 stale-file cleanup, §18.16 error-injection with project
reuse). The nightly end-to-end tier against real Supabase credentials exists
and is credential-gated. Not yet done: real-model calibration pairs
(R3's primary endpoint), baseline runs against LLM backends, and any
comparative measurement against external generators — §5.1/§5.3/§5.4 report
the status of each.

## 4. Experimental Setup

### 4.1 Task and dataset

The task (§3.1) is `compile : NL → BackendSpec → deployed project`. The
golden corpus is **50 hand-crafted inputs** (`tests/golden/cases/`, spec
§10.2) covering the full ontology surface — every feature, parameter branch,
bucket purpose, derived edge function, role combination, and the display
cases for negation and contradiction resolution. Each case pins: the input
text; a Laya *persona* (`none` = empty model envelope, `default` = 0.5 noul
answers, `high` = 0.95 noul answers); the `user_answers` a human would give
the clarification loop; and the expected `BackendSpec` fragment (features,
parameters, and, where relevant, roles, entities, buckets, edge functions).

**Honesty note on the dataset.** The expected specs are *engine-pinned*:
they were written and then confirmed by running the engine with the mock
personas, so they are regression truth, not yet independent human
annotation. Splits (train / golden / held-out) and independent annotation
are part of the §4.4 protocol but not yet authored. All experiment numbers
in §5.2 are therefore measurements of the *engine with the contract-test
model double*, not of the real 421M checkpoint (which remains blocked on
installation; §5.3).

### 4.2 Baselines

Per §4.3 of the outline, five baselines; their harness states today:

1. **End-to-end LLM direct-to-SQL** — *built, gated.* `DirectSqlBaseline`
   prompts an OpenAI/Anthropic model (pinned checkpoint ids; §4.4) for a
   Supabase migration and scores artifact-level CREATE TABLE presence
   against the case's gold entities. Constructs a real completer only when
   `OPENAI_API_KEY`/`ANTHROPIC_API_KEY` is set; otherwise self-skips
   (credentials absent in this environment → no measured rows yet).
2. **LLM → `BackendSpec` → same composer** — *built, gated.*
   `BackendSpecBaseline` prompts the model (bounded to the ontology
   vocabulary) for a `BackendSpec` JSON, parses it, runs it through the
   *same* `recompute_spec` and fragment composer as Mechanism C's output, and
   scores with the same fidelity metrics — isolating the contribution of the
   IR from the generator. Self-skips without keys. The parse → spec → score
   path is unit-tested offline with injected completers.
3. **Rules-only** — *measured* (§5.2, mechanisms `A+B`).
4. **Laya-only** — *measured* (§5.2, mechanism `C`, mock persona).
5. **DbSmash / off-the-shelf generator** — adapter surface only; the tool is
   external and not configured, so the adapter reports `skipped` with the
   reason, matching the e2e tier's behavior.

### 4.3 Metrics

All metrics are computed from the golden labels (§4.1) against the spec a
configuration produces (`tests/experiments/metrics.py`, runnable via
`python -m tests.experiments.run_ablation`):

- **Feature precision / recall** over the *positive* class (feature
  enabled): `precision = TP / |predicted enabled|`, `recall = TP /
  |gold enabled|`. A case with no gold-enabled features (pure-negation case)
  scores 1.0 iff nothing was enabled.
- **Silent-omission rate** (R1's primary endpoint) and **hallucinated-feature
  count** = `|gold enabled \ predicted|` and `|predicted \ gold enabled|`.
  Note the asymmetry: the golden suite's partial submatch (§18.13) asserts
  presence but *cannot* catch additions — the precision half of this metric
  is what surfaces them.
- **Dimension exactness** for parameters, roles, entities, buckets, edge
  functions, each scored only when the case pins that dimension; the empty
  gold case (`no gold-true features`) is handled explicitly.
- **MCQ burden** = the number of questions the clarification loop would put
  to the user, measured as the untruncated residual question count of
  `run_mcq_loop` with no user answers.
- **Latency** = wall-clock ms per run (mock model ≈ 0.2–0.4 ms).
- **Spec-exact** (all-match) = features exact *and* every pinned dimension
  exact.

### 4.4 Protocol

Deterministic: mock personas are tape-like, so every row reproduces
byte-for-byte (`ablation.jsonl` is committed). For the LLM baselines the
protocol pins model versions (`gpt-4o`, `claude-sonnet-4-20250514`), ≥ 3
seeds, a paired per-requirement comparison, and McNemar on omission /
Wilcoxon signed-rank on continuous metrics (outline §4.4). The default Laya
behaviors under measurement are the shipped mock personas; real-checkpoint
measurements replace the persona on the same cases in the same JSON schema
(R3, §5.3). `laya-typed-decisions` is intentionally out of scope (DoD #22).

## 5. Results

### 5.1 → R1. Fidelity vs. baselines

**Current evidence state: no measured rows yet.** The harness is built and
the golden corpus is fixed; every LLM baseline self-skips in this
environment because no `OPENAI_API_KEY`/`ANTHROPIC_API_KEY` is configured.
Filling this section requires (i) credentials for §4.2.1/2/5, and (ii)
independent ground-truth annotation so the golden expectations are not
author-authored by the engine it measures.

What *is* measurable today is the composition side of R1: the delivered
`BackendSpec` compiles to SQL that applies cleanly twice across the 595-pair
fragment matrix on live PostgreSQL 15, byte-identically for identical input
(§3.5), giving the claim's determinism half a firm basis.

### 5.2 → R2. Ablations (mechanism subset × MCQ on/off)

Measurements on the 50 golden cases with the mock personas
(`python -m tests.experiments.run_ablation`; full detail in
`tests/experiments/results/ablation_summary.md`):

| Config | macro R / P | pooled R / P | omissions | hallucinations | feature-exact | params (pinned) | MCQ count (mean) | ms (mean) |
|---|---|---|---|---|---|---|---|---|
| A only + MCQ | 0.702 / 0.960 | 0.550 / 1.000 | 58 | 0 | 21/50 | 16/26 | 6.58 | 0.3 |
| A only (no MCQ) | 0.080 / 0.080 | 0.000 / 1.000 | 129 | 0 | 4/50 | 0/26 | 1.30 | 0.2 |
| B only + MCQ | 0.972 / 1.000 | 0.922 / 1.000 | 10 | 0 | 48/50 | 19/26 | 6.70 | 0.3 |
| A+B rules + MCQ | 0.972 / 1.000 | 0.922 / 1.000 | 10 | 0 | 48/50 | 25/26 | 6.54 | 0.3 |
| A+B rules (no MCQ) | 0.397 / 0.720 | 0.419 / 1.000 | 75 | 0 | 4/50 | 6/26 | 2.14 | 0.2 |
| C only (Laya) + MCQ | 0.742 / 0.984 | 0.643 / 0.912 | 46 | 8 | 22/50 | 13/26 | 6.94 | 0.3 |
| C only (Laya) (no MCQ) | 0.120 / 0.104 | 0.093 / 0.600 | 117 | 8 | 5/50 | 0/26 | 1.58 | 0.3 |
| **A+B+C hybrid + MCQ** | 1.000 / 0.984 | 1.000 / 0.942 | **0** | **8** | **49/50** | **26/26** | 6.74 | 0.4 |
| A+B+C hybrid (no MCQ) | 0.425 / 0.704 | 0.496 / 0.889 | 65 | 8 | 5/50 | 7/26 | 2.34 | 0.3 |

Four findings, each honest to its measurement setting (mock personas):

1. **The clarification loop carries the completeness.** Across every
   mechanism subset, disabling MCQ collapses recall (hybrid pooled recall
   0.496 → 1.000 with MCQ on) and multiplies omissions (65 → 0). The loop's
   residual question burden is low — ~6.5–6.9 questions per input for the
   human-answerable configs, 2.34 for the interpretation-only floor — which
   is the case for the always-ask-vs-auto-accept trade (§6).
2. **Mechanism A (aliases) is a parameter supplier, not a feature detector.**
   Alone it decides nothing (pooled recall 0.000 without MCQ) but lifts
   parameters from 19/26 to 25/26 when added to B — provider, auth-method,
   and lifetime params arrive only via exact matches.
3. **Mechanism B (phrases) is the workhorse** on its own vocabulary: 0.922
   pooled recall with MCQ, zero hallucinations, 48/50 feature-exact. This
   corroborates the outline's R2 risk — on a bounded vocabulary rules carry
   most of the load.
4. **Mechanism C contributes exactly the residual—and that contribution has
   two faces.** The hybrid's superiority over rules-only (0 omissions vs 10,
   pooled recall 1.000 vs 0.922, 26/26 vs 25/26 params) is entirely carried
   by the two `high`-persona cases, where features exist in the gold spec
   that *no rule and no alias can see*: mechanism C genuinely extends
   coverage. But the same two cases produce all 8 hallucinations: the
   model proposes *every* capability at 0.95, and — this is the important
   part — the golden suite's partial submatch does not catch the additions,
   while the precision metric does (`laya_high_decides` enables ten
   features for an input that names two). Under the design, this is R3's
   job: 0.95 *raw* confidence must not survive as 0.95 *answer_confidence*
   where the model is wrong (§5.3).

### 5.3 → R3. Calibration and the auto-accept gate

**Current evidence state: synthetic only, and it does not yet pass the
gate.** The committed fixture (40-entry, `answer_confidence`+labels in the
real JSON schema) measures ECE 0.045 < 0.1 (the §3.6 gate) — a unit test of
the ECE formula and `fit_temperature`, not a model measurement. The
temperature-fit demo (20-entry set) moves ECE 0.45 → 0.1047, stopping just
above the gate at best T = 10.0 — the grid-search boundary, and > 5.0, so
not persistable under the vendor clamp. **This section stays empty of model
numbers.** The blocking gap is concrete: the vendored `laya` package
(0.3.20) requires `torch` and an ~800 MB checkpoint download, neither
available in this environment; the Phase-7 fine-tuning decision is likewise
unmade. Until held-out `(answer_confidence, label)` pairs exist for the
`english` checkpoint, R3 cannot be demonstrated, and the 8 hallucinations of
§5.2 remain *uncalibrated* — they are the expected consequence of the
vendor's shipped ECE distribution, not a failure of the gate.

### 5.4 End-to-end (secondary)

**Current evidence state: built, no measured deployments.** Composition +
deployer + the nightly credential-gated e2e tier ship
(`compiler/generator/`, `compiler/deployer/`, 595-pair matrix on live PG);
no Supabase account is configured in this environment, so deployment
success / first-attempt rate / time-to-spec / cost have no measured rows.
Filling this section requires `SUPABASE_ACCESS_TOKEN` (+ org slug) — a
credential, not a code gap.

## 6. Discussion

**The MCQ burden is the price of zero omission.** Interpretation alone
reaches pooled recall 0.496 on these 50 inputs; the clarification loop
closes the remaining 54% of recall at a cost of ~6.5 questions per input
(human-answerable). Whether that is the right trade is exactly what the
coverage-vs-correctness curve R3 must produce should settle: if 0.75
auto-accept on calibrated confidence covers, say, 80% of decisions at ≥ 99%
agreement, the marginal questions are the residual ambiguity users actually
have — versus always-ask, which would pay the burden for decisions the
system could take. The 2.34-question no-MCQ floor shows the loop is not
padding: those are genuine undecideds, not noise (§5.2, finding 1).

**Rules win the bounded vocabulary; the model earns its place narrowly.**
On 48/50 cases rules+aliases alone already reconstruct the spec (0.922
pooled recall, zero hallucinations). The model's measured contribution is
real but thin and double-edged: it alone is near-useless (0.093 without
MCQ), yet the two inputs whose requirements *no rule can see* are only
resolvable through it, and its over-proposal is what precision metrics must
catch. This is the honest shape of R2 on this vocabulary: not "the model
wins", but "the hybrid is the only configuration with zero omission, and the
model is the only mechanism that can see the long tail — if its confidence
is calibrated".

**The golden evaluation has a blind spot this setup exposes.** `spec_matches`
(§18.13) checks that expected values appear in the output; it cannot flag
output the gold set doesn't name. Eight hallucinated features passed the
golden suite and were caught only by the experiment tier's precision half.
Two consequences: (i) golden expectations should gain absence pinning
(the empty-`features` convention the metrics module implements), and (ii)
the paper must treat precision and recall as equally first-class — a purely
recall-driven metric on this corpus would over-credit an over-confident
model.

**Where the layered design loses.** Rule and alias tables are finite; a
paraphrase outside both the phrase rules and the ontology vocabulary falls
to the model, and if the model is below the majority-class baseline (vendor
benchmarks), fallback is MCQ or silence-flagging. The never-silently-omit
invariant is preserved structurally (unparsed sentences become
`clarify_unparsed`), but the *precision* of that guarantee scales with the
rule tables and the calibrated coverage — never with raw generation. That
is the paper's central trade, and it is the R1 sub-clause worth stating
loudest: unsupported requirements are flagged, not guessed.
