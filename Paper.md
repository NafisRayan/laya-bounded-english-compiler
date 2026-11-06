# From Bounded English to a Working Backend: A Deterministic, Ontology-Bounded Compiler

*Draft: all sections drafted (§1–§8, measured results on cleaned human-verified
gold, frozen held-out split). Evidence ledger and per-section status:
`Paper Outline.md`. Bibliography is generated from `submission/references.bib`; add entries there, not in a list here.*

**Abstract.** A common belief in AI-assisted software engineering is that natural-language
tasks require large language models. This paper argues, and measures, a narrower
claim: against a fixed ontology, deterministic compilation of a specified spec
replaces free-form generation for the deployable artifact; not for unaided
interpretation, where a zero-shot LLM wins recall. We present a deterministic,
ontology-bounded compiler for Supabase backends: three interpretation mechanisms
(exact aliases, span-clamped phrase rules, and a 421M-parameter typed-decision
model) merge tier-first, a multiple-choice loop resolves every uninterpreted
sentence, and a fragment composer deploys the result. With clarification answers
taken from the gold (oracle MCQ), rules plus the loop reconstruct it at 1.000 /
1.000 (35/15 split); without them the hybrid scores 0.807 / 0.939 (11 omissions)
vs 0.906 / 0.850 (6 omissions, unparseable excluded) for the zero-shot LLM→spec
baseline. Its deterministic deliverables: fragment composition, RLS by
construction, idempotent redeployment. The optional 421M ModernBERT slot-filler
is well calibrated (ECE 0.0381) but adds no significant fidelity (p = 0.421);
its temperature refit helps in-sample, degrades held-out, and is not shipped.
Deployment reliability: 30/30 first-attempt operations (Wilson CI [0.886,
1.000]); three live e2e sessions (nine operations), the first in 39 s. The
supporting gold is author-curated, dual-annotated, author-reconciled (raw
κ = 0.16), linted, re-reviewed 184/184; its limitations (authoring bias,
self-adjudication, operator-answer contamination) are consolidated as threats
to validity.
**Keywords.** Natural language to backend; Deterministic compilation; Software specification; Program synthesis; Calibration; Human-in-the-loop clarification
---

## 1. Introduction

Building the backend of a web application (database schema, row-level
security, authentication, file storage, realtime channels, and edge functions)
is a well-bounded engineering task that is nonetheless inaccessible to many
people who can describe it precisely in a paragraph of English. This paper
studies the task of compiling that paragraph into a working Supabase project:
the input is a 1–500 word natural-language description of a backend, and the
output is a validated, typed intermediate specification (`BackendSpec`) that is
compiled into pre-tested SQL migrations, RLS policies, auth configuration,
storage buckets, and edge functions, then deployed programmatically through
the Supabase Management API and CLI.

The obvious approach, prompting a large language model to emit the schema and
policies directly, fails in ways that matter for this task. End-to-end
generation is nondeterministic: the same prompt can yield different schemas on
different runs, so the build cannot be audited or reproduced. It hallucinates
tables and policies that no requirement asked for. Most importantly, its worst
failure mode is silent: a requirement that the model simply drops never
appears in the output, and nothing marks the omission. A malformed generated
RLS policy is not a cosmetic bug but a security risk: the difference between
"owner can read their rows" and "everyone can read everyone's rows" is one
prompt drift away, and security audits of LLM-generated code find exactly
this class of failure at scale [@pearce2022asleep].

We instead treat NL-to-backend as a *compilation* problem over an explicit,
versioned task vocabulary. A fixed ontology enumerates the features,
parameters, entities, roles, and storage buckets the platform knows how to
build; the ontology bounds expressiveness by construction, and requirements
outside the vocabulary are *flagged as unsupported* rather than guessed.
Three interpretation mechanisms, exact alias matching, character-span phrase
rules with sentence-clamped negation detection, and a small (421M-parameter)
typed-decision model, propose typed decisions against the ontology; a tiered
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
   model, gated by targeted MCQ clarification, with the small model used
   strictly as a *classifier against a fixed option set*, never as a
   generator (R2).
3. **A closed-form calibration gate, and its measured limits**: ECE on
   the model's shipped `answer_confidence`, with temperature fitting
   applied only when the gate (ECE ≥ 0.1) demands it, feeding the 0.75
   auto-accept threshold. Measured honestly: the shipped confidence passes
   every gold generation, the refit helps in-sample but degrades held-out
   and is not shipped, and the checkpoint is strictly optional (R3).
4. **An evaluation protocol** for NL-to-backend fidelity: silent-omission
   rate, hallucination counts, exact-match on the typed IR, MCQ burden,
   and deployment success, with ablations that isolate the IR, the
   rules, and the model, external baselines reported under disclosed run
   limits (§4.4), plus a dual-annotated, author-reconciled gold whose
   limitations are consolidated as threats to validity (§4, §7).

**Evidence state.** The system is implemented end to end
(`backend-compiler/compiler/`: interpreter, MCQ engine, spec derivation and
validation, fragment composition, deployer), with 1,100+ tests including a
595-pair fragment matrix applied against a live PostgreSQL 15 and a 50-case
golden corpus. Comparative measurements against baselines, ablations,
calibration, and end-to-end deployments are all measured in §5 under
the cleaned human gold (§4.1).

## 2. Related Work

Five literatures border this system. Each is stated in its strongest form
before the delta.

**NL to schema and text-to-SQL.** The largest neighboring line maps natural
language to database *queries over an existing schema*: benchmarks such as
Spider [@yu2018spider] and BIRD [@li2023bird] fixed the cross-domain task
and its execution-based scoring, LLM-era decomposed and schema-aware prompting, as surveyed in [@jiang2025survey],
then moved execution accuracy sharply upward via DIN-SQL [@pourreza2023dinsql] and C3 [@dong2023c3], and the older semantic-parsing context is
surveyed in [@kamath2019survey], and prompt-design itself is benchmarked in
DAIL-SQL [@gao2024dailsql]. Text2Schema [@wang2025text2schema] begins to
close the gap on our side of the line, generating table structures from
unstructured intent. The line validates a premise we build on:
constrained, schema-aware decoding beats free-form generation for structured
output, but its schema is an *input* (Text2Schema's output stops at bare
relational DDL), and none of it, to our knowledge,
scores requirement omission as a first-class metric. Our delta: the target is
not SQL text but a typed `BackendSpec` covering schema plus security policy
plus platform configuration; the vocabulary is bounded by a versioned
ontology with a never-silently-omit invariant (§3.1, §3.4); deployment
through the platform API is part of the measured task (§5.4), and rather
than compare on their benchmarks, we run the LLM baselines on ours, where
direct-to-SQL generation recovers 0.419 table recall and the spec-space
baseline holds the precision edge (§5.1).

