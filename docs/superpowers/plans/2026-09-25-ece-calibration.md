# ECE Calibration Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the §3.5 / §18.17 ECE measurement gates — pure-Python `expected_calibration_error` + `fit_temperature` in the calibration module, two pinned JSON calibration sets, and the integration gate asserting shipped `answer_confidence` is calibrated (ECE < 0.1) and that temperature fitting strictly improves a miscalibrated set.

**Architecture:** Math lives in `compiler/interpreter/calibration.py` (no numpy — deps stay pydantic+pyyaml); gates live at `tests/integration/test_ece_measurement.py` per §18.17. Datasets are pinned synthetic stand-ins (real `laya` is not installed); measured pairs replace them in the same JSON schema later without touching the gates.

**Tech Stack:** pytest 8, stdlib json/math only.

**Design doc:** `docs/superpowers/specs/2026-09-25-ece-calibration-design.md` (authoritative for deviations from §18.17: production-math home, unconditional fit-path test, synthetic dataset).

**Baseline:** 129 tests pass on `master`. Final state: **139** (129 + 8 unit math tests + 2 gates). All dataset/ECE numbers below were pinned by running the planned math (script output: calibration_set ECE = 0.045; miscalibrated ECE 0.45 → best T = 10.0 → 0.104711).

---

### Task 1: ECE math in the calibration module

**Files:**
- Modify: `backend-compiler/compiler/interpreter/calibration.py`
- Test: `backend-compiler/tests/unit/test_calibration.py`

- [ ] **Step 1: Write the failing tests**

Create `backend-compiler/tests/unit/test_calibration.py` with EXACTLY this content:

```python
"""Known-answer tests for the ECE/temperature math (Developer Spec.md §3.5, §18.17)."""

import pytest

from compiler.interpreter.calibration import (
    apply_temperature,
    expected_calibration_error,
    fit_temperature,
    load_calibration,
)


def test_ece_perfectly_calibrated_is_zero():
    # One bin, mean confidence == mean accuracy.
    assert expected_calibration_error([0.5, 0.5], [1, 0]) == 0.0


def test_ece_hand_computed_single_bin():
    # All four land in [0.8, 0.9): |mean conf 0.8 − mean acc 0.25| = 0.55.
    assert expected_calibration_error([0.8, 0.8, 0.8, 0.8], [1, 0, 0, 0]) == pytest.approx(0.55)


def test_ece_weights_bins_by_share():
    # Bin [0.5,0.6): |0.5 − 1.0| = 0.5 at share 0.5 → 0.25
    # Bin [0.9,1.0]: |0.9 − 0.0| = 0.9 at share 0.5 → 0.45; total 0.70.
    assert expected_calibration_error([0.5, 0.9], [1, 0]) == pytest.approx(0.70)


def test_ece_last_bin_includes_one():
    assert expected_calibration_error([1.0], [0]) == pytest.approx(1.0)


def test_fit_temperature_reduces_ece_on_overconfident_set():
    probs = [0.9, 0.9, 0.9, 0.9]
    labels = [0, 0, 0, 0]
    before = expected_calibration_error(probs, labels)
    t = fit_temperature(probs, labels)
    after = expected_calibration_error([apply_temperature(p, t) for p in probs], labels)
    assert after < before


def test_apply_temperature_half_is_identity():
    # logit(0.5) == 0, so any temperature leaves it at 0.5.
    assert apply_temperature(0.5, 3.7) == pytest.approx(0.5)


def test_apply_temperature_clips_extremes():
    assert apply_temperature(0.0, 1.0) == pytest.approx(1e-6)
    assert apply_temperature(1.0, 1.0) == pytest.approx(1 - 1e-6)


def test_load_calibration_v1_english_is_passthrough():
    cal = load_calibration()
    assert cal["english"]["temperature"] == 1.0
    assert cal["english"]["needs_fit"] is False
```

- [ ] **Step 2: Run to verify failure**

Run: `& "C:\Users\BS00861\Documents\GitHub\Laya Supabase\system\backend-compiler\.venv\Scripts\python.exe" -m pytest tests/unit/test_calibration.py -q` (from `backend-compiler`)
Expected: collection ImportError — `cannot import name 'expected_calibration_error'`

- [ ] **Step 3: Implement**

In `backend-compiler/compiler/interpreter/calibration.py`:

Change the `__all__` line to:

```python
__all__ = [
    "CALIBRATION_FILE",
    "apply_temperature",
    "expected_calibration_error",
    "fit_temperature",
    "load_calibration",
]
```

Append the two functions at the end of the file:

