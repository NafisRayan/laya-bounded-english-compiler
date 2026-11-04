[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.23942697.svg)](https://doi.org/10.5281/zenodo.23942697)

# Replication Package

Artifact for **"From Bounded English to a Working Backend: A Deterministic,
Ontology-Bounded Compiler"** (Nafis Rayan, 2026).

Everything below marked **[verified offline]** was executed from this exact
tree on a clean run: no network, no API keys, no model downloads.

## Requirements

- Python 3.13
- OS: Windows or Linux (paths below are Windows; flip separators elsewhere)
- Optional, only for key-gated tiers: Supabase access token / project ref
  (`.env`, see `backend-compiler/.env.example`), `OPENAI_API_KEY` /
  `ANTHROPIC_API_KEY` for the LLM baselines, local Laya checkpoint for
  real-model calibration

## Quick start (60 s, offline)

```powershell
cd backend-compiler
py -m venv .venv
.\.venv\Scripts\pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest tests\unit tests\golden -q
```

Expected: **505 passed** (~3 s). The `tests\golden` tier is the paper's
compile-faithfulness result (§5.1): 50 fixed natural-language inputs, each
asserted against its expected `BackendSpec` in `tests/golden/cases/`.

## Regenerating the measured tables

| Paper claim | Committed measurement | Regenerate with |
|---|---|---|
| §5.1 compile-faithfulness (oracle MCQ) | `tests/golden/cases/` + `tests/golden/splits.yaml` (golden 35 / held-out 15) | the quick-start command above **[verified offline]** |
| §5.2 mechanism × MCQ ablation | `tests/experiments/results/ablation*.jsonl` + `*_summary.md` | `python -m tests.experiments.run_ablation` **[verified offline: 500 rows + summary table in ~1 s]** |
| §5.1 external baselines (LLM→SQL, LLM→spec, DbSmash) | `tests/experiments/results/baselines*.jsonl` | `python -m tests.experiments.run_baselines` — adapters self-skip without credentials; every committed row was measured with keys present |
| §5.3 calibration (ECE, temperature fit) | `tests/experiments/results/calibration_pairs_human.jsonl`, `calibration_summary_human.md` | `python -m tests.experiments.run_calibration` — needs the pinned Laya checkpoint |
| Unaided (operator-free) numbers | `tests/experiments/results/ablation_*human*.jsonl` | same ablation CLI scored against human gold (below) |
| Human ground truth + inter-annotator reconciliation | `tests/annotation/human_gold.yaml`, `RECONCILIATION.yaml`, `second_annotator/` | static artifacts; annotation protocol in `docs/annotation-protocol.md` |

Ablation determinism: mock personas are tape-like — successive runs produce
identical rows.

## Test tiers

| Tier | Command | Needs |
|---|---|---|
| Unit + golden (offline) | `pytest tests\unit tests\golden -q` | nothing |
| Experiments harness self-tests | `pytest tests\experiments -q` | nothing |
| Integration (live Postgres, 595-pair idempotency matrix, ECE gates) | `pytest tests\integration` | local/remote Postgres + `.env` |
| E2E real deployments | `pytest tests\e2e` | Supabase credentials |

## Repository map

```
backend-compiler/compiler/     the compiler (interpreter → MCQ → spec → generator → deployer)
backend-compiler/ontology/     the bounded vocabulary (v1)
backend-compiler/tests/golden/ 50 fixed cases + splits
backend-compiler/tests/experiments/results/   every measurement ever taken (JSONL + markdown summaries)
backend-compiler/tests/annotation/            human gold, second annotator, reconciliation
Paper.md                       full manuscript source
Paper Outline.md               claim → experiment → artifact evidence ledger
```

## Citing

Archived release: [![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.23942697.svg)](https://doi.org/10.5281/zenodo.23942697)
(version 1.0.0: [10.5281/zenodo.23942698](https://doi.org/10.5281/zenodo.23942698)).
If you use this artifact, cite:

> Rayan, N. (2026). *Laya: a deterministic, ontology-bounded compiler from
> bounded English to Supabase backends* (v1.0.0) [Computer software].
> Zenodo. https://doi.org/10.5281/zenodo.23942698

## License

MIT — see `LICENSE`. The manuscript (`Paper.md`) is separately available for
text reuse under CC BY 4.0 via the Zenodo record.
