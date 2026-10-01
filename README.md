# Laya Supabase — pick your system

A compiler that turns plain-English app descriptions into a deployed
Supabase project (spec → SQL → RLS → auth → storage → deploy).

All commands below run from `backend-compiler/` with the venv python:

```powershell
cd backend-compiler
$py = ".\.venv\Scripts\python.exe"
```

---

## I want to...

### ...compile a description and deploy it (the full product)

```powershell
$py -m pytest tests\e2e -q        # needs SUPABASE_ACCESS_TOKEN + SUPABASE_ORG_SLUG in .env
```
See `tests/e2e/` for the pipeline calls (interpret → MCQ → validate → deploy).
Requirements: `.env` keys, Supabase CLI (`npm i -g supabase`).

### ...score interpretation approaches (which mechanism is best)

```powershell
$py -m tests.experiments.run_ablation                              # mock personas, engine gold
$py -m tests.experiments.run_ablation --real-laya                  # real 421M checkpoint
$py -m tests.experiments.run_ablation --real-laya --gold human --split golden   # human gold
$py -m tests.experiments.run_ablation --real-laya --gold human --split held_out # frozen held-out
```
Needs for `--real-laya`: torch + `pip install -e ..\laya` (downloads ~800 MB once).

### ...measure model calibration (ECE, temperature fit, threshold sweep)

```powershell
$py -m tests.experiments.run_calibration --gold human
```

### ...benchmark against external baselines (LLMs, dbsmash)

```powershell
$py -m tests.experiments.run_baselines --gold human
```
Needs: `OPENAI_BASE_URL`+`OPENAI_API_KEY` (any OpenAI-compatible gateway)
and/or `GEMINI_API_KEY`; dbsmash additionally wants `OPENROUTER_API_KEY`
+ `npm i -g dbsmash`.

### ...annotate / re-verify the ground truth

```powershell
$py -m tests.annotation.validate --check --set golden   # structural check
$py -m tests.annotation.validate --score --set golden   # blind scoring
$py -m tests.annotation.build_human_gold                # rebuild human gold
```
Protocol: `docs/annotation-protocol.md`. Third-reader guide:
`docs/third-reader-review.md`.

### ...just run the test suite

```powershell
$py -m pytest tests\unit tests\golden tests\experiments -q   # fast, offline
$py -m pytest tests\integration -q                            # needs Docker (postgres:15)
```

---

## Configuration

Copy `.env.example` to `.env` and fill what you use — real keys are never
committed. Results land in `backend-compiler/tests/experiments/results/`.

## The numbers

`Paper.md` is the full write-up (methods, measurements, limitations);
`Paper Outline.md` is the evidence ledger mapping every claim to its
measured artifact.