**Program synthesis with intermediate representations.** Synthesis over
bounded target languages is a mature discipline: sketching [@solarlezama2008sketching], syntax-guided synthesis [@alur2013syntax], grammar-augmented generation [@ugare2024syncode], DSL-bounded induction
shipped at consumer scale in FlashFill [@gulwani2011flashfill], neural prior guidance
over DSLs in DeepCoder [@balog2017deepcoder], and solver-aided host languages
[@torlak2013rosette], and the tiered NL→DSL shape has an ICSE-published
ancestor [@desai2016program]: precise recognizers first, probabilistic
ranking second, user queries for the remainder: our A→B→C→MCQ order
exactly. Its recurrent finding is ours by adoption:
restricting the target to a typed intermediate representation [@mundler2025type] makes search
tractable and the result checkable. Our delta: the IR here is not a program
space to be searched but a domain-typed product spec; correctness is not
established by a solver over candidate programs but by a validator that
re-derives the spec from its decisions and rejects any mismatch (§3.5), and
specification misunderstanding is a documented failure mode [@tian2025fixing], and the closed vocabulary is precisely what makes *flag-don't-guess* expressible
as an invariant rather than an aspiration (§3.1). The generate-then-verify
counterpart exists in specification generation: SpecGen [@dong2025specgen]
and AutoReSpec [@ayon2026autorespec] iterate LLM output until a formal
verifier accepts it, whereas here the validator sits inside the compiler
and no free-form artifact ever exists to repair. The strongest published
alternative is the one we reject: scale-and-filter; AlphaCode [@li2022alphacode] bought competitive-programming reliability with millions of samples
filtered by execution, a strategy unusable here where the output includes
artifacts no test suite can grade, like RLS policies.

**Human-in-the-loop disambiguation.** Mixed-initiative interaction
principles [@horvitz1999mixed], clarifying-question retrieval in open-domain
conversational QA [@aliannejadi2019asking], and question selection under
uncertainty in active learning [@settles2009active] establish that targeted
questions outperform both silence and over-asking. Our delta: the questions
are neither authored in advance nor free-form generated; they are
multiple-choice items *derived from the partial spec itself* (contradiction
and negation resolutions, capability confirms, parameter choices, and
unparsed-sentence clarification), ordered by a dependency graph and hard-
capped, with the burden measured rather than asserted: ≈6.5–7 questions per
input for the human-answerable configurations and ≈2.3 for the
interpretation-only floor (§5.2). Automated assistance for requirements completeness is an established line [@luitel2024improving]. The unparsed-sentence item is what makes
never-silently-omit structural: the user is asked about exactly the sentence
the interpreter could not read (§3.4). The dialogue-precedent line, CoSQL
[@yu2019cosql], PRACTIQ [@dong2025practiq], and ambiguity benchmarks such as AMBROSIA [@saparina2024ambrosia], established that database
interfaces must model clarification and unanswerable queries; those systems
resolve through free-form dialogue with editable step-by-step explanations [@tian2023interactive], where ours presents bounded,
ontology-grounded multiple-choice options. Learning-to-defer theory
[@mozannar2020consistent] supplies the loss-theoretic view of that
threshold (our "expert" is the user, queried at inference time through
options the ontology enumerates), and SMCalFlow [@andreas2020task] is
the closest published cousin: a typed dataflow IR with explicit
clarification for uninterpretable utterances, their metacomputation being
our `clarify_unparsed`.

**Model calibration and selective prediction.** Expected calibration error
[@naeini2015obtaining], temperature scaling [@guo2017calibration], and the
reject-option / risk-coverage line [@chow1970optimum; @geifman2017selective]
form the standard toolkit, since extended to LLM validity by conformal prediction [@cherian2024large]: measure calibration post hoc, rescale, and trade
coverage against accuracy at a chosen operating point, with the metric
itself handled conservatively, since binned ECE is sensitive to binning
choices and can shift under correction [@kumar2019verified], which is why
the gate fails conservative and reports the full sweep rather than a
single operating point (§5.3). Our delta is the
deployment shape: calibration as an *in-compiler gate* (10-bin ECE measured
on the model's shipped `answer_confidence`, a temperature fitted only when
ECE ≥ 0.1, feeding a fixed 0.75 auto-accept threshold (§3.6)), with the
coverage–correctness curve measured on the golden corpus: 87.8% of decisions
auto-accept at 80.0% correctness, and the curve is non-monotone, so raising
the threshold is not monotonically safer (§5.3). One finding is consistent
with label noise as a first-order confounder [@frenay2014classification]:
successive cleanups of the gold labels moved measured ECE 0.0951 → 0.0381
while accuracy rose 0.784 → 0.896 in-sample (§5.3), and most of the
apparent miscalibration lived in the labels.

**Backend and schema generator tooling.** Managed-backend platforms supply
the substrate but consume explicit configuration [@firebase2026; @supabase2026], the ecosystem's natural-language story is prompt templates and
assistants rather than compilers [@supabase2026], and infrastructure-as-code
is deterministic but requires formal input (e.g., Terraform, Prisma). Two
findings motivate replacing probabilistic generation in this domain
outright: LLM-generated code carries security vulnerabilities in roughly
40% of scenarios [@pearce2022asleep], with broken access control and
injection among the most frequent; and on cloud infrastructure tasks the
best LLM achieves only 19.36% pass@1 against 86.6% on ordinary Python
IaC-Eval [@kon2024iaceval]. The closest published-tool neighbor is
DbSmash, an AI CLI that turns a
plain-text app description into a schema [@reddy2025dbsmash]; we benchmarked it on
our corpus through its non-interactive CLI path: schema artifacts in 15 of 50
runs, table recall 0.081 / precision 0.179 (§5.1), stated with the fairness
caveat that the tool's intended interactive flow is stronger than the path
our harness drives, so the number prices the non-interactive mode, not the
tool at its best. Our delta: the pipeline produces a validated, reviewable
typed spec that a human approves before anything deploys (§3.2); its RLS
policies and auth rules are synthesized from pre-verified parameterized
fragments rather than generated text, the direct answer to the access-control
failure modes Pearce et al. document; the pipeline is
deterministic and idempotent downstream of interpretation, with byte-identical
migrations for identical input, 595-pair fragment matrix against a live
PostgreSQL (§3.5), measured end to end against cleaned human gold:
with the oracle operator it reconstructs the gold exactly, while
operator-free it trades omissions for precision against the best
zero-shot baseline (§5.1).
The security literature closes the loop: developers assisted by AI write
significantly less secure code while feeling more confident in it [@sandoval2023users], the same pattern predates LLMs in infrastructure-as-code, where security smells in Ansible and Chef scripts replicate [@rahman2021security], and extracting enforceable access-control policy from natural
language has been a recognized hard problem since before LLMs [@narouei2020automatic], with current LLM translation still falling short of enforceable
accuracy [@lawal2024translating]: the reason this compiler classifies policy
decisions against a fixed option set and expands pre-verified fragments
rather than generating policy text.

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
deploy → remediate → retry`. Interpretation produces *candidates*: typed
decisions over ontology capabilities. Classification assigns each candidate a
confidence taken from the decision model's ECE-calibrated
`answer_confidence` (never the raw score; §3.6). Clarification (§3.4) resolves
whatever interpretation left undecided. Specification derives the full spec
from decided features (§3.5). Validation checks it against the ontology's
constraint graph (§3.5). Approval is the human review gate: nothing deploys
without it. Compilation, deployment, and remediation are §3.5–§3.6.

### 3.3 Interpreter: three mechanisms and a tiered merge

**Mechanism A: exact aliases.** A hand-authored alias table maps unambiguous
surface forms (`stripe`, `email password`, `magic link`, `google auth`,
`github auth`) to capability values with confidence 1.0. Aliases are exact
matches, so they cannot misfire on morphological variants.

**Mechanism B: phrase rules with negation spans.** Regex phrase rules map
verb-object patterns to feature enablements (`book/reserve/rent` +
`item/listing/property` → bookings; `message/chat/contact` + `each
other/user/owner/renter` → messaging; and so on for payments, reviews, file
storage, verification, favorites, and admin-role mentions). Each match is
checked for negation cues (`no`, `not`, `don't`, `without`, `avoid`, `skip`,
…) within a ±40-character window *clamped at sentence boundaries*; a match
inside a negated span becomes a proposal of `false` rather than being
dropped, so "there is no review system" decides reviews *off* deterministically
instead of silently doing nothing. Sentence clamping keeps a trailing "but we
won't do X" from negating the feature asserted in the previous sentence.

