# Laya Supabase — natural language in, deployed Supabase app out

## TL;DR

A deterministic, ontology-bounded compiler: you describe a backend in
plain English, it produces a typed `BackendSpec` (validated against a
fixed vocabulary), composes pre-tested SQL/RLS/auth/storage fragments,
and deploys the result to a real Supabase project — with a human-in-the-loop
question flow so nothing is ever silently omitted.

The research question it answers: **does a layered compiler beat
end-to-end LLM generation on fidelity?** Measured answer (human-verified
gold): yes, by a wide margin — pooled recall **0.952 / precision 0.911**
for the full pipeline vs **0.608 / 0.815** for the strongest LLM baseline,
with 4 missed requirements per 35 cases vs 44. Full write-up:
[`Paper.md`](Paper.md). Evidence ledger: [`Paper Outline.md`](Paper%20Outline.md).

## Quick start

```powershell
cd backend-compiler
py -m venv .venv
.\.venv\Scripts\pip install -e ".[dev]"
copy .env.example .env        # fill in the keys you have (see Configuration)

.\.venv\Scripts\python.exe -m pytest tests\unit tests\golden -q    # 60s, offline, no keys
```

If that passes you have a working install. Everything else below is a
menu — each system runs independently.

---

## What the codebase is

```
backend-compiler/
├── compiler/                  # the product (pure Python, no torch required)
│   ├── interpreter/           # NL → candidates: 3 mechanisms + merge
│   │   ├── aliases.py         #   A: exact alias matches ("stripe" → payments.provider)
│   │   ├── rules.py           #   B: phrase rules with regex spans
│   │   ├── negation.py        #   B: sentence-clamped negation detection
│   │   ├── laya_client.py     #   C: the Laya 421M decision model (optional at runtime)
│   │   ├── merge.py           #   tiered conflict resolver: exact > phrase > laya
│   │   ├── calibration.py     #   ECE math + temperature fitting
│   │   └── pipeline.py        #   run_interpreter(text, ontology, laya, mechanisms)
│   ├── mcq/                   # the clarification loop
│   │   ├── pipeline.py        #   run_mcq_loop: fold candidates, surface questions
│   │   ├── selector.py        #   which questions to ask next (dependency-ordered)
│   │   └── thresholds.py      #   AUTO_ACCEPT = 0.75, the auto-accept gate
│   ├── spec/                  # the typed intermediate representation
│   │   ├── models.py          #   BackendSpec / Candidate / PartialSpec
│   │   ├── derive.py          #   entities/buckets/edges derived from features
│   │   └── validator.py       #   dependency + type + contradiction checks
│   ├── generator/             # spec → SQL/RLS/auth/storage/edges (Jinja2 fragments)
│   ├── deployer/              # Supabase Management API + CLI orchestration
│   │   ├── supabase_api.py    #   create_project, wait_for_healthy
│   │   ├── deployer.py        #   deploy_spec + deploy_with_remediation (3-attempt loop)
│   │   ├── auth_config.py     #   auth providers via Management API
│   │   └── edge_functions.py  #   function deploy (server-side bundling)
│   ├── ontology/versions/v1/  # the bounded vocabulary (features/params/roles/buckets)
│   ├── mcq/thresholds.py      # the 0.75 auto-accept decision threshold
│   └── api/                   # optional FastAPI wrapper (sessions + interpret/answer)
├── tests/
│   ├── golden/cases/          # 50 fixed NL inputs with expected specs (regression truth)
│   ├── unit/                  # offline component tests (no network, no torch)
│   ├── integration/           # live-Postgres idempotency + 595-pair matrix + ECE gates
│   ├── experiments/           # the measurement harness (ablation/calibration/baselines)
│   │   ├── runner.py          #   run_case: one config through the whole pipeline
│   │   ├── run_ablation.py    #   mechanism × MCQ grid (see below)
│   │   ├── run_calibration.py #   (answer_confidence, label) pairs → ECE → fit → sweep
│   │   ├── run_baselines.py   #   external baselines (LLM spec/SQL, dbsmash)
│   │   ├── personas.py        #   contract-test doubles for the model
│   │   └── results/           #   every measurement ever taken (jsonl + summaries)
│   ├── annotation/            # the human ground-truth kit (worksheets/validator/gold)
│   └── e2e/                   # nightly real deployments (credential-gated)
├── tests/annotation/          # filled worksheets + adjudication + human_gold.yaml
├── .env / .env.example        # local keys (gitignored) / committed template
docs/
├── annotation-protocol.md     # how the human gold was (and can be re-)produced
└── third-reader-review.md     # guide for an independent adjudication reviewer
Paper.md                       # the full research write-up with measured numbers
Paper Outline.md               # claim → experiment → artifact evidence ledger
```

