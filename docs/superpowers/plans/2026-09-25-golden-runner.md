# Golden Test Runner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the §18.13 golden test runner — 11 YAML-driven end-to-end cases through `run_interpreter` → `run_mcq_loop` → `validate`, with zero compiler-code changes.

**Architecture:** A typed pydantic `GoldenCase` schema validated at collection time; persona-based mock Laya doubles (`default`/`high`/`none`); partial `expected_spec` submatch returning diffs; positive/negative question-type and per-target assertions. All case texts and expectations were pinned by running the real engine during plan authoring (see design doc "The 11 cases").

**Tech Stack:** pytest 8 (module-level `pytest_generate_tests` parametrization), pydantic v2, PyYAML, existing `tests/conftest.py` fixtures (`ontology`, `MockLayaClient`).

**Design doc:** `docs/superpowers/specs/2026-09-25-golden-runner-design.md` (authoritative for deviations from §18.13 — persona doubles, `text=` passed, typed schema, `validate_ok`, `absent_question_targets`).

**Baseline:** 118 tests pass on `master`. Final state: **129** (118 + 11 golden).

---

### Task 1: Runner infrastructure + smoke case

**Files:**
- Create: `backend-compiler/tests/golden/__init__.py` (empty)
- Create: `backend-compiler/tests/golden/test_golden.py`
- Create: `backend-compiler/tests/golden/cases/empty_spec_junk_text.yaml`

- [ ] **Step 1: Create the package marker**

Create an empty file `backend-compiler/tests/golden/__init__.py` and an empty directory `backend-compiler/tests/golden/cases/`.

- [ ] **Step 2: Write the runner**

Create `backend-compiler/tests/golden/test_golden.py` with EXACTLY this content:

```python
"""Golden end-to-end cases: text -> run_interpreter -> run_mcq_loop -> validate.

Developer Spec.md §18.13; design:
docs/superpowers/specs/2026-09-25-golden-runner-design.md (persona doubles,
text= passed, typed schema, validate_ok, absent_question_targets).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

import pytest
import yaml
from pydantic import BaseModel, Field

from compiler.interpreter.pipeline import run_interpreter
from compiler.mcq.pipeline import run_mcq_loop
from compiler.spec.validator import validate
from tests.conftest import MockLayaClient

CASES = sorted((Path(__file__).parent / "cases").glob("*.yaml"))


class GoldenCase(BaseModel):
    input: str
    laya: Literal["default", "high", "none"] = "default"
    user_answers: dict[str, Any] = Field(default_factory=dict)
    expected_spec: dict[str, Any]
    expect_question_types: list[str] = Field(default_factory=list)
    absent_question_types: list[str] = Field(default_factory=list)
    absent_question_targets: list[str] = Field(default_factory=list)
    max_mcqs: int = 10
    validate_ok: bool = True


class _NoLaya(MockLayaClient):
    """Persona 'none': empty answers — run_interpreter always calls predict()."""

    def predict(self, state: str, questions: dict) -> dict:
        return self._envelope({})


class _HighConfidence(MockLayaClient):
    """Persona 'high': 0.95 noul — every needs_* proposal clears AUTO_ACCEPT."""

    def predict(self, state: str, questions: dict) -> dict:
        from tests.conftest import _first_choice, _make_laya_answer

        answers = {}
        for qid, q in questions.items():
            if q["type"] == "noul":
                answers[qid] = _make_laya_answer("noul", 0.95)
            else:
                answers[qid] = _make_laya_answer("choice", _first_choice(q["criteria"]))
        return self._envelope(answers)


def _persona(name: str) -> MockLayaClient:
    if name == "none":
        return _NoLaya()
    if name == "high":
        return _HighConfidence()
    return MockLayaClient()


def pytest_generate_tests(metafunc):
    if "case_path" in metafunc.fixturenames:
        metafunc.parametrize("case_path", CASES, ids=[c.stem for c in CASES])


def spec_matches(actual, expected: dict) -> list[tuple]:
    """Partial submatch of actual.model_dump() against expected (§18.13).

    Dict values submatch per key; list values compare order-insensitively
    (JSON-canonical sort so dict entries cannot crash sorted()); absent keys
    are unchecked. Returns mismatch tuples so failures print diffs.
    """
    actual_dict = actual.model_dump()
    diffs: list[tuple] = []

    def canon(items) -> list:
        return sorted(items or [], key=lambda x: json.dumps(x, sort_keys=True))

    for key, expected_val in expected.items():
        actual_val = actual_dict.get(key)
        if isinstance(expected_val, dict):
            actual_sub = actual_val or {}
            for k, v in expected_val.items():
                if actual_sub.get(k) != v:
                    diffs.append((key, k, v, actual_sub.get(k)))
        elif isinstance(expected_val, list):
            if canon(actual_val) != canon(expected_val):
                diffs.append((key, None, expected_val, actual_val))
        elif actual_val != expected_val:
            diffs.append((key, None, expected_val, actual_val))
    return diffs


def test_golden(case_path, ontology):
    case = GoldenCase.model_validate(yaml.safe_load(case_path.read_text(encoding="utf-8")))
    mock = _persona(case.laya)

    candidates = run_interpreter(case.input, ontology, laya=mock)
    spec, mcqs = run_mcq_loop(candidates, ontology,
                              user_answers=case.user_answers,
                              text=case.input,
                              laya=mock)

    diffs = spec_matches(spec, case.expected_spec)
    assert not diffs, f"{case_path.stem}: spec mismatch — {diffs}"
    for qtype in case.expect_question_types:
        assert any(q.type == qtype for q in mcqs), (
            f"{case_path.stem}: expected a {qtype} question, "
            f"got {[(q.type, q.target) for q in mcqs]}")
    for qtype in case.absent_question_types:
        assert not [q for q in mcqs if q.type == qtype], (
            f"{case_path.stem}: {qtype} should be absent, "
            f"got {[(q.type, q.target) for q in mcqs]}")
    for target in case.absent_question_targets:
        assert not [q for q in mcqs if q.target == target], (
            f"{case_path.stem}: nothing should target {target}, "
            f"got {[(q.type, q.target) for q in mcqs]}")
    assert len(mcqs) <= case.max_mcqs, (
        f"{case_path.stem}: {len(mcqs)} questions exceed max_mcqs={case.max_mcqs}")
    result = validate(spec, ontology)
    assert result.ok == case.validate_ok, (
        f"{case_path.stem}: validate ok={result.ok}, expected "
        f"{case.validate_ok}: {result.errors}")
```

- [ ] **Step 3: Write the smoke case**

Create `backend-compiler/tests/golden/cases/empty_spec_junk_text.yaml`:

```yaml
# Junk text produces no candidates, but the engine still asks: the sentence is
# unmapped (clarify_unparsed) and authentication is always confirmable.
input: "Hello there."
laya: none
expected_spec:
  features: {}
  parameters: {}
  roles: []
expect_question_types: [clarify_unparsed, confirm_feature]
```

- [ ] **Step 4: Run the golden suite**

Run: `& "C:\Users\BS00861\Documents\GitHub\Laya Supabase\system\backend-compiler\.venv\Scripts\python.exe" -m pytest tests/golden -q` (from `backend-compiler`)
Expected: `1 passed` (id `empty_spec_junk_text`)

- [ ] **Step 5: Run the full suite**

Run: `& "C:\Users\BS00861\Documents\GitHub\Laya Supabase\system\backend-compiler\.venv\Scripts\python.exe" -m pytest -q`
Expected: `119 passed`

- [ ] **Step 6: Commit**

```bash
git add backend-compiler/tests/golden
git commit -m "Add golden runner with typed case schema"
```

---

### Task 2: Decide-path cases (exact+phrase, laya default, laya high, negation)

