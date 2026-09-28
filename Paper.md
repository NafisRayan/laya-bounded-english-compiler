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
(R3's primary endpoint), baseline harness runs, and any comparative
measurement — §4–§5 are empty until those land.