**Mechanism C: typed-decision model.** Laya (421M ModernBERT-large, English
checkpoint, 512-token context) scores yes/no (`needs_X`) questions over the
union of feature and entity names against the running partial state. It is
used strictly as a classifier over a fixed option set (it cannot invent a
label), which is what bounds its failure mode: an unsure model produces a
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

Residual ambiguity becomes a bounded multiple-choice session, the
structured counterpart to the free-form clarification conversation
ClarifyGPT [@mu2024clarifygpt] generates around LLM code generation. The engine
generates six question kinds: feature confirmation, parameter choice,
negation resolution, contradiction resolution, *unparsed-sentence
clarification*, and (ordering-reserved) weak confirmation. Every input
sentence must be covered by some candidate's evidence span; a sentence that
maps to nothing becomes `clarify_unparsed` offering the ontology's feature
list as answers; this is the never-silently-omit invariant's structural
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
buckets) → emit `{ordinal}_{fragment_id}.sql`. Generated SQL is idempotent (
`CREATE … IF NOT EXISTS`, drop-before-create policies and triggers,
`ON CONFLICT DO NOTHING` bucket inserts), so re-applying a composition to a
live database is a no-op. Edge functions are deliberately *not* migrations;
they ship as Deno templates scaffolded by the deployer. Two properties are
verified continuously: compiling the same spec twice yields byte-identical
migrations (the determinism test), and *every pair* of the 35 fragments, 595
combinations, composes to SQL that applies cleanly twice against a live
PostgreSQL 15 (the pairwise composition test), which is what makes the pairwise
ablation in §5.2 trustworthy at the SQL layer.

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
structured errors surface a remediation multiple-choice; empty
remediation escalates to the operator. The final result always carries the
project ref and the last error category, so a half-deployed project is never
orphaned silently.

**Calibration gate.** The compiler consumes the model's shipped
`answer_confidence` and never fits a temperature by default. A pinned test
measures 10-bin ECE, Σ over non-empty bins of bin share × |mean confidence
− mean accuracy|, on a held-out `(answer_confidence, label)` set; only when
measured ECE ≥ 0.1 does the fitter run, applying
`calibrated = sigmoid(logit(clip(p, 1e-6, 1−1e-6)) / T)`. The gate exists
because the vendor's shipped calibration for the base checkpoint is far from
the 0.1 target, and because the auto-accept threshold (0.75) is only
meaningful if the confidences it thresholds are honest. The in-repo fitter is
a single scalar T (clamped to [0.5, 5.0] when persisted, matching the
vendor's convention); the vendor fits per (question type, option count), and
whether the scalar refit reproduces their measured 0.47 → 0.08 improvement is
an open experimental question (§5.3, R3). **Honesty note:** the gate
fixture is now 500 measured pairs (real `english` checkpoint on the golden
corpus, §5.3); the deliberately-miscalibrated fit-demo set stays synthetic
on purpose: a well-calibrated real set cannot demo the fit.

### 3.7 Evidence state

Implemented and tested end to end with mock-model doubles: interpretation
(mechanisms A/B/C, merge, negation), the MCQ engine, derivation, validation,
composition (idempotency + 595-pair matrix on live PostgreSQL), and the
deployer (stale-file cleanup and error-injection with project
reuse). The end-to-end tier has been exercised against a real Supabase
account in three live sessions plus a ten-session deployment battery
(§5.4), the baseline harness has been
exercised against a live LLM through its real code path (§5.1), and the real
pinned checkpoint has been measured two ways: calibration (§5.3) and the
full ablation grid (§5.2). The full baseline sweep, including the
off-the-shelf generator, is measured (§5.1), and every §5 number is
reported against the author-curated, dual-annotated, author-reconciled gold with a frozen
held-out split (§4.1). The agreement-bias re-review has also run: an
independent blind reviewer covered all 184 gold rows (a confirmation
pass, not independent label construction), confirming the prior
rulings everywhere but one held-out parameter defect, held and disclosed
by decision (§4.1).

## 4. Experimental Setup

### 4.1 Task and dataset

The task (§3.1) is `compile : NL → BackendSpec → deployed project`. The
golden corpus is **50 hand-crafted inputs** (`tests/golden/cases/`) covering
the full ontology surface: every feature, parameter branch,
bucket purpose, derived edge function, role combination, and the display
cases for negation and contradiction resolution. Each case pins: the input
text; a Laya *persona* (`none` = empty model envelope, `default` = 0.5 noul
answers, `high` = 0.95 noul answers); the `user_answers` a human would give
the clarification loop; and the expected `BackendSpec` fragment (features,
parameters, and, where relevant, roles, entities, buckets, edge functions).

**Honesty note on the dataset.** The expected specs began as *engine-pinned*
regression truth and went through three corrections to become the scoring
gold: (1) blind human annotation of all 50 inputs; (2) clash adjudication
of 77 disputes (final tally **48 `engine-wrong` / 21 `both-defensible` /
8 `annotator-misread`**); (3) a mechanical no-anchor linter whose 136
candidates received human batch rulings, removing **60 further items:
39 unpinned `authentication` claims and all 16 edge functions** (no
sentence in the corpus mentions webhooks). Disclosures, all load-bearing.

**Two annotators.** The corpus was annotated twice: annotator 1
(the system author, first pass) and annotator 2 (project-aware, but
blinded to all gold materials: fresh blank worksheets only). Inter-
annotator agreement: raw 74.3% on features, Cohen's κ = 0.16 (roles
−0.23, buckets −0.55); the low κ is dominated by vocabulary and taxonomy
skew; after synonym normalization, only **35 genuine disagreements**
remained across 50 cases. Those 35 rows received human reconciliation
rulings (27 upholding annotator 1, 8 taking annotator 2), producing the
**final three-reading gold** every §5 number is reported against.

