# MCQ Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the MCQ engine — `PartialSpec`, `Question`, `next_questions`, `order_questions`, and the single-pass `run_mcq_loop` pipeline that turns interpreter candidates into a resolved `BackendSpec` plus the open questions still needing user input.

**Architecture:** Pure single-pass pipeline. User answers apply directly to a `PartialSpec` first; interpreter candidates are folded into decisions by confidence thresholds (§3.4); leftover ambiguity (negation conflicts, unparsed sentences, hard contradictions, undecided features/params) is surfaced as ordered `Question`s, capped at `max_mcqs`.

**Tech Stack:** Python 3.13, pydantic v2, pytest 9. Venv at `system/backend-compiler/.venv`.

**Working dir for all commands:** `C:\Users\BS00861\Documents\GitHub\Laya Supabase\system\backend-compiler`
**Python:** `& "C:\Users\BS00861\Documents\GitHub\Laya Supabase\system\backend-compiler\.venv\Scripts\python.exe"`
**Git root:** `C:\Users\BS00861\Documents\GitHub\Laya Supabase\system`

**Design doc:** `docs/superpowers/specs/2026-09-24-mcq-engine-design.md` (approved). Deviations and semantics are recorded there and must not be contradicted by the code.

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `compiler/spec/models.py` | Modify | Add `PartialSpec` (imported by §18.10 tests from here) |
| `compiler/mcq/__init__.py` | Create | Package marker |
| `compiler/mcq/selector.py` | Create | `QuestionType`, `Question`, `next_questions` (imported by §18.10 tests from here) |
| `compiler/mcq/thresholds.py` | Create | `MCQ_MIN`, `AUTO_ACCEPT`, `WEAK_MIN` constants |
| `compiler/mcq/graph.py` | Create | `_feature_depths`, `_rank`, `order_questions` |
| `compiler/mcq/pipeline.py` | Create | `_fold_candidates`, `_coverage_questions`, `_contradiction_questions`, `run_mcq_loop` |
| `compiler/spec/validator.py` | Modify | Add public `constraint_holds(cond, features, parameters)`; `_constraint_matches` delegates to it |
| `tests/unit/test_mcq.py` | Create | All MCQ tests (built up across tasks) |

Existing helpers used (do not reimplement): `compiler.interpreter.merge.check_coverage(text, mapped)`, `compiler.spec.derive.recompute_spec(spec, ontology)`, `tests.conftest.MockLayaClient`, fixtures `ontology`, `mock_laya`, `mock_laya_high_confidence`.

---

### Task 1: `PartialSpec` model

**Files:**
- Modify: `compiler/spec/models.py`
- Test: `tests/unit/test_mcq.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_mcq.py`:

```python
"""MCQ engine unit tests (Developer Spec.md §18.10 + pipeline tests)."""

from compiler.spec.models import PartialSpec


def test_partial_spec_set_form():
    spec = PartialSpec(
        decided_features={"authentication"},
        enabled_features={"authentication"},
    )
    assert spec.decided_features == {"authentication"}
    assert spec.enabled_features == {"authentication"}
    assert spec.decided_parameters == set()
    assert spec.parameter_values == {}


def test_partial_spec_dict_form_normalizes_to_set():
    spec = PartialSpec(decided_features={"authentication": False}, enabled_features=set())
    assert spec.decided_features == {"authentication"}
    assert spec.enabled_features == set()


def test_decide_helpers():
    spec = PartialSpec()
    spec.decide_feature("bookings", enabled=True)
    assert spec.is_decided("bookings") and spec.is_enabled("bookings")
    spec.decide_feature("payments", enabled=False)
    assert spec.is_decided("payments") and not spec.is_enabled("payments")
    spec.decide_parameter("bookings.mode", value="instant")
    assert "bookings.mode" in spec.decided_parameters
    assert spec.parameter_value("bookings.mode") == "instant"


def test_decide_parameter_without_value():
    spec = PartialSpec()
    spec.decide_parameter("bookings.mode")
    assert "bookings.mode" in spec.decided_parameters
    assert spec.parameter_value("bookings.mode") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `& "C:\Users\BS00861\Documents\GitHub\Laya Supabase\system\backend-compiler\.venv\Scripts\python.exe" -m pytest tests/unit/test_mcq.py -q`
Expected: FAIL — `ImportError: cannot import name 'PartialSpec' from 'compiler.spec.models'`

- [ ] **Step 3: Implement `PartialSpec`**

Edit `compiler/spec/models.py`:

- Add `field_validator` to the pydantic import (line 8: `from pydantic import BaseModel, field_validator`).
- Add `PartialSpec` class after `Candidate` (line 56) and add `"PartialSpec"` to `__all__` (line 10).

```python
class PartialSpec(BaseModel):
    """Spec under construction (Developer Spec.md §4.1 / §18.10).

    `decided_features` accepts either a set of feature ids or a dict
    {feature_id: bool} (the dict form is what §18.10 uses); it normalizes to
    a set of keys. Enabling truth lives in `enabled_features`. Parameter
    decisions are recorded in `decided_parameters`; their values (when known)
    in `parameter_values`.
    """

    decided_features: set[str] | dict[str, bool] = Field(default_factory=set)
    enabled_features: set[str] = Field(default_factory=set)
    decided_parameters: set[str] = Field(default_factory=set)
    parameter_values: dict[str, Any] = Field(default_factory=dict)

    @field_validator("decided_features", mode="before")
    @classmethod
    def _normalize_decided_features(cls, v):
        if isinstance(v, dict):
            return set(v)
        return v

    def decide_feature(self, feature_id: str, enabled: bool) -> None:
        self.decided_features.add(feature_id)
        if enabled:
            self.enabled_features.add(feature_id)
        else:
            self.enabled_features.discard(feature_id)

    def decide_parameter(self, parameter_id: str, value: Any = None) -> None:
        self.decided_parameters.add(parameter_id)
        if value is not None:
            self.parameter_values[parameter_id] = value

    def is_decided(self, feature_id: str) -> bool:
        return feature_id in self.decided_features

    def is_enabled(self, feature_id: str) -> bool:
        return feature_id in self.enabled_features

    def parameter_value(self, parameter_id: str) -> Any:
        return self.parameter_values.get(parameter_id)