```python
def expected_calibration_error(probs, labels, n_bins: int = 10) -> float:
    """ECE over equal-width bins (§18.17): Σ bin_share × |mean conf − mean acc|.

    Bins are [lo, hi) from linspace(0, 1, n_bins + 1); the last bin is
    [lo, 1.0] so a probability of exactly 1.0 is counted.
    """
    edges = [i / n_bins for i in range(n_bins + 1)]
    total = 0.0
    for i in range(n_bins):
        lo, hi = edges[i], edges[i + 1]
        if i == n_bins - 1:
            idx = [j for j, p in enumerate(probs) if lo <= p <= hi]
        else:
            idx = [j for j, p in enumerate(probs) if lo <= p < hi]
        if not idx:
            continue
        mean_p = sum(probs[j] for j in idx) / len(idx)
        mean_l = sum(labels[j] for j in idx) / len(idx)
        total += (len(idx) / len(probs)) * abs(mean_p - mean_l)
    return total


def fit_temperature(probs, labels) -> float:
    """Grid-search T ∈ 0.01…10.00 (step 0.01) minimizing the ECE of the
    temperature-scaled probs (§3.5 step 5). Ties resolve to the smaller T,
    and a T of 1.0 (pass-through) is never replaced by an equal-ECE T.

    The criterion is ECE because that is the §3.5 gate the fit must move.
    """
    best_t = 1.0
    best_ece = expected_calibration_error(
        [apply_temperature(p, best_t) for p in probs], labels)
    for i in range(1, 1001):
        t = i / 100
        e = expected_calibration_error(
            [apply_temperature(p, t) for p in probs], labels)
        if e < best_ece:
            best_t, best_ece = t, e
    return best_t
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/unit/test_calibration.py -q` → Expected: `8 passed`
Run full: `python -m pytest -q` → Expected: `137 passed`

- [ ] **Step 5: Commit**

```bash
git add backend-compiler/compiler/interpreter/calibration.py backend-compiler/tests/unit/test_calibration.py
git commit -m "Add ECE math to calibration module"
```

---

### Task 2: Pinned calibration sets + §18.17 gates

**Files:**
- Create: `backend-compiler/tests/integration/__init__.py` (empty)
- Create: `backend-compiler/tests/integration/test_ece_measurement.py`
- Create: `backend-compiler/tests/fixtures/golden_calibration/calibration_set.json`
- Create: `backend-compiler/tests/fixtures/golden_calibration/miscalibrated_set.json`

- [ ] **Step 1: Write the gates (watch them fail on missing fixtures)**

Create `backend-compiler/tests/integration/__init__.py` — empty file.

Create `backend-compiler/tests/integration/test_ece_measurement.py` with EXACTLY this content:

```python
"""ECE measurement gates (Developer Spec.md §18.17, §3.5; design:
docs/superpowers/specs/2026-09-25-ece-calibration-design.md).

The dataset is a pinned synthetic stand-in (real `laya` is not installed);
measured (answer_confidence, label) pairs replace it in the same schema when
the library is available — the gates do not change.
"""

import json
from pathlib import Path

from compiler.interpreter.calibration import (
    apply_temperature,
    expected_calibration_error,
    fit_temperature,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "golden_calibration"


def _load(name):
    data = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    probs = [d["answer_confidence"] for d in data]
    labels = [d["label"] for d in data]
    return probs, labels


def test_ece_on_shipped_answer_confidence_is_acceptable():
    probs, labels = _load("calibration_set.json")
    ece = expected_calibration_error(probs, labels, n_bins=10)
    assert ece < 0.1, (
        f"ECE on shipped answer_confidence is {ece:.3f}, which exceeds the "
        f"0.1 threshold. See §3.5 for the fitting procedure."
    )


def test_fit_temperature_improves_miscalibrated_set():
    probs, labels = _load("miscalibrated_set.json")
    before = expected_calibration_error(probs, labels, n_bins=10)
    assert before >= 0.1, "miscalibrated_set.json is supposed to be miscalibrated"

    t = fit_temperature(probs, labels)
    after = expected_calibration_error(
        [apply_temperature(p, t) for p in probs], labels, n_bins=10)
    assert after < before, (
        f"temperature fit did not improve ECE: {before:.3f} -> {after:.3f}"
    )
```

Run: `python -m pytest tests/integration -q`
Expected: `2 failed` (FileNotFoundError on the fixture files — the gates must fail before the data exists)

- [ ] **Step 2: Create the pinned fixtures**

Create `backend-compiler/tests/fixtures/golden_calibration/calibration_set.json` with EXACTLY this content (40 entries, pinned ECE = 0.045):

