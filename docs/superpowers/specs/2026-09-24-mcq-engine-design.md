# MCQ Engine — Design

- **Date:** 2026-09-24
- **Status:** Approved (brainstorming gate)
- **Source spec:** `Developer Spec.md` §4 (MCQ Engine), §18.10 (unit tests), §18.13 (golden runner dependency), §3.4 (confidence thresholds), §11 Phase 5
- **Repo:** `Laya Supabase/system` (backend-compiler)

## Context

Phase 1 (ontology + spec IR + derivation + validator) and the interpreter layer
(exact/phrase/negation extraction, merge, coverage, Laya client, calibration)
are complete (`f94f747`). The next sub-project is the MCQ engine: the piece
that turns a list of `Candidate`s into a pending set of questions and a final
`BackendSpec`. The golden runner (`tests/golden`, §18.13) imports
`compiler.mcq.pipeline.run_mcq_loop`, so this engine is a prerequisite for it.

## Scope

- `PartialSpec` — added to `compiler/spec/models.py` (§18.10 imports it from there).
- `Question` — in `compiler/mcq/selector.py` (§18.10 imports it from there).
- `compiler/mcq/selector.py` — `next_questions(spec, ontology)` (§4.1).
- `compiler/mcq/graph.py` — `order_questions(qs, ontology)` (§4.3).
- `compiler/mcq/pipeline.py` — `run_mcq_loop(...)`.
- `tests/unit/test_mcq.py` — the six §18.10 tests verbatim + pipeline tests.

Out of scope: golden runner, session API (`/v1/sessions/*`), interactive
re-asking UI, and the `confirm_weak` UX.

## Design decisions (confirmed with user)

1. **Pure single-pass loop.** `run_mcq_loop` is deterministic and stateful-free:
   fold candidates → surface ordered questions → apply applicable
   `user_answers` → re-surface until no applicable answers remain → return
   `(BackendSpec, mcqs_asked)`. No `Session` object; a future interactive
   wrapper can reuse the same fold/ask/apply functions.
2. **Target-keyed `user_answers`.** Keys name the decision target, independent
   of question type:
   - `features.<feature_id>` → bool (or `yes`/`no`/`true`/`false`, coerced)
   - `parameters.<feature_id>.<parameter_id>` → option value (list type → `list[str]`)
   - `unparsed.<sentence_index>` → ontology item id (feature id the sentence maps to)

## Models

### `PartialSpec` (in `compiler/spec/models.py`)

```python
class PartialSpec(BaseModel):
    decided_features: set[str] | dict[str, bool] = Field(default_factory=set)
    enabled_features: set[str] = Field(default_factory=set)
    decided_parameters: set[str] = Field(default_factory=set)
```

- `decided_features` accepts a `set` or a `dict[str, bool]`; the dict form is
  normalized to a `set` of its keys (test 1 of §18.10 uses `{"authentication": False}`).
  Enabling truth lives in `enabled_features`.
- Helpers: `decide_feature(id, enabled)`, `decide_parameter(id)`, `is_enabled(id)`.

### `Question` (in `compiler/mcq/selector.py`)

```python
class Question(BaseModel):
    type: QuestionType            # literal: confirm_feature | choose_parameter |
                                  #         resolve_contradiction | resolve_negation |
                                  #         clarify_unparsed | confirm_weak
    feature_id: str | None = None   # None for clarify_unparsed
    parameter_id: str | None = None
    options: list[str] = []
    confidence: float = 0.0
    prompt: str = ""

    def target(self) -> str: ...   # features.<id> | parameters.<f>.<p> | unparsed.<i>
```

`QuestionType` is a `Literal` (six values from §4.2).

## Selector — `next_questions(spec, ontology)` (§4.1)

For each ontology feature:

1. If `feature.id not in spec.decided_features` and every id in
   `feature.requires` is in `spec.enabled_features` → `confirm_feature`
   question (options `["yes", "no"]`).
2. Else if `feature.id in spec.enabled_features` → one `choose_parameter`
   question per undecided parameter, options from ontology parameter
   `options` (list types keep their options/preformed values).

## Ordering — `order_questions(qs, ontology)` (§4.3)

Six tiers:

1. `resolve_contradiction`
2. `resolve_negation`
3. `clarify_unparsed`
4. `confirm_feature` with `confidence < MCQ_MIN` (0.35)
5. `confirm_feature` with `confidence >= MCQ_MIN`
6. `choose_parameter`