```

Note: `models.py` line 8 currently imports only `BaseModel`. Update it to
`from pydantic import BaseModel, Field, field_validator` (`Field` is required
by `PartialSpec`'s `default_factory` defaults; `BackendSpec` uses plain `= []`
defaults and does not use `Field`).

- [ ] **Step 4: Run test to verify it passes**

Run: `& "C:\Users\BS00861\Documents\GitHub\Laya Supabase\system\backend-compiler\.venv\Scripts\python.exe" -m pytest tests/unit/test_mcq.py -q`
Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add backend-compiler/compiler/spec/models.py backend-compiler/tests/unit/test_mcq.py
git commit -m "Add PartialSpec model for MCQ engine"
```

---

### Task 2: `Question` model and `next_questions` selector

**Files:**
- Create: `compiler/mcq/__init__.py`
- Create: `compiler/mcq/selector.py`
- Test: `tests/unit/test_mcq.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_mcq.py`:

```python
from compiler.mcq.selector import Question, next_questions
from compiler.spec.models import PartialSpec


def test_no_questions_when_feature_disabled(ontology):
    spec = PartialSpec(decided_features={"authentication": False}, enabled_features=set())
    qs = next_questions(spec, ontology)
    assert not any(q.feature_id == "bookings" for q in qs)


def test_parameter_question_only_after_feature_enabled(ontology):
    spec = PartialSpec(
        decided_features={"authentication", "bookings"},
        enabled_features={"authentication", "bookings"},
        decided_parameters=set(),
    )
    qs = next_questions(spec, ontology)
    assert any(q.parameter_id == "mode" and q.feature_id == "bookings" for q in qs)


def test_parameter_question_skipped_after_answered(ontology):
    spec = PartialSpec(
        decided_features={"authentication", "bookings"},
        enabled_features={"authentication", "bookings"},
        decided_parameters={"bookings.mode"},
    )
    qs = next_questions(spec, ontology)
    assert not any(q.parameter_id == "mode" and q.feature_id == "bookings" for q in qs)


def test_dependency_pruning_payments_without_auth(ontology):
    spec = PartialSpec(decided_features=set(), enabled_features=set())
    qs = next_questions(spec, ontology)
    assert not any(q.feature_id == "payments" for q in qs)


def test_question_target_values(ontology):
    q = Question(type="confirm_feature", feature_id="payments", options=["yes", "no"], confidence=0.5)
    assert q.target == "features.payments"
    q2 = Question(type="choose_parameter", feature_id="bookings", parameter_id="mode",
                  options=["instant", "owner_approval"], confidence=0.5)
    assert q2.target == "parameters.bookings.mode"
    q3 = Question(type="clarify_unparsed", unparsed_index=1, options=["messaging"], confidence=0.5)
    assert q3.target == "unparsed.1"
```

Note: §18.10 constructs `Question(...)` with keyword args only; keep `Question` a plain pydantic model (no custom `__init__` needed — unlike `Candidate`, no spec test builds it positionally).

- [ ] **Step 2: Run test to verify it fails**

Run: `& "C:\Users\BS00861\Documents\GitHub\Laya Supabase\system\backend-compiler\.venv\Scripts\python.exe" -m pytest tests/unit/test_mcq.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'compiler.mcq'`

- [ ] **Step 3: Implement the package, `Question`, and `next_questions`**

Create `compiler/mcq/__init__.py`:

```python
"""MCQ engine (Developer Spec.md §4)."""
```

Create `compiler/mcq/selector.py`:

```python
"""Question model and the per-state question selector (Spec §4.1/§4.2)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from compiler.ontology.loader import Ontology
from compiler.spec.models import PartialSpec

__all__ = ["Question", "QuestionType", "next_questions"]

QuestionType = Literal[
    "confirm_feature",
    "choose_parameter",
    "resolve_contradiction",
    "resolve_negation",
    "clarify_unparsed",
    "confirm_weak",
]


class Question(BaseModel):
    type: QuestionType
    feature_id: str | None = None
    parameter_id: str | None = None
    unparsed_index: int | None = None
    options: list[str] = Field(default_factory=list)
    confidence: float = 0.5
    prompt: str = ""

    @property
    def target(self) -> str:
        if self.type == "clarify_unparsed":
            return f"unparsed.{self.unparsed_index}"
        if self.parameter_id is not None:
            return f"parameters.{self.feature_id}.{self.parameter_id}"
        return f"features.{self.feature_id}"


def next_questions(spec: PartialSpec, ontology: Ontology,
                   confidence: dict[str, float] | None = None) -> list[Question]:
    """Features/parameters needing confirmation (Developer Spec.md §4.1)."""
    confidence = confidence or {}
    questions = []
    for feature_id, feature in ontology.features.items():
        if not spec.is_decided(feature_id):
            if all(dep in spec.enabled_features for dep in feature.requires):
                questions.append(Question(
                    type="confirm_feature",
                    feature_id=feature_id,
                    options=["yes", "no"],
                    confidence=confidence.get(feature_id, 0.5),
                    prompt=f"Enable {feature_id}?",
                ))
        elif spec.is_enabled(feature_id):
            for param_name, param in feature.parameters.items():
                key = f"{feature_id}.{param_name}"
                if key not in spec.decided_parameters:
                    questions.append(Question(
                        type="choose_parameter",
                        feature_id=feature_id,
                        parameter_id=param_name,
                        options=list(param.options),
                        confidence=confidence.get(key, 0.5),
                        prompt=f"Choose {key}",
                    ))
    return questions
```

- [ ] **Step 4: Run test to verify it passes**

Run: `& "C:\Users\BS00861\Documents\GitHub\Laya Supabase\system\backend-compiler\.venv\Scripts\python.exe" -m pytest tests/unit/test_mcq.py -q`
Expected: all pass (Task 1's 6 + Task 2's 5 = `11 passed`)

- [ ] **Step 5: Commit**

```bash
git add backend-compiler/compiler/mcq backend-compiler/tests/unit/test_mcq.py
git commit -m "Add Question model and next_questions selector"
```

---

### Task 3: `order_questions` with six tiers

**Files:**
- Create: `compiler/mcq/thresholds.py`
- Create: `compiler/mcq/graph.py`
- Test: `tests/unit/test_mcq.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_mcq.py`:

```python
from compiler.mcq.graph import order_questions
from compiler.mcq.selector import Question


def _q(type_, feature_id, confidence=0.5):
    return Question(type=type_, feature_id=feature_id,
                    parameter_id=None, options=[], confidence=confidence)


def test_question_ordering_negation_second(ontology):
    qs = [
        _q("confirm_feature", "messaging"),
        _q("resolve_contradiction", "bookings"),
        _q("resolve_negation", "payments"),
        _q("clarify_unparsed", None),
    ]
    ordered = order_questions(qs)
    assert ordered[0].type == "resolve_contradiction"
    assert ordered[1].type == "resolve_negation"
    assert ordered[2].type == "clarify_unparsed"
    assert ordered[3].type == "confirm_feature"


def test_confirm_feature_confidence_split(ontology):
    qs = [
        _q("confirm_feature", "bookings", confidence=0.70),
        _q("confirm_feature", "messaging", confidence=0.30),
    ]
    ordered = order_questions(qs, ontology)
    assert [q.feature_id for q in ordered] == ["messaging", "bookings"]


def test_choose_parameter_ordered_by_feature_depth(ontology):
    qs = [
        Question(type="choose_parameter", feature_id="favorites", parameter_id="x",
                 options=[], confidence=0.5),
        Question(type="choose_parameter", feature_id="bookings", parameter_id="mode",
                 options=[], confidence=0.5),
    ]
    ordered = order_questions(qs, ontology)
    assert [q.feature_id for q in ordered] == ["bookings", "favorites"]


def test_confirm_weak_sorts_last(ontology):
    qs = [_q("confirm_feature", "bookings"), _q("confirm_weak", "authentication")]
    ordered = order_questions(qs, ontology)
    assert ordered[-1].type == "confirm_weak"
```

Expected ordering rule: `bookings` has depth 1 (requires `authentication`),
`favorites` has depth 2 (requires `authentication`, `bookings`).

- [ ] **Step 2: Run test to verify it fails**

Run: `& "C:\Users\BS00861\Documents\GitHub\Laya Supabase\system\backend-compiler\.venv\Scripts\python.exe" -m pytest tests/unit/test_mcq.py::test_question_ordering_negation_second -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'compiler.mcq.graph'`

- [ ] **Step 3: Implement thresholds and ordering**

Create `compiler/mcq/thresholds.py`:

```python
"""Confidence thresholds (Developer Spec.md §3.4)."""

from __future__ import annotations

__all__ = ["AUTO_ACCEPT", "MCQ_MIN", "WEAK_MIN"]

CONFIDENCE_AUTO_ACCEPT = 0.75
CONFIDENCE_MCQ_MIN = 0.35
CONFIDENCE_WEAK_MIN = 0.20

AUTO_ACCEPT = CONFIDENCE_AUTO_ACCEPT
MCQ_MIN = CONFIDENCE_MCQ_MIN
WEAK_MIN = CONFIDENCE_WEAK_MIN
```

Create `compiler/mcq/graph.py`:

```python
"""Question ordering (Developer Spec.md §4.3)."""

from __future__ import annotations

from compiler.mcq.selector import Question
from compiler.mcq.thresholds import MCQ_MIN
from compiler.ontology.loader import Ontology

__all__ = ["order_questions"]


def _feature_depths(ontology: Ontology) -> dict[str, int]:
    depths: dict[str, int] = {}

    def depth(fid: str, stack: frozenset[str]) -> int:
        if fid in depths:
            return depths[fid]
        if fid in stack:  # cycle guard: validator flags cycles separately
            return 0
        requires = ontology.features[fid].requires
        d = 0 if not requires else 1 + max(depth(r, stack | {fid}) for r in requires)
        depths[fid] = d
        return d

    for fid in ontology.features:
        depth(fid, frozenset())
    return depths


def _rank(q: Question) -> int:
    if q.type == "resolve_contradiction":
        return 0
    if q.type == "resolve_negation":
        return 1
    if q.type == "clarify_unparsed":
        return 2
    if q.type == "confirm_feature":
        return 3 if q.confidence < MCQ_MIN else 4
    if q.type == "choose_parameter":
        return 5
    if q.type == "confirm_weak":  # unranked in §4.3; sorts last
        return 6
    return 7


def order_questions(questions: list[Question],
                    ontology: Ontology | None = None) -> list[Question]:
    """Order questions by type priority, then dependency depth (if ontology
    given), then ids. Stable — preserves caller order within a tie."""
    depths = _feature_depths(ontology) if ontology else {}
    return sorted(
        questions,
        key=lambda q: (
            _rank(q),
            depths.get(q.feature_id or "", 0),
            q.feature_id or "",
            q.parameter_id or "",
        ),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `& "C:\Users\BS00861\Documents\GitHub\Laya Supabase\system\backend-compiler\.venv\Scripts\python.exe" -m pytest tests/unit/test_mcq.py -q`
Expected: all pass (`15 passed`)

- [ ] **Step 5: Commit**

```bash
git add backend-compiler/compiler/mcq backend-compiler/tests/unit/test_mcq.py
git commit -m "Add order_questions six-tier question ordering"
```

---

### Task 4: Fold candidates into decisions

**Files:**
- Create: `compiler/mcq/pipeline.py`
- Test: `tests/unit/test_mcq.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_mcq.py`:

```python
from compiler.mcq.pipeline import fold_candidates
from compiler.spec.models import Candidate


def test_fold_classifies_feature_and_param(ontology):
    cands = [
        Candidate("bookings.enabled", True, 1.0, "exact", "bookings"),
        Candidate("bookings.mode", "instant", 1.0, "exact", "instant"),
    ]
    result = fold_candidates(cands, ontology)
    assert result.spec.is_enabled("bookings")
    assert result.spec.parameter_value("bookings.mode") == "instant"


def test_fold_laya_needs_feature_uses_bool(ontology):
    cands = [Candidate("needs_payments", True, 0.95, "laya", None)]
    result = fold_candidates(cands, ontology)
    assert result.spec.is_enabled("payments")


def test_fold_ignores_entity_and_unknown(ontology):
    cands = [
        Candidate("needs_profiles", True, 0.95, "laya", None),
        Candidate("bogus.target", True, 0.95, "laya", None),
    ]
    result = fold_candidates(cands, ontology)
    assert result.spec.decided_features == set()
    assert "bogus.target" in result.unsupported


def test_fold_neutral_confidence_leaves_open(ontology):
    cands = [Candidate("needs_bookings", True, 0.5, "laya", None)]
    result = fold_candidates(cands, ontology)
    assert not result.spec.is_decided("bookings")
    assert result.feature_confidence.get("bookings") == 0.5


def test_fold_conflict_creates_negation(ontology):
    cands = [
        Candidate("payments.enabled", True, 0.9, "phrase", "pay"),
        Candidate("payments.enabled", False, 0.9, "phrase_negated", "no pay"),
    ]
    result = fold_candidates(cands, ontology)
    assert not result.spec.is_decided("payments")
    assert any(q.type == "resolve_negation" and q.feature_id == "payments"
               for q in result.negations)