```json
[
  {"answer_confidence": 0.5, "label": 1},
  {"answer_confidence": 0.5, "label": 1},
  {"answer_confidence": 0.5, "label": 1},
  {"answer_confidence": 0.5, "label": 1},
  {"answer_confidence": 0.5, "label": 1},
  {"answer_confidence": 0.5, "label": 1},
  {"answer_confidence": 0.5, "label": 0},
  {"answer_confidence": 0.5, "label": 0},
  {"answer_confidence": 0.5, "label": 0},
  {"answer_confidence": 0.5, "label": 0},
  {"answer_confidence": 0.5, "label": 0},
  {"answer_confidence": 0.5, "label": 0},
  {"answer_confidence": 0.6, "label": 1},
  {"answer_confidence": 0.6, "label": 1},
  {"answer_confidence": 0.6, "label": 1},
  {"answer_confidence": 0.6, "label": 1},
  {"answer_confidence": 0.6, "label": 0},
  {"answer_confidence": 0.6, "label": 0},
  {"answer_confidence": 0.7, "label": 1},
  {"answer_confidence": 0.7, "label": 1},
  {"answer_confidence": 0.7, "label": 1},
  {"answer_confidence": 0.7, "label": 0},
  {"answer_confidence": 0.8, "label": 1},
  {"answer_confidence": 0.8, "label": 1},
  {"answer_confidence": 0.8, "label": 1},
  {"answer_confidence": 0.8, "label": 0},
  {"answer_confidence": 0.9, "label": 1},
  {"answer_confidence": 0.9, "label": 1},
  {"answer_confidence": 0.9, "label": 1},
  {"answer_confidence": 0.9, "label": 1},
  {"answer_confidence": 0.9, "label": 1},
  {"answer_confidence": 0.9, "label": 0},
  {"answer_confidence": 0.95, "label": 1},
  {"answer_confidence": 0.95, "label": 1},
  {"answer_confidence": 0.95, "label": 1},
  {"answer_confidence": 0.95, "label": 1},
  {"answer_confidence": 0.95, "label": 1},
  {"answer_confidence": 0.95, "label": 1},
  {"answer_confidence": 0.95, "label": 1},
  {"answer_confidence": 0.95, "label": 0}
]
```

Create `backend-compiler/tests/fixtures/golden_calibration/miscalibrated_set.json` with EXACTLY this content (20 entries, pinned ECE = 0.45):

```json
[
  {"answer_confidence": 0.9, "label": 1},
  {"answer_confidence": 0.9, "label": 1},
  {"answer_confidence": 0.9, "label": 1},
  {"answer_confidence": 0.9, "label": 1},
  {"answer_confidence": 0.9, "label": 1},
  {"answer_confidence": 0.9, "label": 1},
  {"answer_confidence": 0.9, "label": 1},
  {"answer_confidence": 0.9, "label": 1},
  {"answer_confidence": 0.9, "label": 1},
  {"answer_confidence": 0.9, "label": 0},
  {"answer_confidence": 0.9, "label": 0},
  {"answer_confidence": 0.9, "label": 0},
  {"answer_confidence": 0.9, "label": 0},
  {"answer_confidence": 0.9, "label": 0},
  {"answer_confidence": 0.9, "label": 0},
  {"answer_confidence": 0.9, "label": 0},
  {"answer_confidence": 0.9, "label": 0},
  {"answer_confidence": 0.9, "label": 0},
  {"answer_confidence": 0.9, "label": 0},
  {"answer_confidence": 0.9, "label": 0}
]
```

- [ ] **Step 3: Verify pass**

Run: `python -m pytest tests/integration -q` → Expected: `2 passed`
Run full: `python -m pytest -q` → Expected: `139 passed`

- [ ] **Step 4: Commit**

```bash
git add backend-compiler/tests/integration backend-compiler/tests/fixtures/golden_calibration
git commit -m "Add ECE measurement gates with pinned calibration sets"
```

---

### Task 3: Final verification and push

- [ ] **Step 1: Full test run**

Run: `& "C:\Users\BS00861\Documents\GitHub\Laya Supabase\system\backend-compiler\.venv\Scripts\python.exe" -m pytest -q`
Expected: `139 passed`

- [ ] **Step 2: Verify clean tree and push (after final code review)**

```bash
git status --short
git push origin master
```
Expected: clean tree; new commits on `origin/master`.

---

## Notes for implementers

- All pytest commands run from `backend-compiler`; git commands from the git
  root `C:\Users\BS00861\Documents\GitHub\Laya Supabase\system`. LF→CRLF
  warnings from git are expected — ignore them.
- The pinned numbers are the spec: calibration_set.json → ECE exactly 0.045;
  miscalibrated_set.json → ECE 0.45 before fit, strictly lower after (pinned
  best T = 10.0 → ≈ 0.1047). If a fresh run disagrees, STOP and report BLOCKED
  with actual output — do NOT edit fixtures or math to force a pass.
- Zero changes are expected outside `calibration.py` (+'__all__'), the new
  test files, and the new fixtures. `laya_client.py`, `conftest.py`, and
  `calibration.json` (v1) must NOT change.