Within a tier, sort by feature dependency depth (longest path from a root
feature) ascending, then `feature_id`. Sort is stable. Defaults:
`MCQ_MIN = 0.35`, `AUTO_ACCEPT = 0.75`, `WEAK_MIN = 0.20` (configurable
constants).

## Pipeline — `run_mcq_loop`

```
run_mcq_loop(
    candidates: list[Candidate],
    ontology: Ontology,
    user_answers: dict[str, Any] | None = None,
    max_mcqs: int = 10,
    text: str | None = None,
    laya=None,
) -> tuple[BackendSpec, list[Question]]
```

1. **Fold.** Classify each candidate by `capability_id`:
   - `X.enabled` (X ∈ features) → feature decision (value bool).
   - `needs_X` (X ∈ features, Laya source) → feature decision (`bool(noul >= 0.5)`).
   - `X.param` (X feature, param exists) → parameter decision.
   - `roles.<role>` → parameter decision for `roles.role_names` (append role).
   - `needs_X` (X ∈ entities) → ignored; entities are derived by
     `recompute_spec` from activated features.
   - unknown id → recorded as unsupported, ignored.
2. **Threshold** each target by the best candidate (source + confidence):
   - two distinct values for one target → conflict → `resolve_negation`.
   - conf ≥ `AUTO_ACCEPT` → auto-decide.
   - conf ≥ `MCQ_MIN` → `confirm_feature` (or `choose_parameter` for params).
   - conf ≥ `WEAK_MIN` → weak `confirm_feature`.
   - conf < `WEAK_MIN` → dropped unless source is `exact`/`phrase`/
     `phrase_negated`, in which case a flagged weak `confirm_feature`.
3. **Coverage** (only if `text` given): `check_coverage(text, outcomes)` →
   `clarify_unparsed` per unparsed sentence.
4. **Hard contradictions**: ontology constraints of type `contradicts` where
   both sides are decided-true → `resolve_contradiction`; options synthesized
   from the two flip-sides of the constraint.
5. **Loop** (max `len(features) + 2` iterations): `next_questions` +
   conflict/coverage/contradiction questions → `order_questions` → for each
   whose `target()` is in `user_answers`, apply the answer and re-surface;
   break when no answer applied in the iteration. Total surfaced questions
   capped at `max_mcqs`.
6. **Assemble** `BackendSpec` from the settled PartialSpec (features,
   parameters, roles, decisions as `Decision` records) then
   `recompute_spec(spec, ontology)` fills derived fields.
7. Return `(spec, mcqs_asked)`.

`mcqs_asked` = every question surfaced across iterations (user-facing count,
capped at `max_mcqs`) — matches DoD #2 and the §18.13 `len(mcqs) <= max_mcqs`
assert.

## Error handling

- Unknown `capability_id` → unsupported, never raised.
- Invalid `user_answers` values (unknown option, wrong type) → ignored and
  treated as unanswered (question stays in `mcqs_asked`).
- Contradiction unresolved (no user answer) → surfaced question returned;
  final spec still assembled (validator may flag it; golden authors provide
  answers to resolve).

## Testing plan (`tests/unit/test_mcq.py`)

- The six §18.10 tests verbatim (no-questions-when-disabled, param-after-enable,
  param-skipped-after-answered, dependency-pruning, ordering-negation-second,
  Question positional construction).
- Fold/threshold: low-confidence mock (`noul 0.5`) → `confirm_feature`
  surfaced; high-confidence mock (`noul 0.95`) → auto-accepted, no question.
- Exact `stripe` (conf 1.0) → `payments` auto-decided true.
- Negation conflict (phrase True + phrase_negated False) → `resolve_negation`.
- Unparsed sentence → `clarify_unparsed` (target `unparsed.0`).
- Hard contradiction (`bookings` instant × `verification`) → `resolve_contradiction`.
- Target-keyed `user_answers` applied → final `BackendSpec` correct.
- `max_mcqs` cap respected.
- End-to-end `run_interpreter → run_mcq_loop → validate` ok.

## Flagged deviations (documented in code and tests)

1. `run_mcq_loop` adds **optional** `text=` and `max_mcqs=` kwargs; the §18.13
   call site (`user_answers=`, `laya=`) works unchanged.
2. `PartialSpec.decided_features` accepts `set | dict` (§18.10 test 1 needs the
   dict form).
3. `clarify_unparsed` generation requires `text`; without it, that source is
   skipped.
4. `mcqs_asked` is counted before answers are applied (represents what the user
   would be asked), capped at `max_mcqs`.
5. `resolve_contradiction` options are synthesized from the ontology constraint
   (two flip-side labels); UX wording is deferred to the UI phase.