def test_fold_role_implies_roles_feature(ontology):
    cands = [Candidate("roles.owner", True, 0.9, "phrase", "owner")]
    result = fold_candidates(cands, ontology)
    assert result.spec.is_enabled("roles")
    assert result.spec.parameter_value("roles.role_names") == ["owner"]


def test_fold_seeded_decided_feature_not_overridden_no_negation(ontology):
    spec = PartialSpec()
    spec.decide_feature("payments", enabled=False)
    cands = [
        Candidate("payments.enabled", True, 0.95, "phrase", "pay"),
        Candidate("payments.enabled", False, 0.95, "phrase_negated", "no pay"),
    ]
    result = fold_candidates(cands, ontology, spec=spec)
    assert result.spec is spec  # the seeded spec is carried through
    assert not result.spec.is_enabled("payments")
    assert result.negations == []


def test_fold_param_candidate_for_unenabled_feature_not_decided(ontology):
    cands = [Candidate("authentication.method", "oauth_google", 1.0, "phrase", "google")]
    result = fold_candidates(cands, ontology)
    assert "authentication.method" not in result.spec.decided_parameters
    assert not result.spec.is_enabled("authentication")


def test_fold_negated_role_not_collected(ontology):
    cands = [Candidate("roles.admin", False, 0.9, "phrase_negated", "no admins")]
    result = fold_candidates(cands, ontology)
    assert not result.spec.is_decided("roles")
    assert "roles.role_names" not in result.spec.decided_parameters


def test_fold_role_names_kept_when_roles_decided_this_pass(ontology):
    cands = [
        Candidate("roles.enabled", True, 0.9, "phrase", "roles on"),
        Candidate("roles.admin", True, 0.9, "phrase", "admins"),
    ]
    result = fold_candidates(cands, ontology)
    assert result.spec.is_enabled("roles")
    assert result.spec.parameter_value("roles.role_names") == ["admin"]
```

`fold_candidates` is made public (not `_fold_candidates`) so tests can target
it directly; `run_mcq_loop` is added in Task 6.

- [ ] **Step 2: Run test to verify it fails**

Run: `& "C:\Users\BS00861\Documents\GitHub\Laya Supabase\system\backend-compiler\.venv\Scripts\python.exe" -m pytest tests/unit/test_mcq.py::test_fold_classifies_feature_and_param -q`
Expected: FAIL — `ImportError: cannot import name 'fold_candidates' from 'compiler.mcq.pipeline'`

- [ ] **Step 3: Implement the fold**

Create `compiler/mcq/pipeline.py`:

```python
"""run_mcq_loop — turn interpreter candidates into a resolved spec + open MCQ
questions (Developer Spec.md §3.4 / §4 / §18.13)."""

from __future__ import annotations

from dataclasses import dataclass, field

from compiler.mcq.selector import Question
from compiler.mcq.thresholds import AUTO_ACCEPT, MCQ_MIN, WEAK_MIN
from compiler.ontology.loader import Ontology
from compiler.spec.models import Candidate, PartialSpec

__all__ = ["FoldResult", "fold_candidates", "run_mcq_loop"]


@dataclass
class FoldResult:
    spec: PartialSpec = field(default_factory=PartialSpec)
    feature_confidence: dict[str, float] = field(default_factory=dict)
    negations: list[Question] = field(default_factory=list)
    unsupported: list[str] = field(default_factory=list)


def _classify(capability_id: str, ontology: Ontology):
    """Return ('feature', fid), ('parameter', 'fid.pid'), ('role', role)
    or ('entity', name) / ('unknown', raw)."""
    if capability_id.startswith("needs_"):
        name = capability_id[len("needs_"):]
        if name in ontology.features:
            return "feature", (name,)
        if name in ontology.entities:
            return "entity", (name,)
        return "unknown", (capability_id,)
    if capability_id.endswith(".enabled"):
        fid = capability_id[: -len(".enabled")]
        if fid in ontology.features:
            return "feature", (fid,)
        return "unknown", (capability_id,)
    if "." in capability_id:
        fid, _, pid = capability_id.partition(".")
        feature = ontology.features.get(fid)
        if feature is not None and pid in feature.parameters:
            return "parameter", (capability_id,)
        if fid == "roles" and capability_id.startswith("roles."):
            return "role", (capability_id[len("roles."):],)
        return "unknown", (capability_id,)
    return "unknown", (capability_id,)


def fold_candidates(candidates: list[Candidate], ontology: Ontology,
                    spec: PartialSpec | None = None) -> FoldResult:
    """Apply interpreter candidates to a PartialSpec by confidence threshold.

    Auto-decides feature/parameter targets with a single high-confidence
    (>= AUTO_ACCEPT) value; records negation conflicts, per-feature
    confidence for ordering bands, and unsupported capability ids.

    `spec` seeds the partial state (user answers already applied). Already
    decided targets are never overridden, and no negation question is
    surfaced for a feature the user has already decided.
    """
    result = FoldResult(spec=spec or PartialSpec())
    seeded_roles = spec is not None and spec.is_decided("roles")
    feature_values: dict[str, list[tuple[Any, float]]] = {}
    param_values: dict[str, list[tuple[Any, float]]] = {}
    roles: list[str] = []

    for cand in candidates:
        kind, payload = _classify(cand.capability_id, ontology)
        if kind == "feature":
            feature_values.setdefault(payload[0], []).append((cand.value, cand.confidence))
        elif kind == "parameter":
            param_values.setdefault(payload[0], []).append((cand.value, cand.confidence))
        elif kind == "role":
            if cand.value:
                roles.append(payload[0])
        elif kind == "unknown":
            result.unsupported.append(cand.capability_id)
        # "entity" candidates are ignored: entities are derived from
        # activated features by recompute_spec.

    for fid, proposals in feature_values.items():
        best = max(proposals, key=lambda p: p[1])
        result.feature_confidence[fid] = best[1]
        if result.spec.is_decided(fid):
            continue
        distinct = {value for value, _ in proposals}
        if len(distinct) > 1:
            result.negations.append(Question(
                type="resolve_negation", feature_id=fid,
                options=["yes", "no"], confidence=best[1],
                prompt=f"Conflicting signals for {fid}. Enable it?",
            ))
            continue
        value, conf = best
        if conf >= AUTO_ACCEPT:
            result.spec.decide_feature(fid, enabled=bool(value))

    for key, proposals in param_values.items():
        if key in result.spec.decided_parameters:
            continue
        best = max(proposals, key=lambda p: p[1])
        if best[1] >= AUTO_ACCEPT:
            fid = key.partition(".")[0]
            if result.spec.is_enabled(fid):
                result.spec.decide_parameter(key, value=best[0])

    if roles and not seeded_roles:
        if not result.spec.is_decided("roles"):
            result.spec.decide_feature("roles", enabled=True)
        if result.spec.is_enabled("roles"):
            result.spec.decide_parameter("roles.role_names", value=sorted(set(roles)))

    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `& "C:\Users\BS00861\Documents\GitHub\Laya Supabase\system\backend-compiler\.venv\Scripts\python.exe" -m pytest tests/unit/test_mcq.py -q`
