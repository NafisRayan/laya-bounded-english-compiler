# ECE calibration harness — design

- **Date:** 2026-09-25
- **Status:** Approved design, ready for implementation planning
- **Source spec:** `Developer Spec.md` §3.5 (Calibration), §18.17 (ECE measurement test), DoD #11 (ECE < 0.1)
- **Depends on:** existing `compiler/interpreter/calibration.py` (`load_calibration`, scalar `apply_temperature`), `calibration.json` (v1, `temperature: 1.0` pass-through), `tests/conftest.py` MockLayaClient contract

## Purpose

The measurement gate behind paper claim **R3** ("ECE-calibrated confidence,
thresholded at 0.1, enables safe auto-accept"): compute Expected Calibration
Error over a pinned golden calibration set, assert the shipped
`answer_confidence` is acceptable (< 0.1), and prove the §3.5 temperature-fit
procedure strictly improves a miscalibrated set.

## Design decisions (confirmed with user)

1. **Pinned synthetic calibration set.** The real `laya` library is not
   installed (venv-only; MockLayaClient contract double). The dataset is a
   hand-constructed, bin-balanced `calibration_set.json`; when real Laya becomes
   installable, measured `(answer_confidence, label)` pairs replace the
   synthetic entries in the SAME JSON schema and the gates do not change.
2. **Spec path.** The gate lives at `tests/integration/test_ece_measurement.py`
   (§18.17's location); the `tests/integration/` package is created here
   (§18.14 idempotency and §18.18 fragment-matrix land there later).
3. **Production math, pure Python.** `expected_calibration_error` and
   `fit_temperature` are added to `compiler/interpreter/calibration.py` —
   single citable home, no numpy dependency (project deps stay
   pydantic + pyyaml). §18.17's sketch defined ECE inside the test file and
   imported a `fit_temperature` that has never existed; both are treated as
   sketch-level.

## Architecture

```
compiler/interpreter/calibration.py      # + expected_calibration_error, fit_temperature
tests/unit/test_calibration.py           # NEW — known-answer math tests
tests/integration/__init__.py            # NEW — empty package marker
tests/integration/test_ece_measurement.py# NEW — the two §18.17 gates
tests/fixtures/golden_calibration/
├── calibration_set.json                 # NEW — pinned, ~40 entries, ECE ≈ 0.04–0.05
└── miscalibrated_set.json               # NEW — pinned, ~20 entries, ECE ≈ 0.4+
```

## Math API (added to calibration.py)

```python
def expected_calibration_error(probs, labels, n_bins=10) -> float:
    """Σ over non-empty bins of (bin share × |mean confidence − mean accuracy|).

    Edges from linspace(0, 1, n_bins+1); bins are [lo, hi) except the last,
    which is [lo, 1.0] so probability 1.0 is counted."""

def fit_temperature(probs, labels) -> float:
    """Deterministic grid search over T ∈ 0.01 … 10.00 (step 0.01); returns the
    T whose sigmoid(logit(clip(p))/T) minimizes ECE (ties → smaller T)."""
```

The fit criterion is ECE because that is the §3.5 gate the fit must move.
`apply_temperature` stays scalar (its production caller `laya_client.calibrated_confidence`
applies it per answer); the harness applies it per element.

## Dataset schema (both files)

Bare JSON list; one entry per noul answer:

```json
[{"answer_confidence": 0.5, "label": 1}, ...]
```

`label` is binary correctness of the answer. No metadata sidecar — provenance
lives in this document and the test docstrings.

- `calibration_set.json` — 40 entries, distribution clustered where Laya
  actually emits confidence (0.5, 0.9, 0.95) plus a spread across 0.6–0.8;
  per-bin accuracy tracks confidence with small deliberate deviations so ECE
  lands ≈ 0.04–0.05: real, non-zero, comfortably under the 0.1 gate. Exact
  entries and the exact ECE value are pinned by RUNNING the function during
  plan authoring (no guessed assertions).
- `miscalibrated_set.json` — ~20 entries, overconfident (e.g. all ≈ 0.9 with
  ~half wrong) → ECE ≈ 0.4. Exists because §18.17's own conditional fit test
  (`if ece_shipped < 0.1: return`) can never reach the fit path with a
  well-calibrated main set — it would be permanently dead code.

## The gates (tests/integration/test_ece_measurement.py)

1. `test_ece_on_shipped_answer_confidence_is_acceptable` —
   `expected_calibration_error(calibration_set) < 0.1`, assert message citing
   §3.5 and reporting the measured value. This is DoD #11's gate.
2. `test_fit_temperature_improves_miscalibrated_set` — assert
   `expected_calibration_error(miscalibrated_set) >= 0.1` (precondition), fit
   `T = fit_temperature(...)`, apply per element, assert ECE strictly
   decreased. Always exercised (never conditionally skipped).

## Deviations from §18.17 (documented)

1. ECE + fit math homed in `compiler/interpreter/calibration.py` (pure Python)
   instead of numpy inside the test file; numpy is NOT added as a dependency.
2. The conditional `test_fit_temperature_only_improves_if_needed` is replaced
   by an unconditional fit-path test over a deliberately miscalibrated fixture
   (the conditional form is unreachable with a passing main gate).
3. Dataset is a pinned synthetic set pending a real, installable Laya.

## Definition of done

- Full suite green: 129 existing + new tests (unit math tests + 2 gates —
  exact count pinned when written).
- `calibration.json` (v1) unchanged: `temperature: 1.0`, `needs_fit: false` —
  the main gate passing is precisely the evidence for that state.
- Zero changes outside `calibration.py` (+ its `__all__`), new tests, and new
  fixtures.
- Same review/push discipline: implementer + spec + quality reviews, final
  whole-feature review, then push `master`.