**Files:**
- Create: `backend-compiler/tests/golden/cases/alias_and_phrase_decide.yaml`
- Create: `backend-compiler/tests/golden/cases/laya_default_asks.yaml`
- Create: `backend-compiler/tests/golden/cases/laya_high_decides.yaml`
- Create: `backend-compiler/tests/golden/cases/negation_resolved_by_answer.yaml`

- [ ] **Step 1: Write the four cases**

`alias_and_phrase_decide.yaml` — alias words also phrase-match, so this pins
the combined path: "stripe" (exact alias + phrase) decides `payments` and its
provider; the auth answer lands BEFORE the fold, so the "email password"
method alias is decided too (fold's param loop sees auth enabled):

```yaml
input: "Use stripe for payments and email password for login"
laya: none
user_answers:
  features.authentication: true
expected_spec:
  features:
    authentication: true
    payments: true
  parameters:
    authentication.method: email_password
    payments.provider: stripe
absent_question_types: [clarify_unparsed, choose_parameter]
```

`laya_default_asks.yaml` — 0.5 signals never clear AUTO_ACCEPT; every needs_*
proposal stays undecided and comes back as questions:

```yaml
input: "We need bookings and messaging"
laya: default
expected_spec:
  features: {}
  parameters: {}
  roles: []
expect_question_types: [confirm_feature, clarify_unparsed]
```

`laya_high_decides.yaml` — 0.95 clears AUTO_ACCEPT for every proposed feature
(10 features end up enabled; we pin a representative subset — validate ok
covers the rest):

```yaml
input: "Use stripe for payments and email password for login"
laya: high
expected_spec:
  features:
    authentication: true
    payments: true
  parameters:
    authentication.method: email_password
    payments.provider: stripe
expect_question_types: [choose_parameter]
absent_question_types: [confirm_feature, resolve_negation]
```

`negation_resolved_by_answer.yaml` — "pay" (phrase, 0.85) and "no payments"
(negated, 0.9) conflict, but the user answer decides payments first, so the
fold's is_decided guard suppresses the negation question:

```yaml
input: "Buyers can pay for services. There are no payments."
laya: none
user_answers:
  features.payments: false
expected_spec:
  features:
    payments: false
absent_question_types: [resolve_negation]
```

- [ ] **Step 2: Run the golden suite**

Run: `& "C:\Users\BS00861\Documents\GitHub\Laya Supabase\system\backend-compiler\.venv\Scripts\python.exe" -m pytest tests/golden -q`
Expected: `5 passed`

- [ ] **Step 3: Run the full suite**

Run: `& "C:\Users\BS00861\Documents\GitHub\Laya Supabase\system\backend-compiler\.venv\Scripts\python.exe" -m pytest -q`
Expected: `123 passed`

- [ ] **Step 4: Commit**

```bash
git add backend-compiler/tests/golden
git commit -m "Add golden cases: decide paths and negation"
```

---

### Task 3: Contradiction, coverage, dependency-pruning cases

**Files:**
- Create: `backend-compiler/tests/golden/cases/contradiction_surfaced.yaml`
- Create: `backend-compiler/tests/golden/cases/contradiction_resolved.yaml`
- Create: `backend-compiler/tests/golden/cases/unparsed_coverage_resolved.yaml`
- Create: `backend-compiler/tests/golden/cases/dep_pruning.yaml`

- [ ] **Step 1: Write the four cases**

`contradiction_surfaced.yaml` — the hard contradicts constraint
(instant × verification) fires; the spec is invalid BY DEFINITION when a
contradiction surfaces, hence `validate_ok: false`:

```yaml
input: "Admins can manage the platform"
laya: none
user_answers:
  features.authentication: true
  features.bookings: true
  parameters.bookings.mode: instant
expected_spec:
  features:
    authentication: true
    bookings: true
  parameters:
    bookings.mode: instant
expect_question_types: [resolve_contradiction]
validate_ok: false
```

`contradiction_resolved.yaml` — the answer breaks the constraint's if_-side,
so no contradiction question and the spec validates:

```yaml
input: "Admins can manage the platform"
laya: none
user_answers:
  features.authentication: true
  features.bookings: true
  parameters.bookings.mode: owner_approval
expected_spec:
  features:
    authentication: true
    bookings: true
  parameters:
    bookings.mode: owner_approval
absent_question_types: [resolve_contradiction]
```

`unparsed_coverage_resolved.yaml` — the junk sentence is unparsed; the
answer maps index 0 to a feature (decided directly) and suppresses the
coverage question:

```yaml
input: "Owners can reject bad actors."
laya: default
user_answers:
  unparsed.0: authentication
expected_spec:
  features:
    authentication: true
absent_question_types: [clarify_unparsed]
```

`dep_pruning.yaml` — bookings stays weak (0.5, undecided), so favorites
(requires authentication AND bookings) is dependency-pruned from the confirm
band while other confirms remain:

```yaml
input: "We need bookings and messaging"
laya: default
user_answers:
  features.authentication: true
  unparsed.0: authentication
expected_spec:
  features:
    authentication: true
expect_question_types: [confirm_feature]
absent_question_targets: [features.favorites]
```

- [ ] **Step 2: Run the golden suite**

Run: `& "C:\Users\BS00861\Documents\GitHub\Laya Supabase\system\backend-compiler\.venv\Scripts\python.exe" -m pytest tests/golden -q`
Expected: `9 passed`

- [ ] **Step 3: Run the full suite**

Run: `& "C:\Users\BS00861\Documents\GitHub\Laya Supabase\system\backend-compiler\.venv\Scripts\python.exe" -m pytest -q`
Expected: `127 passed`

- [ ] **Step 4: Commit**

```bash
git add backend-compiler/tests/golden
git commit -m "Add golden cases: contradiction, coverage, pruning"
```

---

### Task 4: Roles case, cap case, final verification, push

**Files:**
- Create: `backend-compiler/tests/golden/cases/roles_phrases.yaml`
- Create: `backend-compiler/tests/golden/cases/max_mcqs_cap.yaml`

- [ ] **Step 1: Write the two cases**

`roles_phrases.yaml` — role phrase rules are singular-only (`\badmin\b`), so
the text uses "An admin" (NOT "Admins"); the fold's roles block enables the
feature and derives role_names:

```yaml
input: "An admin can manage the platform."
laya: none
user_answers:
  features.authentication: true
expected_spec:
  features:
    authentication: true
    roles: true
  parameters:
    roles.role_names: [admin]
  roles: [admin]
```

`max_mcqs_cap.yaml` — 8 questions pre-cap (clarify_unparsed + 6
confirm_feature + choose_parameter authentication.method); the cap must bind:

```yaml
input: "Owners can reject bad actors."
laya: default
user_answers:
  features.authentication: true
expected_spec:
  features:
    authentication: true
max_mcqs: 4
```

- [ ] **Step 2: Run the golden suite**

Run: `& "C:\Users\BS00861\Documents\GitHub\Laya Supabase\system\backend-compiler\.venv\Scripts\python.exe" -m pytest tests/golden -q`
Expected: `11 passed`

- [ ] **Step 3: Run the full suite (final count)**

Run: `& "C:\Users\BS00861\Documents\GitHub\Laya Supabase\system\backend-compiler\.venv\Scripts\python.exe" -m pytest -q`
Expected: `129 passed`

- [ ] **Step 4: Commit**

```bash
git add backend-compiler/tests/golden
git commit -m "Add golden cases: roles and cap"
```

- [ ] **Step 5: Verify clean tree and push (after final code review)**

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
- Case YAMLs use plain flow/list syntax; `unparsed.0` is a literal key with a
  dot (valid YAML). Booleans are lowercase (`true`/`false`).
- If any pinned expectation fails on a fresh run, STOP and report BLOCKED with
  the actual engine output — do NOT edit the YAML to match a failing engine
  (the pins are the spec; a mismatch means the engine or the environment
  changed).
- Zero compiler-code changes are expected across all tasks. If you find
  yourself editing `compiler/`, STOP and report BLOCKED.