Expected: all pass (`25 passed`)

- [ ] **Step 5: Commit**

```bash
git add backend-compiler/compiler/mcq/pipeline.py backend-compiler/tests/unit/test_mcq.py
git commit -m "Add candidate fold with threshold auto-decisions"
```

---

### Task 5: Coverage and contradiction questions

**Files:**
- Modify: `compiler/spec/validator.py`
- Modify: `compiler/mcq/pipeline.py`
- Test: `tests/unit/test_mcq.py`

- [ ] **Step 1: Refactor validator's constraint predicate to be public (test stays green)**

Edit `compiler/spec/validator.py`:

- Replace the body of `_constraint_matches` (lines 136–152) with a delegation, and add the new public function.

```python
def constraint_holds(cond: ConstraintCond, features: dict[str, bool],
                     parameters: dict[str, Any]) -> bool:
    """True when a constraint condition holds against feature/parameter state."""
    feature_id = cond.feature
    if cond.parameter is None:
        return features.get(feature_id) == cond.value
    if not features.get(feature_id):
        return False
    key = f"{feature_id}.{cond.parameter}"
    if key not in parameters:
        return False
    actual = parameters[key]
    if cond.contains is not None:
        return isinstance(actual, list) and cond.contains in actual
    return actual == cond.value


def _constraint_matches(constraint: ConstraintDef, spec: BackendSpec) -> bool:
    return constraint_holds(constraint.if_, spec.features, spec.parameters)
```

- [ ] **Step 2: Add coverage + contradiction test (fails)**

Append to `tests/unit/test_mcq.py`:

```python
from compiler.interpreter.merge import check_coverage
from compiler.mcq.pipeline import contradiction_questions, coverage_questions


def test_coverage_question_per_unparsed_sentence(ontology):
    text = "Users can message each other. Owners can reject bad actors."
    cands = [Candidate("messaging.enabled", True, 0.9, "phrase", "s1")]
    qs = coverage_questions(text, cands, ontology, resolved={})
    assert len(qs) == 1
    assert qs[0].type == "clarify_unparsed"
    assert qs[0].unparsed_index == 1
    assert qs[0].target == "unparsed.1"
    assert "payments" in qs[0].options


def test_coverage_resolved_index_skipped(ontology):
    text = "We need bookings. Owners can reject bad actors."
    cands = [Candidate("bookings.enabled", True, 0.9, "phrase", "bookings")]
    qs = coverage_questions(text, cands, ontology, resolved={1: "bookings"})
    assert len(qs) == 0


def test_contradiction_surfaced_and_resolvable(ontology):
    cands = [
        Candidate("authentication.enabled", True, 1.0, "exact", "auth"),
        Candidate("bookings.enabled", True, 1.0, "exact", "bookings"),
        Candidate("bookings.mode", "instant", 1.0, "exact", "instant"),
    ]
    features = {"authentication": True, "bookings": True}
    params = {"bookings.mode": "instant"}
    qs = contradiction_questions(features, params, ontology)
    assert len(qs) == 1 and qs[0].type == "resolve_contradiction"
    assert qs[0].target == "features.bookings"

    params2 = {"bookings.mode": "owner_approval"}
    assert contradiction_questions(features, params2, ontology) == []


def test_contradiction_skips_soft_severity(ontology):
    from compiler.ontology.loader import ConstraintCond, ConstraintDef
    soft = ConstraintDef(
        type="contradicts", severity="soft",
        if_=ConstraintCond(feature="bookings", parameter="mode", value="instant"),
        then=ConstraintCond(feature="verification", value=True),
        message="soft conflict",
    )
    ontology.constraints.append(soft)
    features = {"authentication": True, "bookings": True}
    params = {"bookings.mode": "instant"}
    # Only the fixture's HARD contradicts surfaces; the soft copy is skipped.
    assert len(contradiction_questions(features, params, ontology)) == 1


def test_coverage_identical_unparsed_sentences_both_asked(ontology):
    text = "Owners can reject bad actors. Owners can reject bad actors."
    qs = coverage_questions(text, [], ontology, resolved={})
    assert [q.unparsed_index for q in qs] == [0, 1]
```

Note: the fixture ontology's hard `contradicts` constraint is the pair
`if bookings.mode == instant  then verification == true`; the pipeline that
implements contradiction triggering calls `constraint_holds(cond.if_, ...)`
on every `contradicts` constraint and mirrors the validator trigger semantics
(`if_` side only).

- [ ] **Step 3: Implement coverage + contradiction helpers (fails until code)**

Edit `compiler/mcq/pipeline.py`:

- Extend imports: add `inspect`-free direct imports — `from compiler.interpreter.merge import check_coverage`, `from compiler.interpreter.negation import SENTENCE_BOUNDARY`, `from compiler.spec.validator import constraint_holds`.
- Extend `__all__` with `coverage_questions`, `contradiction_questions`.
- Also add `constraint_holds` to `validator.py`'s `__all__` (the file keeps
  strict export discipline).
- Append functions:

```python
def coverage_questions(text: str, candidates: list[Candidate], ontology: Ontology,
                       resolved: dict[int, str]) -> list[Question]:
    """clarify_unparsed questions for sentences still unmapped (Spec §3.6)."""
    unparsed = check_coverage(text, candidates)
    questions = []
    options = sorted(ontology.features)
    # Re-derive original sentence indexes from the SAME split check_coverage
    # uses (identical boundaries/strip), walking the unparsed list in order.
    # Covered sentences never match an unparsed entry, so their indexes pass
    # through untouched — unparsed.1 == the second sentence even when the
    # first was covered. (An earlier while-resolved counter misaligned gaps
    # from covered sentences; this version cannot.)
    unparsed_iter = iter(unparsed)
    next_unparsed = next(unparsed_iter, None)
    for idx, chunk in enumerate(SENTENCE_BOUNDARY.split(text)):
        sentence = chunk.strip()
        if not sentence:
            continue
        if idx in resolved:
            continue
        if next_unparsed is not None and sentence == next_unparsed:
            questions.append(Question(
                type="clarify_unparsed", unparsed_index=idx,
                options=options, confidence=0.5,
                prompt=f"Which capability does this sentence describe? \"{sentence}\"",
            ))
            next_unparsed = next(unparsed_iter, None)
    return questions


def contradiction_questions(features: dict[str, bool], parameters: dict[str, Any],
                            ontology: Ontology) -> list[Question]:
    """resolve_contradiction questions for hard contradicts constraints whose
    if_ side holds (mirrors interpreter of the validator)."""
    questions = []
    for constraint in ontology.constraints:
        if constraint.type != "contradicts" or constraint.severity != "hard":
            continue
        if not constraint_holds(constraint.if_, features, parameters):
            continue
        fid = constraint.if_.feature
        questions.append(Question(
            type="resolve_contradiction", feature_id=fid,
            options=[f"Change {constraint.if_.feature}",
                     f"Reconsider {constraint.then.feature if constraint.then else 'conflict'}"],
            confidence=1.0,
            prompt=constraint.message or f"Conflicting choices involving {fid}.",
        ))
    return questions
```