**LLM-annotator sensitivity check.** To probe the gold's conventions
from outside the author's head, a disclosed LLM annotator was run three
times over the corpus with identical worksheets and varying roles
instructions (`tests/annotation/llm_annotator*/RESULTS.md`): generic
wording and a "distinct capabilities" wording both failed to reproduce
the gold's roles convention (exact roles-list match 0.44), and mining
the convention into an explicit synonym-mapping rubric raised it to
0.96 — establishing that the roles dimension is definitional (a mapping
table, now normative for annotators, `tests/annotation/external/
ROLES_RUBRIC.md`) rather than a judgment disagreement. The check is
reported as evidence about the gold's conventions, not as validation of
the gold; independent human annotation under supervised, AI-free
conditions remains future work.

**Remaining limitations, stated plainly.** (a) The reconciliation was
performed by the same person who annotated first and built the system;
a full third-party reconciliation of the 35 rows has not run (agreement
coverage itself is complete: annotator 2 re-annotated all 50 cases
blind). (b) Phrase rules and aliases were developed against this same
corpus, a train/test contamination on the compiler side that mirrors the
baselines' zero-shot disadvantage; the held-out 15 were scored once and
the rules were never edited after that scoring, but a corpus authored by
a third party remains future work. Further disclosures: the first
self-adjudication's 41:3 skew was revised: the independent third reader,
working from pre-filled verdicts **with side labels visible**, flipped 21
rulings in both directions; `both-defensible` items are scored on the
annotator side (the scorer has no neutral state); agreement-on-wrong bias
(annotator and engine agreeing on an unmentioned feature, invisible to
clash review) was found (e.g. `authentication` in "We need bookings and
messaging") and then **measured**: an independent reviewer, blind on all
required tiers, covered 184/184 rows (zero boilerplate; reasons quoting
sentence words), overturning 0 of 82 prior keeps, confirming all 5 judgment
drops, and disagreeing 4 times: two concurred soft calls (`mixed` read as
a two-inference stack, `verifier` as canonicalization), one self-
contradictory sentence read as ambiguous, and one concurred defect on a
never-ruled row: `kitchen_sink_marketplace` · `roles.role_names = [admin]`
pins admin-only while the sentence names owners, renters, and admins. The
defect sits in a once-scored held-out case and is **held and disclosed by
decision**; mutating a frozen scored set to fix one parameter row was
ruled not worth breaking the score-once protocol; it is named here and
fixed in the next gold generation. The re-review's blind attestation was
corrected post-hoc (original negative → confirmed positive after the
reviewer's edit and content corroboration); the full trail is in
`tests/annotation/AGREEMENT_REVIEW_VALIDATION.md`. Held-out cases were
scored exactly once, after measurement code and gold were frozen, and
after the fixtures' engine-era operator answers were re-derived from the
human gold itself, removing the operator-answer contamination that had
inflated hallucination counts in an intermediate measurement round (§5.1).
This
stance follows the code-generation evaluation literature's own correction:
benchmark saturation deflated under rigorous testing on EvalPlus [@liu2023evalplus] and ClassEval [@du2023classeval], and real-repository tasks remain
near-unsolved on SWE-bench [@jimenez2024swebench]; weak gold over-claims,
which is precisely what the annotation rounds here repaired.

### 4.2 Baselines

Five baselines; their harness states today:

1. **End-to-end LLM direct-to-SQL** (*measured*). `DirectSqlBaseline`
   prompts a Gemini / OpenAI / Anthropic model (or any OpenAI-compatible
   gateway; §4.4) for a Supabase migration and
   scores artifact-level CREATE TABLE presence against the case's gold
   entities. Measured 50/50 (§5.1) through an OpenAI-compatible gateway.
2. **LLM → `BackendSpec` → same composer** (*measured*).
   `BackendSpecBaseline` prompts the model
   (bounded to the ontology vocabulary) for a `BackendSpec` JSON, parses it,
   runs it through the *same* `recompute_spec` and fragment composer as
   Mechanism C's output, and scores with the same fidelity metrics,
   isolating the contribution of the IR from the generator. Measured 50/50,
   45 parseable (§5.1). The parse → spec → score
   path is unit-tested offline with injected completers.
3. **Rules-only** (*measured*; §5.2, mechanisms `A+B`).
4. **Laya-only** (*measured*; §5.2, mechanism `C`, mock persona).
5. **DbSmash / off-the-shelf generator**: measured through its
   non-interactive CLI path (table R / P 0.081 / 0.179, §5.1); the
   in-compiler adapter surface reports `skipped` by design for external
   tools, matching the e2e tier's behavior.

### 4.3 Metrics

All metrics are computed from the golden labels (§4.1) against the spec a
configuration produces (`tests/experiments/metrics.py`, runnable via
`python -m tests.experiments.run_ablation`):

- **Feature precision / recall** over the *positive* class (feature
  enabled): `precision = TP / |predicted enabled|`, `recall = TP /
  |gold enabled|`. A case with no gold-enabled features (pure-negation case)
  scores 1.0 iff nothing was enabled.
- **Silent-omission rate** (R1's primary endpoint) and **hallucinated-feature
  count** = `|gold enabled \ predicted|` and `|predicted \ gold enabled|`;
  the second is the artifact-level instance of the hallucination taxonomy
  [@ji2023survey].
  Note the asymmetry: the golden suite's partial submatch (`spec_matches`) asserts
   presence but *cannot* catch additions; the precision half of this metric
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
byte-for-byte (`ablation.jsonl` is committed). Statistics: exact McNemar on
paired per-case omission / hallucination outcomes, Wilcoxon signed-rank on
per-case continuous metrics, percentile bootstrap CIs, n = 35.
**Protocol as designed vs. as executed.** The baseline protocol was
designed to pin model versions (`gpt-4o`, `claude-sonnet-4-20250514`)
with ≥ 3 seeds and a paired per-requirement comparison. As executed,
budget constraints reduced the LLM→spec baseline to a **single zero-shot
run through one OpenAI-compatible gateway**
(`antigravity/gemini-3.8-flash-tiered`), scored once and never re-run
after gold corrections; its pinned outputs were re-scored against each
corrected gold (§5.1). The baseline comparison is therefore reported as
indicative point estimates under the disclosed parse convention, not as a
seed-averaged significance result; the significance machinery runs on the
committed paired compiler rows. The default Laya
behaviors under measurement are the shipped mock personas; real-checkpoint
measurements replace the persona on the same cases in the same JSON schema
(R3, §5.3). `laya-typed-decisions` is intentionally out of scope (DoD #22).

## 5. Results

### 5.1 → R1. Fidelity vs. baselines

**Measured against cleaned human gold (2026-09-30).** The gold went through
three corrections: clash adjudication (48/21/8 of 77 disputes), a no-anchor
linter pass whose rulings removed 60 more items (39 `authentication` pins,
all 16 edge functions, 5 others; every edge function is now absent from
gold, since no sentence in the corpus mentions webhooks), and a batch
human ruling on the linter's candidates (`LINTER_RULINGS.md`, 82 keep /
54 drop + 6 consistency). Baselines ran zero-shot through an
OpenAI-compatible gateway (`antigravity/gemini-3.8-flash-tiered`);
dbsmash through its non-interactive path. Parse counts: the baseline emitted parseable specs for 45 of 50 inputs in the original pinned run; 32 of those fall in the golden 35 (13 in held-out); the baseline was never re-run, its pinned outputs were only re-scored against the corrected gold.

**Claim structure.** Two questions, two tables. *Unaided
interpretation* (operator-free compiler vs zero-shot baselines) asks
what the system does when nobody supplies answers: the honest basis
for comparison against the LLM. *Compile-faithfulness*
(oracle operator: MCQ answers taken per the gold) asks whether the
pipeline builds exactly what the gold specifies: an upper bound on the
pipeline, not a baseline comparison.

**Unaided interpretation (golden 35; operator-free compiler vs zero-shot baselines).**

| System | pooled R / P | omissions | hallucinations |
|---|---|---|---|
| LLM → spec → same composer (n=32 parsed) | 0.906 / 0.850 | 6 | 10 |
| Compiler hybrid, MCQ-off (operator-free) | 0.807 / 0.939 | 11 | 3 |
| Compiler rules, MCQ-off (operator-free) | 0.667 / 1.000 | 19 | 0 |
| LLM → direct SQL (table R / P) | 0.419 / 0.268 | — | — |
| dbsmash CLI (table R / P) | 0.081 / 0.179 | — | — |

**Compile-faithfulness (golden 35, cleaned human gold; oracle operator).**

| System | pooled R / P | omissions | hallucinations |
|---|---|---|---|
| **Compiler rules + MCQ** | **1.000 / 1.000** | **0** | **0** |
| **Compiler hybrid + MCQ (real ckpt)** | 1.000 / 0.949 | 0 | 3 |
| **Compiler hybrid + MCQ, refit T = 1.40** | 1.000 / **0.982** | 0 | **1** |

Parse convention: the spec baseline emitted parseable specs for 45 of 50
inputs in its single pinned run (32 within the golden 35); unparseable
outputs are excluded from the metric means and reported as the parse rate
; a stricter convention would score them as total omission, which moves
every baseline number down, never up. The baselines were never re-run;
their pinned outputs were re-scored against each corrected gold.

**Read this table with the significance results (exact McNemar on paired
per-case outcomes, Wilcoxon signed-rank on per-case recall, percentile
bootstrap CIs, n = 35):** with the oracle operator, rules + MCQ is
*perfect*:
no statistical difference exists between hybrid and rules on recall
(Wilcoxon p = 0.617; pooled recall difference +0.000, CI [0.000, 0.000]);
the hybrid's residual hallucinations (3 cases) are not significant at
case level (exact McNemar p = 0.250); the pooled precision difference is
−0.050 with CI [−0.117, +0.000] touching zero. The only interval
excluding zero in the compiler's favor is the **operator-free recall
lift** (MCQ-off: hybrid 0.807 / 0.939 pooled vs rules 0.667 / 1.000;
recall-lift CI [+0.049, +0.261], Wilcoxon p = 0.421, suggestive, not
conventionally significant at n = 35). The strong form of R1 that
survives: **with an oracle operator, the pipeline reconstructs the gold
perfectly, deterministically, and deploys**: a reconstruction result;
it scores faithful compilation of a specified spec, not unaided
interpretation. The honest comparison against the LLM baseline is the
operator-free one, and it is a trade-off at the point estimates: the
compiler wins precision (0.939 vs 0.850) and hallucinations (3 vs 10);
the baseline wins recall (0.906 vs 0.807) and omissions (6 vs 11).

Composition-side determinism is unchanged: the delivered `BackendSpec`
compiles to SQL that applies cleanly twice across the 595-pair fragment
matrix on live PostgreSQL 15, byte-identically for identical input (§3.5).

### 5.2 → R2. Ablations (mechanism subset × MCQ on/off)

Two measurement settings, one corpus: the mock personas first (the
contract-test setting the golden suite pins), then the real checkpoint
(`python -m tests.experiments.run_ablation --real-laya`; summaries in
`tests/experiments/results/ablation_summary.md` and
`ablation_real_summary.md`). Mock-persona ablation:

Table: Mock-persona ablation across ten mechanism configs (golden 50; feature-exact out of 50, MCQ count and runtime are means).
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
   residual question burden is low (~6.5–6.9 questions per input for the
   human-answerable configs, 2.34 for the interpretation-only floor), which
   is the case for the always-ask-vs-auto-accept trade (§6).
2. **Mechanism A (aliases) is a parameter supplier, not a feature detector.**
   Alone it decides nothing (pooled recall 0.000 without MCQ) but lifts
   parameters from 19/26 to 25/26 when added to B (provider, auth-method,
   and lifetime params arrive only via exact matches.
3. **Mechanism B (phrases) is the workhorse** on its own vocabulary: 0.922
   pooled recall with MCQ, zero hallucinations, 48/50 feature-exact. This
   corroborates the R2 risk: on a bounded vocabulary rules carry
   most of the load.
4. **Mechanism C contributes exactly the residual, and that contribution has
   two faces.** The hybrid's superiority over rules-only (0 omissions vs 10,
   pooled recall 1.000 vs 0.922, 26/26 vs 25/26 params) is entirely carried
   by the two `high`-persona cases, where features exist in the gold spec
   that *no rule and no alias can see*: mechanism C genuinely extends
   coverage. But the same two cases produce all 8 hallucinations: the
   model proposes *every* capability at 0.95, and (this is the important
   part) the golden suite's partial submatch does not catch the additions,
   while the precision metric does (`laya_high_decides` enables ten
   features for an input that names two). Under the design, this is R3's
   job: 0.95 *raw* confidence must not survive as 0.95 *answer_confidence*
   where the model is wrong (§5.3).

**Real-checkpoint rerun: same corpus, same gold, the real `english` model**
(`python -m tests.experiments.run_ablation --real-laya`; rows in
`tests/experiments/results/ablation_real_summary.md`). The rule-only rows
reproduce the table above byte-identically (they never touch the model)
which isolates exactly what changes when the persona becomes the checkpoint.
Three states were measured:

*Unfixed (checkpoint swapped in, harness as shipped):*

| Config | macro R / P | pooled R / P | omissions | hallucinations | feature-exact | MCQ count (mean) |
|---|---|---|---|---|---|---|
| A+B+C hybrid + MCQ | 0.794 / 0.858 | 0.721 / 0.912 | **36** | 9 | 27/50 | 2.90 |

*Fixed (two defects found by this rerun, each TDD'd):*

| Config | macro R / P | pooled R / P | omissions | hallucinations | feature-exact | MCQ count (mean) |
|---|---|---|---|---|---|---|
| C only (Laya) + MCQ | 0.730 / 0.858 | 0.651 / 0.903 | 45 | 9 | 20/50 | 6.98 |
| A+B+C hybrid + MCQ | 0.912 / 0.898 | **0.922 / 0.930** | **10** | 9 | 39/50 | 6.70 |
| A+B+C hybrid (no MCQ) | 0.404 / 0.453 | 0.481 / 0.873 | 67 | 9 | 2/50 | 2.74 |

5. **The unfixed rerun falsified the persona headline, and the harness was
   at fault, not just the model.** Swapping the checkpoint in dropped
   hybrid+MCQ from 0 omissions to 36 while rules+MCQ held at 10, and the
   excess traced to a real merge defect: candidates grouped by raw
   `capability_id`, so a laya `needs_payments` twinned a rule
   `payments.enabled` into the fold, whose distinct-value check fired a
   spurious negation and undecided the rule's correct positive. The claimed
   tier protection (§3.3) was not real at the feature level; the mock
   personas never exposed it because their 0.5-confidence answers never
   cleared the fold's threshold. Fixed by grouping merge on the normalized
   feature target (`needs_X` ≡ `X.enabled`).
6. **The second defect was the symmetric negative gate.** A laya "no" at
   `answer_confidence >= 0.75` decided features *off*, suppressing the
   clarifying question (measured: question burden 6.98 → 2.36 with the gate
   removed). The fix is asymmetric: laya-sourced negatives never auto-decide
   off: the loop asks; rules keep deciding off. With both fixes,
   **hybrid+MCQ recovers to rules-parity: 0.922 pooled recall, 10 omissions**
   (from 36), and the model's yes-side still lifts no-MCQ recall
   0.419 → 0.481.
7. **The calibration refit closes most of the remaining gap, measured.**
   Two wiring fixes let the §5.3 fit reach the fold: `candidates_from_laya_response`
   now consumes the client's *calibrated* confidence (the ECE-gated
   quantity), and the client honors a run-scoped `LAYA_TEMPERATURE`
   override (shipped behavior stays pass-through T = 1.0 per the gate).
   With the fitted T = 1.40: hybrid+MCQ hallucinations **9 → 4**, precision
   **0.930 → 0.967**, feature-exact **39/50 → 44/50**, at unchanged recall
   and omissions (`results/ablation_real_fit_summary.md`). Softening
   over-confident yes-answers below the 0.75 auto-accept bar converts them
   back into questions: the MCQ backstop absorbing exactly the decisions
   calibration does not trust.

**Compile-faithfulness (cleaned human gold, oracle operator): the pipeline
reconstructs the gold exactly.** Re-measured after the full gold cleanup (48/21/8 clash
adjudication + 60 linter-ruling removals) *and* the operator-answer
re-derivation (golden 35, real checkpoint):

Table: Compile-faithfulness on the golden 35 (oracle operator, real checkpoint)

| Config (golden 35) | pooled R / P | omissions | hallucinations |
|---|---|---|---|
| **rules + MCQ** | **1.000 / 1.000** | **0** | **0** |
| hybrid + MCQ | 1.000 / 0.949 | 0 | 3 |
| hybrid + MCQ, refit T = 1.40 | 1.000 / **0.982** | 0 | **1** |
| hybrid, MCQ-off (operator-free) | 0.807 / 0.939 | 11 | 3 |
| rules, MCQ-off (operator-free) | 0.667 / 1.000 | 19 | 0 |

Table: Compile-faithfulness on the frozen held-out 15 (scored once)

| Config (held-out 15, scored once, frozen) | pooled R / P | omissions | hallucinations |
|---|---|---|---|
| **rules + MCQ** | **1.000 / 1.000** | **0** | **0** |
| hybrid + MCQ | 1.000 / 0.926 | 0 | 2 |
| hybrid + MCQ, refit T = 1.40 | 0.933 / 0.911 | 0 | 2 |
| hybrid, MCQ-off (operator-free) | 0.800 / 0.909 | 5 | 2 |

8. **The oracle-MCQ result is a reconstruction result, and it belongs to
    rules + MCQ:** with the operator answering exactly per the adjudicated
    gold, the rule layer plus clarification reproduces the gold with
    nothing invented and nothing omitted, in-sample and on the frozen
    held-out set. This measures compile-faithfulness of a specified spec
    (§7), not unaided interpretation; the operator-free rows above are the
    interpretation numbers. Statistics (n = 35): rules vs hybrid recall shows no
    significant difference (Wilcoxon p = 0.617; pooled difference +0.000);
    the hybrid's residual hallucinations are not significant at case level
    (exact McNemar p = 0.250); no between-config interval excludes zero.
9. **The model slot's measured value is operator-free recall lift, and
   nothing else.** MCQ-off, the checkpoint lifts pooled recall 0.667 →
   0.807 (lift CI [+0.049, +0.261], Wilcoxon p = 0.421) while adding 3
   hallucinations; MCQ-on with a clean operator, it adds 2-3
   hallucinations and no recall. The R2 strong form is therefore
   architecture-level, not model-level: tiered interpretation plus
   clarification achieves perfect fidelity, the protective design makes
   the model slot safe to include (refit hybrid: 1.000 / 0.982, one
   hallucination), and the calibrated checkpoint is strictly optional.
10. **Against the spec baseline (§5.1) the compiler sweeps the point
     estimates on precision and hallucinations** (1.000 / 1.000 vs
     0.906 / 0.850, zero hallucinations vs ten), with the significance
     caveat above applying to compiler-vs-compiler gaps, not to the
     40-point gaps against the baseline. Operator-free, the picture
     inverts on omissions: the hybrid's 11 trail the baseline's 6. The
     honest baseline comparison is a precision-for-omissions trade-off,
     not a sweep.

### 5.3 → R3. Calibration and the auto-accept gate

**Measured (real `english` checkpoint; both golds, then cleaned gold).**
This gate matters because code LLMs are in fact badly miscalibrated (
token probabilities diverge from functional correctness across models and
benchmarks [@spiess2025calibration]), and our auto-accept
threshold gates deployment on exactly that quantity. With the vendored
`laya` 0.3.20 installed in the venv (torch 2.14 CPU,
transformers 5.17) and the pinned `english` checkpoint (421M ModernBERT,
fetched from the Hub), Mechanism C's actual noul questions ran on all 50
golden cases; each feature-item answer yields one
`(answer_confidence, label)` pair: **500 pairs** per gold setting.
Against the engine-pinned gold: accuracy 0.784, ECE 0.0951 (gate PASS,
fit 0.0425 @ T = 1.40). Against the first human gold: 0.824 / 0.0727.
Against the **fully cleaned** gold (clash adjudication + linter-ruling
removals): **accuracy 0.896, ECE 0.0381, gate PASS, fit 0.0208 @
T = 0.88**. Each cleanup raised the model's measured accuracy and lowered
its ECE: most of what earlier rounds called model miscalibration lived in
the labels.

- **Raw ECE = 0.0951 < 0.1, so the §3.6 gate passes** on the shipped
  `answer_confidence` (the vendor benchmark reports 0.175 for this
  checkpoint on typed decisions; this task's binary noul questions
  calibrate better). The committed gate fixture is now these 500 measured
  pairs, so the gate test measures the model, not a hand-authored set.
- The temperature fit moves 0.0951 → **0.0425 at T = 1.40**, inside the
  vendor's [0.5, 5.0] clamp, unlike the earlier synthetic demo's boundary
  T = 10.0. Per the spec's decision rule (fit only when the gate fails),
  the shipped `calibration.json` stays at pass-through T = 1.0, and the
  refit's *downstream* value is now measured too: with T = 1.40 applied,
  hybrid+MCQ hallucinations halve (9 → 4) at unchanged recall (§5.2,
  finding 7).
- **Auto-accept sweep:** at the shipped 0.75 threshold, 87.8% of decisions
  auto-accept at **80.0% correctness** among them; the curve peaks at 0.85
  (70.6% coverage, 82.4% correctness) and decays by 0.95 (18.6% coverage,
  78.5%): the highest-confidence bin is not the most accurate, so raising
  the threshold is not monotonically safer. The §6 coverage-vs-correctness
  question now has a measured curve
  (`tests/experiments/results/calibration_summary.md`).

**Honesty note.** Labels are scored against the **cleaned, reconciled
human gold** (three readings; two independent annotators; 35
reconciliation rulings; see §4.1), not the engine-pinned regression
expectations, and the held-out 15 were scored once after freezing. The
§5.2 hallucinations are no longer *uncalibrated* (the checkpoint's
confidence has a measured ECE of 0.0381 on this gold, gate PASS), and
the claim-grade R3 caveat is now narrower: an independent third-party
reconciliation of the 35 disagreement rows has not run, and the
annotators are not independent of the system's rule author.

### 5.4 End-to-end (secondary)

**Measured: three e2e sessions, all first-attempt success.** Deployment is
where generative approaches measurably collapse: on cloud
infrastructure-as-code tasks the best LLM reaches 19.36% pass@1 against
86.6% on ordinary Python IaC-Eval [@kon2024iaceval], which is why this
pipeline deploys by deterministic API compilation instead. Each session
performs three deployment operations against a real, subsequently
torn-down project (marketplace compile+deploy, minimal-spec deploy,
idempotent re-deploy). With a real
organization configured (`SUPABASE_ACCESS_TOKEN` + org slug, loaded from
`.env`), the e2e tier created a project through the Management API, applied
29 generated migrations with the CLI, configured auth, deployed two edge
functions, and then verified the live database directly: the
`listings`/`bookings`/`messages` tables and the `listings` storage bucket
exist, and the project is torn down afterwards. Wall clock from project
creation to verified tables was **39 s** in the first session (n=1 for
that single-operation timing). The interpreter ran against
the mock Laya persona, so this measures deployment, not model latency; the
organization is free-tier, so the marginal monetary cost is $0. All three
sessions (9 deployment operations) succeeded first-attempt, and a
dedicated 10-session deployment battery (30 deployment operations across
fresh projects, sequential create → deploy ×3 → verify → teardown)
succeeded **30/30**, a first-attempt success rate of 1.000 with Wilson
95% CI [0.886, 1.000] (`results/e2e_battery.jsonl`): the deployability
claim is now a measured rate, not an anecdote.

**Deployment is API-drift sensitive.** First contact with the live API
surfaced five breaks that no mock could have caught, each fixed in the
deployer or the e2e tier: (1) `region_selection.code` now accepts only smart
groups (`americas` | `emea` | `apac`), not city codes such as
`ap-southeast-1`; (2) `/health` reports nothing unless its repeated
`services` parameter is supplied, and answers with an error object rather
than a list when it is missing, so the poller now shape-checks its payload;
(3) `npm install -g supabase` exposes only a `.cmd` shim, which Windows'
`CreateProcess` cannot execute, so every CLI call now goes through a
resolver that prefers a real executable; (4) `functions deploy` bundles with
Deno inside Docker and must reach `esm.sh`, which restricted networks block,
so functions deploy with `--use-api` (server-side bundling); (5) the
`database/query` endpoint is POST-only. Deployment claims that have not been
executed against a live account should be read as untested in this respect -
mock-based deployer coverage cannot see any of it.

## 6. Discussion

**The MCQ burden is the price of zero omission, and the curve now exists.**
Interpretation alone reaches pooled recall 0.496 on these 50 inputs; the
clarification loop closes the remaining 54% of recall at a cost of ~6.5
questions per input (human-answerable). The measured coverage-vs-correctness
curve (§5.3) prices the alternative: at the shipped 0.75 auto-accept, 87.8%
of model decisions skip the question but only 80.0% of them are right:
one in five auto-accepted decisions is wrong, far from the ≥ 99% agreement
that would make the marginal questions "residual ambiguity users actually
have". The measured curve says the opposite: on this checkpoint and corpus,
auto-accept buys question-removal by selling correctness, and the 2.34
questions per input of the no-MCQ floor are doing real work. A checkpoint
refit (T = 1.40 halves ECE to 0.0425) or better annotation may move the
trade, but the current numbers argue for asking.

**Rules win the bounded vocabulary; calibration is what makes the model
pay.** On 48/50 cases rules+aliases alone reconstruct the spec (0.922
pooled recall, zero hallucinations). The checkpoint rerun (§5.2, findings
5–7) first falsified the persona headline, then traced the loss to two
harness defects (merge twinning, symmetric negative gate), both fixed;
the model reached parity. The final measured step is calibration: with the
§5.3 refit applied, hybrid+MCQ holds rules-parity on recall while
hallucinations halve (9 → 4, precision 0.967). The architecture's promise (
a protected model slot, an MCQ backstop, and ECE-gated confidence gating
the slot) is now measured end to end: in-sample, the refit halves
hallucinations, but the held-out refit degrades (0.933 / 0.911 vs
1.000 / 0.926), so the shipped configuration keeps T = 1.0, and the
remaining route (fine-tuning) is scoped by the same harness.

**The golden evaluation has a blind spot this setup exposes.** `spec_matches`
checks that expected values appear in the output; it cannot flag
output the gold set doesn't name. Eight hallucinated features passed the
golden suite and were caught only by the experiment tier's precision half.
Two consequences: (i) golden expectations should gain absence pinning
(the empty-`features` convention the metrics module implements), and (ii)
the paper must treat precision and recall as equally first-class; a purely
recall-driven metric on this corpus would over-credit an over-confident
model.

**Where the layered design loses.** Rule and alias tables are finite; a
paraphrase outside both the phrase rules and the ontology vocabulary falls
to the model, and if the model is below the majority-class baseline (vendor
benchmarks), fallback is MCQ or silence-flagging. The never-silently-omit
invariant is preserved structurally (unparsed sentences become
`clarify_unparsed`), but the *precision* of that guarantee scales with the
rule tables and the calibrated coverage, never with raw generation. That
is the paper's central trade, and it is the R1 sub-clause worth stating
loudest: unsupported requirements are flagged, not guessed.

## 7. Threats to Validity

**Construct.** The headline 1.000 / 1.000 is obtained with operator
answers re-derived from the same gold: oracle-MCQ reconstruction,
measuring whether the pipeline compiles a specified spec faithfully, not
not whether it interprets unaided English (§5.1, §5.2). The gold itself
is author-curated: annotator 1 is the system author, reconciliation of
the 35 synonym-normalized disputes was performed by the same person
(27:8 in annotator 1's favor), raw feature agreement is κ = 0.16 (roles
−0.23, buckets −0.55), the third clash reader worked from pre-filled
verdicts with side labels visible, and a full third-party reconciliation
has not run (§4.1). *Verified* would overstate this process;
*dual-annotated, author-reconciled* is the accurate label.

**Internal.** Phrase rules and aliases were developed against the same
corpus they are scored on, compiler-side train/test contamination that
mirrors the baselines' zero-shot disadvantage. The held-out 15 were
scored once under the score-once protocol and the rules were never
edited after, but the same author wrote both splits. One known held-out
parameter defect is held and disclosed by decision rather than fixed.
Agreement-on-wrong bias (annotator and engine concurring on an
unmentioned feature) is invisible to clash review and was found at
least once (§4.1).

**External.** One ontology of ten features, one platform, 50
author-written inputs: the corpus establishes vocabulary coverage, not
paraphrastic or third-party language. The deployment battery (30/30)
measures repeated-operation deployer reliability, not NL diversity.

**Statistical.** n = 35 scored pairs: no compiler-vs-compiler difference
is significant (Wilcoxon p = 0.617; exact McNemar p = 0.250), and the
model's operator-free recall lift is suggestive only (p = 0.421, CI
[+0.049, +0.261]). Baseline gaps are 40+ points wide but rest on a
single zero-shot run of one gateway model with unparseable outputs
excluded (§4.4); no seed averaging.

**Baseline.** The LLM→spec baseline is bounded to the ontology vocabulary
at the prompt level and reuses the same composer (§4.2), but it is not
grammar-constrained at decoding time; a decode-time constrained
generator remains future work. The baseline saw no clarification loop,
and its single zero-shot run (§4.4) makes the comparison indicative
point estimates rather than a seed-averaged significance result.

## 8. Conclusion

The layered compiler ships and is measured end to end against a cleaned,
adjudicated human gold with an oracle-operator protocol: natural
language in, a typed `BackendSpec` and a deployed Supabase project out.
What survives, claim by claim:

**R1/R2 (fidelity and architecture).** Under the cleaned gold **with
oracle operator answers**, the
rules-plus-clarification configuration is **perfect: 1.000 recall,
1.000 precision, zero omissions, zero hallucinations**, in-sample and on
the frozen held-out set. That is a reconstruction result: it establishes
that the pipeline faithfully compiles a specified spec. The decision-model slot is measured to be
strictly optional there (it adds 2-3 hallucinations with no recall gain);
its measured value is operator-free recall lift (rules 0.667 → hybrid
0.807 golden; 0.615 → 0.769 held-out), and the calibration refit is not
shipped (it degrades held-out). Operator-free, the comparison against
the LLM baseline is a trade-off: precision and hallucinations favor the
compiler, recall and omissions favor the baseline (§5.1). The
architecture protects its model slot; the operator protocol makes the
rule layer sufficient.

**R3 (calibration).** The shipped confidence passes the ECE < 0.1 gate
under every gold generation (0.0951 engine, 0.0727 first human,
0.0381 cleaned, accuracy 0.896), with a fit at an enforceable temperature
(T = 0.88). Each gold cleanup raised the model's measured accuracy
and lowered its ECE: most of what earlier rounds called model
miscalibration lived in the labels, and the gate now measures a
well-calibrated checkpoint.

**Baselines.** On the same golden cases, the operator-free compiler wins
precision and hallucinations at the point estimates (0.939 / 3 vs the best
zero-shot LLM→spec baseline's 0.850 / 10, direct-SQL table recall 0.419,
dbsmash 0.081), while the baseline wins recall and omissions (0.906 / 6 vs
0.807 / 11): a precision-for-omissions trade-off against a single zero-shot
run (§4.4, §7). Under the oracle protocol the rules-plus-MCQ configuration
reaches 1.000 / 1.000, but that is a reconstruction bound, not a baseline
comparison, and no compiler-vs-compiler difference is significant at n = 35.

**Deployment.** A 10-session deployment battery (30 operations across
fresh projects: marketplace, minimal, idempotent re-deploy) succeeded
**30/30 first-attempt** (rate 1.000, Wilson 95% CI [0.886, 1.000]) at
56-111 s per session, with five live-API drift points found and fixed
along the way.

**Honest costs.** The gold took three corrections and still carries two
disclosed limits: the gold's correction chain involved the same person
as annotator, first adjudicator, and reconciler (the independent third
reader flipped 21 of 77 clash rulings; a second annotator then re-
annotated the full corpus, and the 35 synonym-normalized disagreements
were reconciled into the final gold with Cohen's kappa = 0.16 raw on
features, dominated by vocabulary skew), and the phrase rules were
developed against this same corpus (compiler-side train/test
contamination, the mirror of the baselines' zero-shot disadvantage). The compiler's
perfect score is achieved with operator answers derived from that same
gold; the circularity is deliberate and disclosed: the claim is that the
pipeline faithfully compiles what the human gold specifies, and the
remaining open question is how the human gold itself generalizes. Every
number carries its setting, and every number regenerates from committed
artifacts.

## Declarations

**CRediT author statement.** **Nafis Rayan:** Conceptualization, Methodology,
Software, Validation, Formal analysis, Investigation, Data curation,
Writing – original draft, Writing – review & editing, Visualization, Project
administration.

**Funding.** This research did not receive any specific grant from funding
agencies in the public, commercial, or not-for-profit sectors.

**Declaration of competing interests.** The author declares no competing
interests.

**Declaration of generative AI and AI-assisted technologies.** During the
preparation of this work the author used opencode, an AI coding agent running
Gemini and GLM models, to assist with software implementation and to touch up
the manuscript's prose. Figures 1 and 2 were produced with AI
image-generation tools from the author's designs and then edited by the
author; all technical content they depict is the author's, and each
figure caption states this provenance. After using these tools the author reviewed and edited
all output as needed and takes full responsibility for the content of the
published article.

**Acknowledgments.** The author thanks the independent annotator
(re-annotation of all 50 corpus cases, §4.1) and the independent third
reader (clash-adjudication review and the 184-row agreement re-review,
§4.1) for their validation contributions to the gold-correction process.
The two peer annotation returns collected and excluded by provenance
analysis are discussed in §4.1; their submitters are not acknowledged as
contributors. The author additionally thanks the Shandong University
journal press and the maintainers of the laya repository for the
checkpoint infrastructure underpinning the mechanism-C measurements
(pinned `english` checkpoint, 421M ModernBERT).

**CRediT author statement note.** Validation and annotation work
described in §4.1 was shared between the author and the independent
contributors acknowledged above; the named CRediT statement reflects the
author's roles as the sole accountable author.

**Data and code availability.** Every number in this paper regenerates from
the public replication package at
https://github.com/NafisRayan/laya-bounded-english-compiler (archived at
https://doi.org/10.5281/zenodo.23942698):
the 50-case golden corpus (`tests/golden/cases/`), the YAML ontology, the
alias and phrase-rule tables, the annotation worksheets and reconciliation
rulings (`tests/annotation/LINTER_RULINGS.md`), the operator-answer
re-derivation procedure, the paired compiler rows and baseline outputs
(`tests/experiments/results/ablation.jsonl`), and the deployment-battery
logs (`tests/experiments/results/e2e_battery.jsonl`). The offline tier
(unit, golden, and the ablation harness) runs with no credentials:
`pytest tests/unit tests/golden -q` passes 505 tests, and
`python -m tests.experiments.run_ablation` regenerates the §5.2 table.