The three interpretation mechanisms are independently toggleable
(`mechanisms="A"`, `"B"`, `"C"`, `"AB"`, `"ABC"`), which is what the
ablation harness sweeps. Mechanism C needs the optional
[laya](https://github.com/convaiinnovations/laya) package and its
checkpoint; without it the compiler still runs on rules + MCQ alone
(the model slot simply stays undecided and the questions get asked).

---

## The systems, in detail

### 1. The compiler pipeline (the product)

Input is a 1–500 word English description. Stages:

1. **Interpret** — three mechanisms extract `Candidate`s (feature on/off,
   parameter values, roles) with confidences, merged tier-first so rules
   outrank the model on overlap.
2. **Clarify** — `run_mcq_loop` folds candidates into a partial spec
   (auto-accepting only confidence ≥ 0.75; model-sourced *negatives* never
   auto-decide off), then surfaces the residue as multiple-choice questions:
   negation conflicts, contradictions, undecided features, unmapped
   sentences (`clarify_unparsed` — the never-silently-omit mechanism).
3. **Specify** — `recompute_spec` derives entities/buckets/edge functions
   from the enabled features; `validate` enforces dependencies (payments
   needs auth), types, and contradiction constraints.
4. **Deploy** — the composer emits idempotent SQL migrations + RLS +
   bucket + edge-function fragments; the deployer creates the Supabase
   project via the Management API, waits for service health, links the
   CLI, applies migrations (`supabase db push`), configures auth, deploys
   edge functions server-side, and can re-run the bounded remediation
   loop (max 3 attempts) on failure.

The FastAPI wrapper (`compiler/api/`) exposes the same pipeline as
`POST /v1/sessions` → `interpret` → `answer` with transactional session
state (a failed pipeline never commits).

### 2. The measurement harness (`tests/experiments/`)

Every claim in the paper regenerates from these CLIs. Common flags:

| flag | meaning |
|---|---|
| `--real-laya` | use the real pinned `english` checkpoint instead of mock personas |
| `--gold engine\|human` | score against the engine-pinned spec or the adjudicated human gold |
| `--split all\|golden\|held_out` | 35 golden / 15 held-out per `tests/golden/splits.yaml` |
| `--device cpu\|cuda` | torch device for the checkpoint |
| `--out` / `--summary` | output paths (defaults land in `results/`) |

**Ablation grid** — every mechanism subset × MCQ on/off, scored on
recall/precision/omissions/hallucinations per gold setting:

```powershell
$py -m tests.experiments.run_ablation                     # mock personas, engine gold
$py -m tests.experiments.run_ablation --real-laya --gold human --split golden
$py -m tests.experiments.run_ablation --real-laya --gold human --split held_out
$env:LAYA_TEMPERATURE = "1.40"                            # optional what-if refit
$py -m tests.experiments.run_ablation --real-laya --gold human            # with refit
```

**Calibration** — runs mechanism C's actual yes/no questions on every
case, then reports decision accuracy, raw ECE, the grid-searched
temperature, post-fit ECE, and the auto-accept coverage-vs-correctness
sweep from 0.50 to 0.95:

```powershell
$py -m tests.experiments.run_calibration --gold human
```

**Baselines** — three external rivals scored on the same corpus:
an LLM emitting a `BackendSpec` through our own composer (isolates the
compiler's value), an LLM writing raw SQL directly, and the off-the-shelf
dbsmash CLI:

```powershell
$py -m tests.experiments.run_baselines --gold human
```

All three runners are **resumable** (rows stream to JSONL; completed
(baseline, case) pairs are skipped on re-run) and deterministic except
where a live model is involved.

### 3. The human ground truth (`tests/annotation/`)

The engine-pinned case expectations are regression truth; the paper's
claim-grade numbers use independently annotated gold:

- `golden/` + `held_out/` worksheets: inputs only, filled blind by a human
- `DISAGREEMENTS.json`: the 142 spots where human and engine gold differ
- `ADJUDICATION.yaml`: each disagreement ruled (`engine-wrong` /
  `annotator-misread` / `both-defensible`), with source-evidence checks
  recorded (final tally 41/33/3)
- `human_gold.yaml`: the merged, adjudicated result — what `--gold human`
  loads
- `validate.py`: `--check` (structure/ontology, blind) and `--score`
  (against gold, after the fact)

Protocol and decision rules: `docs/annotation-protocol.md`. Independent
re-review guide: `docs/third-reader-review.md`.

### 4. The deployment tier (`tests/e2e/`)

A real end-to-end contract test: creates a throwaway Supabase project via
the Management API, compiles the marketplace description, links the CLI,
applies all migrations, configures auth, deploys two edge functions,
verifies the live database (tables + storage bucket), re-deploys the same
spec (idempotency), then deletes the project. Runs on every push to
`master` and on a schedule in CI; locally it needs the Supabase CLI
(`npm i -g supabase`) and `.env` credentials. It self-skips without them.

---

## Configuration (`.env`)

| variable | used by | notes |
|---|---|---|
| `OPENAI_BASE_URL` + `OPENAI_API_KEY` | baselines | any OpenAI-compatible gateway; endpoint is `{BASE_URL}/chat/completions`; takes precedence |
| `OPENAI_MODEL` | baselines | gateway's model id; falls back to `GEMINI_MODEL` |
| `GEMINI_API_KEY` | baselines + dbsmash schema agent | native Gemini REST |
| `GEMINI_MODEL` | baselines | default `gemini-3.5-flash` |
| `OPENROUTER_API_KEY` | dbsmash baseline | its intent agent calls OpenRouter |
| `SUPABASE_ACCESS_TOKEN` / `SUPABASE_ORG_SLUG` | deployer + e2e | personal access token + org |
| `SUPABASE_REGION` | deployer | smart group: `americas\|emea\|apac` (default `apac`) |
| `TEST_DATABASE_URL` | integration tier | postgres:15 URL (CI provides one) |
| `LAYA_DEVICE` | real checkpoint | default `cpu` |
| `LAYA_TEMPERATURE` | real checkpoint | experiment-only refit override (never persisted) |
| `DBSMASH_CMD` | dbsmash baseline | executable override (else resolved from PATH) |

## Dependencies

- Core: Python ≥ 3.11, pydantic, pyyaml, fastapi, requests (`pip install -e ".[dev]"` adds pytest/ruff/mypy/psycopg/httpx)
- Real-checkpoint runs: `torch` (CPU build fine), `transformers`, then
  `pip install --no-deps -e ..\laya` (the vendored library, one level above
  this repo); first use downloads the ~800 MB `english` checkpoint from
  the Hugging Face Hub
- Deployment runs: Supabase CLI (`npm i -g supabase`) and a Supabase org
- dbsmash baseline: `npm i -g dbsmash` + the keys above

## Current measured results (human-verified gold, golden 35)

| system | pooled recall / precision | omissions |
|---|---|---|
| **compiler hybrid + MCQ (real checkpoint)** | **0.952 / 0.911** | **4** |
| compiler rules + MCQ | 0.916 / 0.938 | 7 |
| LLM → spec → same composer | 0.608 / 0.815 | 44 |
| LLM → direct SQL (table-level R / P) | 0.366 / 0.361 | — |
| dbsmash CLI (table-level R / P) | 0.046 / 0.133 | — |

Held-out (15 cases, scored once, frozen): hybrid **0.950 / 0.905** with
2 omissions vs rules 0.900 / 0.947 with 4. Calibration: ECE 0.0727 on the
shipped confidence (gate < 0.1 passes), 0.0560 after refit. Deployment:
first-attempt success, idempotent re-deploy verified. Full detail,
caveats, and the authoring-bias analysis: `Paper.md` §5.

## Testing

```powershell
$py -m pytest tests\unit tests\golden tests\experiments -q    # fast, offline
$py -m pytest tests\integration -q                            # needs Docker (postgres:15)
$py -m pytest tests\e2e -q                                    # needs .env Supabase keys + CLI
$py -m ruff check compiler tests ; $py -m mypy compiler       # lint + types
```

CI runs the first line plus the integration tier on every push (with a
postgres service), and the e2e deployment tier on `master`/schedule.

## Where the research lives

- `Paper.md` — the write-up: methods, all measured tables, limitations
  (self-adjudication COI, gateway model provenance, hybrid hallucination
  cost), and conclusion
- `Paper Outline.md` — the evidence ledger: every claim → experiment →
  committed artifact, plus the risk register
- `Developer Spec.md` — the original system specification the code
  implements (§-references throughout the codebase point here)