Index alignment: `check_coverage` splits via `SENTENCE_BOUNDARY` and returns
only unparsed sentences. `coverage_questions` re-splits the text with the SAME
boundary and walks the unparsed list with a pointer, so each `idx` is a true
original sentence position. Covered sentences never match an unparsed entry and
therefore never advance the pointer — `unparsed.1` is always the second
sentence. This is the canonical implementation; keep the alignment mechanism as
specified here.

- [ ] **Step 4: Run test to verify it passes**

Run: `& "C:\Users\BS00861\Documents\GitHub\Laya Supabase\system\backend-compiler\.venv\Scripts\python.exe" -m pytest tests/unit/test_mcq.py -q`
Expected: all pass (`30 passed`)

- [ ] **Step 5: Run the full suite (validator refactor must stay green)**

Run: `& "C:\Users\BS00861\Documents\GitHub\Laya Supabase\system\backend-compiler\.venv\Scripts\python.exe" -m pytest -q`
Expected: `108 passed` (78 existing + 30 MCQ tests so far)

- [ ] **Step 6: Commit**

```bash
git add backend-compiler/compiler/spec/validator.py backend-compiler/compiler/mcq/pipeline.py backend-compiler/tests/unit/test_mcq.py
git commit -m "Add coverage and contradiction question generation"
```

---

### Task 6: `run_mcq_loop` — assembly and return

**Files:**
- Modify: `compiler/mcq/pipeline.py`
- Test: `tests/unit/test_mcq.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_mcq.py`:

```python
from compiler.interpreter.pipeline import run_interpreter
from compiler.mcq.pipeline import run_mcq_loop
from compiler.spec.derive import recompute_spec
from compiler.spec.models import Candidate, Decision
from compiler.spec.validator import validate


def test_run_mcq_loop_applies_answers_and_resolves(ontology):
    cands = [
        Candidate("authentication.enabled", True, 1.0, "exact", "auth"),
        Candidate("bookings.enabled", True, 1.0, "exact", "bookings"),
        Candidate("bookings.mode", "instant", 1.0, "exact", "instant"),
    ]
    spec, mcqs = run_mcq_loop(
        cands, ontology,
        user_answers={"parameters.bookings.mode": "owner_approval"},
    )
    assert spec.features.get("bookings") is True
    assert spec.parameters.get("bookings.mode") == "owner_approval"
    assert not [q for q in mcqs if q.type == "resolve_contradiction"]
    assert validate(spec, ontology).ok


def test_run_mcq_loop_surfaces_open_questions(ontology):
    cands = [Candidate("needs_payments", True, 0.5, "laya", None)]
    spec, mcqs = run_mcq_loop(cands, ontology)
    assert spec.features.get("payments") is False or spec.features.get("payments") is None
    types = {q.type for q in mcqs}
    assert "confirm_feature" in types  # payments undecided, normal band


def test_run_mcq_loop_caps_at_max_mcqs(ontology):
    cands = [Candidate(f"needs_{f}", True, 0.5, "laya", None)
             for f in ("bookings", "messaging", "payments", "reviews")]
    spec, mcqs = run_mcq_loop(cands, ontology, max_mcqs=2,
                              user_answers={"features.authentication": True})
    assert len(mcqs) == 2


def test_run_mcq_loop_answers_apply_directly_deps_validated_later(ontology):
    cands = [Candidate("needs_bookings", True, 0.5, "laya", None)]
    spec, mcqs = run_mcq_loop(cands, ontology,
                              user_answers={"features.bookings": True})
    # Answers apply directly regardless of dependencies (single-pass rule);
    # the missing authentication dependency is a *validation* concern, not a
    # prompt concern — the MCQ engine never re-asks a user-decided feature.
    assert spec.features.get("bookings") is True
    assert not validate(spec, ontology).ok  # MissingDependency(authentication)


def test_run_interpreter_to_run_mcq_loop_to_validate(ontology, mock_laya_high_confidence):
    text = "Use stripe for payments and email password for login"
    candidates = run_interpreter(text, ontology, laya=mock_laya_high_confidence)
    spec, mcqs = run_mcq_loop(candidates, ontology, text=text,
                              laya=mock_laya_high_confidence)
    assert spec.features.get("payments") is True
    assert spec.parameters.get("payments.provider") == "stripe"
    assert spec.parameters.get("authentication.method") == "email_password"
    result = validate(spec, ontology)
    assert result.ok, f"Spec failed validation: {result.errors}"


def test_run_mcq_loop_records_decisions_and_unsupported(ontology):
    cands = [
        Candidate("authentication.enabled", True, 1.0, "exact", "auth"),
        Candidate("unknown.thing", True, 0.9, "laya", None),
    ]
    spec, mcqs = run_mcq_loop(cands, ontology)
    assert "unknown.thing" in spec.unsupported
    assert any(isinstance(d, Decision) and d.capability_id == "authentication.enabled"
               for d in spec.decisions)


def test_run_mcq_loop_rejects_invalid_parameter_answers(ontology):
    spec, _ = run_mcq_loop([], ontology, user_answers={
        "parameters.nonexistent.thing": "x",      # unknown key
        "parameters.bookings.mode": "nonsense",   # not a choice option
        "parameters.realtime.channels": 5,        # list[choice] wants a list
    })
    assert spec.parameters == {}
```

Notes for correctness:
- `spec.features` should contain only decided features (True/False as decided);
  an undecided feature simply is not present.
- **Answers apply directly** (single-pass rule): a `features.<fid>` / `parameters...`
  answer is written to the partial spec *before* the fold, and the fold never
  overrides an already-decided target (see the `is_decided` guards added in
  Task 4). Dependency gating is NOT done at answer time — an ill-ordered answer
  simply produces a spec that `validate` flags (`MissingDependency`), which is
  what `test_run_mcq_loop_answers_apply_directly_deps_validated_later` asserts.
- `test_run_mcq_loop_applies_answers_and_resolves` relies on user answer
  `parameters.bookings.mode` desugaring to `decide_parameter("bookings.mode", "owner_approval")`,
  and the contradiction check re-running *after* answers are applied.

- [ ] **Step 2: Run tests to verify they fail**

Run: `& "C:\Users\BS00861\Documents\GitHub\Laya Supabase\system\backend-compiler\.venv\Scripts\python.exe" -m pytest tests/unit/test_mcq.py -q`
Expected: the 6 new tests FAIL (run_mcq_loop not yet defined or incomplete).

- [ ] **Step 3: Implement `run_mcq_loop`**

Edit `compiler/mcq/pipeline.py` — extend imports and `__all__`, then append:

```python
from datetime import datetime, timezone

from compiler.mcq.graph import order_questions
from compiler.mcq.selector import next_questions
from compiler.spec.derive import recompute_spec
from compiler.spec.models import BackendSpec, Decision


def _as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        norm = value.strip().lower()
        if norm in {"yes", "true", "1"}:
            return True
        if norm in {"no", "false", "0"}:
            return False
    return None


def _parameter_answer_ok(key: str, value: Any, ontology: Ontology) -> bool:
    """True when a parameters.<key> answer is safe to decide against the
    ontology (known key; value shape/contents match the declared type).
    Guards recompute_spec from KeyError/TypeError on malformed answers."""
    fid, _, pid = key.partition(".")
    feature = ontology.features.get(fid)
    if feature is None:
        return False
    pdef = feature.parameters.get(pid)
    if pdef is None or value is None:
        return False
    if pdef.type == "choice":
        return isinstance(value, str) and value in pdef.options
    if pdef.type == "list[choice]":
        return (isinstance(value, list) and len(value) > 0
                and all(isinstance(item, str) and item in pdef.options
                        for item in value))
    if pdef.type == "list[string]":
        return (isinstance(value, list) and len(value) > 0
                and all(isinstance(item, str) and item for item in value))
    if pdef.type == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            return False
        if pdef.min is not None and value < pdef.min:
            return False
        if pdef.max is not None and value > pdef.max:
            return False
        return True
    return isinstance(value, str) and bool(value)


def run_mcq_loop(candidates: list[Candidate], ontology: Ontology,
                 user_answers: dict[str, Any] | None = None,
                 max_mcqs: int = 10, text: str | None = None,
                 laya=None) -> tuple[BackendSpec, list[Question]]:
    """Resolve interpreter candidates into a BackendSpec, returning the
    ordered list of questions still needing user input.

    User answers are applied first (and never overridden by the fold).
    Invalid parameter answers (unknown key, wrong type, disallowed choice,
    None) are ignored."""
    user_answers = user_answers or {}
    spec = PartialSpec()

    # 1) apply user answers directly to the partial spec
    for target, value in user_answers.items():
        if target.startswith("features."):
            fid = target[len("features."):]
            if fid not in ontology.features:
                continue
            b = _as_bool(value)
            if b is not None:
                spec.decide_feature(fid, enabled=b)
        elif target.startswith("parameters."):
            key = target[len("parameters."):]
            if _parameter_answer_ok(key, value, ontology):
                spec.decide_parameter(key, value=value)

    # 2) fold candidates into the same partial spec. The fold's is_decided
    #    guards ensure user answers from step 1 are never overridden.
    folded = fold_candidates(candidates, ontology, spec=spec)

    # 3) unparsed answers (require text)
    unparsed_resolved: dict[int, str] = {}
    if text is not None:
        for target, value in user_answers.items():
            if target.startswith("unparsed."):
                try:
                    idx = int(target[len("unparsed."):])
                except ValueError:
                    continue
                if isinstance(value, str) and value in ontology.features:
                    unparsed_resolved[idx] = value
                    folded.spec.decide_feature(value, enabled=True)

    # 4) cover/open questions
    open_questions = list(folded.negations)
    if text is not None:
        open_questions.extend(coverage_questions(text, candidates, ontology,
                                                 resolved=unparsed_resolved))
    open_questions.extend(next_questions(
        folded.spec, ontology, confidence=folded.feature_confidence))

    features = {fid: fid in folded.spec.enabled_features
                for fid in folded.spec.decided_features}
    contradiction = contradiction_questions(features, dict(folded.spec.parameter_values),
                                            ontology)
    open_questions.extend(contradiction)

    ordered = order_questions(open_questions, ontology)[:max_mcqs]

    # 5) assemble the final spec
    roles = folded.spec.parameter_values.get("roles.role_names", [])
    if not isinstance(roles, list):
        roles = [roles]
    spec_out = BackendSpec(
        version="1.0",
        ontology_version=ontology.version,
        created_at=datetime.now(timezone.utc),
        features=features,
        parameters=dict(folded.spec.parameter_values),
        roles=roles,
        rls_overrides={},
        decisions=[Decision(
            capability_id=c.capability_id, value=c.value,
            confidence=c.confidence, source=c.source, evidence=c.evidence,
        ) for c in candidates],
        defaulted=[],
        unsupported=folded.unsupported,
    )
    spec_out = recompute_spec(spec_out, ontology)
    return spec_out, ordered
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `& "C:\Users\BS00861\Documents\GitHub\Laya Supabase\system\backend-compiler\.venv\Scripts\python.exe" -m pytest tests/unit/test_mcq.py -q`
Expected: all pass (`37 passed`)

- [ ] **Step 5: Run the full suite**

Run: `& "C:\Users\BS00861\Documents\GitHub\Laya Supabase\system\backend-compiler\.venv\Scripts\python.exe" -m pytest -q`
Expected: `115 passed`

- [ ] **Step 6: Commit**

```bash
git add backend-compiler/compiler/mcq/pipeline.py backend-compiler/tests/unit/test_mcq.py
git commit -m "Add run_mcq_loop pipeline with spec assembly"
```

---

### Task 7: Resolve-negation targeting, clarification answers, full-suite green

**Files:**
- Modify: `compiler/mcq/pipeline.py` (only if a test surfaces a fix)
- Test: `tests/unit/test_mcq.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_mcq.py`:

```python
def test_resolve_negation_via_answer(ontology):
    cands = [
        Candidate("payments.enabled", True, 0.9, "phrase", "pay"),
        Candidate("payments.enabled", False, 0.9, "phrase_negated", "no pay"),
    ]
    spec, mcqs = run_mcq_loop(cands, ontology,
                              user_answers={"features.payments": False})
    assert spec.features.get("payments") is False
    assert not [q for q in mcqs if q.type == "resolve_negation"]


def test_unparsed_answer_removes_coverage_question(ontology, mock_laya):
    text = "Owners can reject bad actors."
    cands = run_interpreter(text, ontology, laya=mock_laya)
    spec, mcqs = run_mcq_loop(cands, ontology, text=text,
                              user_answers={"unparsed.0": "roles"},
                              laya=mock_laya)
    assert spec.features.get("roles") is True
    assert not [q for q in mcqs if q.type == "clarify_unparsed"]
```

- [ ] **Step 2: Run tests to verify they fail (or pass)**

Run: `& "C:\Users\BS00861\Documents\GitHub\Laya Supabase\system\backend-compiler\.venv\Scripts\python.exe" -m pytest tests/unit/test_mcq.py -q`
Expected: investigate. If `test_resolve_negation_via_answer` fails (e.g. a
user feature answer for an already-negated feature must suppress the negation
question), fix `fold_candidates` to skip negation generation when the feature
is already decided by a user answer. If `test_unparsed_answer_removes_coverage_question`
fails, fix index alignment in `coverage_questions`.

- [ ] **Step 3 (conditional): Fix fold to honor user-decided features**

A correct implementation of the negation check must only surface the question
when the feature is not already decided. Adjust the negation block in
`fold_candidates`:

```python
        if len(distinct) > 1:
            if not result.spec.is_decided(fid):
                result.negations.append(Question(
                    type="resolve_negation", feature_id=fid,
                    options=["yes", "no"], confidence=best[1],
                    prompt=f"Conflicting signals for {fid}. Enable it?",
                ))
            continue
```

- [ ] **Step 4: Run the full suite**

Run: `& "C:\Users\BS00861\Documents\GitHub\Laya Supabase\system\backend-compiler\.venv\Scripts\python.exe" -m pytest -q`
Expected: `118 passed`

- [ ] **Step 5: Commit**

```bash
git add backend-compiler/compiler/mcq/pipeline.py backend-compiler/tests/unit/test_mcq.py
git commit -m "Resolve negation/unparsed via user answers"
```

---

### Task 8: Final verification and push

- [ ] **Step 1: Full test run**

Run: `& "C:\Users\BS00861\Documents\GitHub\Laya Supabase\system\backend-compiler\.venv\Scripts\python.exe" -m pytest -q`
Expected: `118 passed` (78 legacy + 40 MCQ: 6 PartialSpec, 5 selector, 4 ordering, 10 fold, 5 coverage/contradiction, 7 run_mcq_loop, 3 negation/unparsed; all GREEN)

- [ ] **Step 2: Review the tree and push**

Run (from git root `C:\Users\BS00861\Documents\GitHub\Laya Supabase\system`):
```bash
git status --short
```
Expected: only `backend-compiler/compiler/mcq/`, `backend-compiler/compiler/spec/models.py`,
`backend-compiler/compiler/spec/validator.py`, `backend-compiler/tests/unit/test_mcq.py`
(+ the design/plan docs already committed).

- [ ] **Step 3: Push**

Run: `git push origin master`
Expected: new commits on `origin/master`.

- [ ] **Step 4: Update paper outline if the MCQ engine materially changes
   architecture claims** — otherwise no-op. Report completion.

---

## Self-review notes (from the author of this plan)

- **Spec coverage:** §18.10's six tests map to Task 2 (selector tests 1–4),
  Task 3 (ordering test 5), Task 2 (Question construction -- §18.10 helper
  `_q` builds `Question(...)` with kwargs only; supported). §4.3 ordering
  tiers implemented in `graph._rank`. §3.4 thresholds in `thresholds.py` and
  `fold_candidates`. §4.1 selector logic in `selector.next_questions`. DoD
  #2 (`≤10 MCQs`) via `max_mcqs`. §3.6 coverage via Task 5. Hard
  contradictions (DoD-relevant) via Task 5.
- **Placeholder scan:** none; every step has concrete code/commands.
- **Type consistency:** `PartialSpec.decide_parameter(id, value=None)` used
  consistently across Tasks 4–6; `Question.target` is a property throughout;
  `order_questions(qs, ontology=None)` matches §18.10's one-arg call and the
  depth tests' two-arg call; `fold_candidates`/`coverage_questions`/
  `contradiction_questions` symbols match between tests and imports.
- **Known risk:** `check_coverage` uses substring evidence; the
  `coverage_questions` unparsed-index alignment (Task 5) is the most fragile
  piece — the plan's implementation walks the unparsed list in order, which
  matches `check_coverage`'s split order (opportunity underscored in-task).

## Plan corrections (reviewed before execution)

Applied to fix defects found while preparing Task dispatch (see design doc
deviation #8):

1. **Answers apply directly, no dependency gating** (Tasks 6/7): the original
   answer-merge step contradicted its own test. Resolved: answers seed the
   `PartialSpec` first; `fold_candidates(candidates, ontology, spec=spec)`
   runs on the SAME spec and its `is_decided` guards prevent the fold from
   overriding user answers; feature/param answers are never dropped for
   unmet deps (validator reports `MissingDependency`). `run_mcq_loop` merge
   steps removed. Test renamed
   `test_run_mcq_loop_answers_apply_directly_deps_validated_later`.
2. **`coverage_questions` index alignment** (Task 5): the original
   while-resolved counter misaligned gaps from covered sentences (produced
   `unparsed_index=0` for the second sentence). Replaced with a re-split +
   pointer walk over the same `SENTENCE_BOUNDARY` so `unparsed.i` matches
   true original sentence positions. Added `SENTENCE_BOUNDARY` import.
3. **Fold guards moved into Task 4** (already-decided feature/param/roles
   targets never overridden, negation suppressed for decided features), so
   Task 7 Step 3 is effectively redundant — keep it only as a verification
   note.
4. **Expected run counts corrected** to match the plan's own test
   definitions: intermediate suite totals 84/108 and full suite `118 passed`
   (78 legacy + 40 MCQ), not the mis-estimated 83/89/91.
5. **Integration test text uses the singular alias** ("email password", not
   "email passwords"): Mechanism A exact aliases are word-boundary rigid by
   design (§3.1) — plural tolerance belongs to phrase/laya mechanisms. With
   the plural form the auth-method signal degrades gracefully to a
   `choose_parameter` question instead of auto-deciding.