# Golden test runner — design

- **Date:** 2026-09-25
- **Status:** Approved design, ready for implementation planning
- **Source spec:** `Developer Spec.md` §18.13 (Golden test runner)
- **Depends on:** MCQ engine (implemented 2026-09-24 — `run_interpreter` → `run_mcq_loop` → `validate` all public and green at 118 tests)

## Purpose

End-to-end YAML-driven cases that run the full natural-language → spec pipeline
(`run_interpreter` → `run_mcq_loop` → `validate`) against the merged v1 fixture
ontology and assert the resulting spec and open questions. This is the DoD gate
for the MCQ engine: it proves the phases compose, not just that units pass.

## Design decisions (confirmed with user)

1. **Persona flag per case** replaces §18.13's hash-keyed `laya_responses`
   (sha256 of `(state, questions)` is impossible to hand-author). Each case
   picks `laya: default | high | none`, reusing `MockLayaClient` / the HighConf
   double from `tests/conftest.py`.
2. **`text=` is passed** to `run_mcq_loop` so coverage questions
   (`clarify_unparsed`) can surface and `unparsed.N` answers resolve — the full
   engine is exercised, not a subset. §18.13's literal call site predates the
   `text=` kwarg.
3. **Typed case schema** (`GoldenCase`, pydantic) validates each YAML at
   collection time — malformed cases fail loudly with the filename, not as
   confusing asserts deep in the engine.
4. **~10 behavior cases** (11 landed, see below), one pinned behavior each.

## Architecture

New files only, under `tests/golden/`:

```
tests/golden/
├── __init__.py          # empty package marker
├── test_golden.py       # GoldenCase schema + runner + spec_matches
└── cases/*.yaml         # 11 hand-authored cases
```

No compiler code changes. Reuses: `run_interpreter`,
`compiler.mcq.pipeline.run_mcq_loop`, `compiler.spec.validator.validate`,
`tests.conftest.ontology` (session-scoped fixture applies to subdirectories),
`MockLayaClient` and its HighConf subclass.

## Case schema

```python
class GoldenCase(BaseModel):
    input: str
    laya: Literal["default", "high", "none"] = "default"
    user_answers: dict[str, Any] = Field(default_factory=dict)
    expected_spec: dict[str, Any]            # required; partial submatch
    expect_question_types: list[str] = Field(default_factory=list)   # all must appear
    absent_question_types: list[str] = Field(default_factory=list)   # none may appear
    absent_question_targets: list[str] = Field(default_factory=list) # no q.target may match
    max_mcqs: int = 10
    validate_ok: bool = True
```

Persona semantics:

- `"default"` — `MockLayaClient()`: noul answers at 0.5 (weak signals → the
  engine asks, does not decide)
- `"high"` — HighConf double: 0.95 noul (signals clear AUTO_ACCEPT →
  auto-decide)
- `"none"` — `_NoLaya` empty-answer double. `run_interpreter` **always** calls
  `predict` (verified: `pipeline.py:50`), so `laya=None` is not an option; the
  double returns an envelope with no answers so only the deterministic
  exact/phrase mechanisms run.

`expected_spec` is §18.13's partial match over `spec.model_dump()`: dict keys
submatch per key, list keys compare sorted, absent keys unchecked. Time-varying
or bulky keys (`created_at`, `decisions`) stay out of case files.

`expect_question_types` strengthens the gate beyond
`len(mcqs) <= max_mcqs`: every listed question type must actually appear among
the returned `mcqs` (e.g. the contradiction case asserts `resolve_contradiction`
surfaces, not merely that the spec is clean). `absent_question_types` is the
negative twin: none of the listed types may appear (used by the
negation-resolved case). `absent_question_targets` pins **feature-level**
absence that type-level checks cannot express — the dependency-pruning case
asserts no question targets `features.favorites` while `confirm_feature`
questions exist for other features.

`validate_ok` (default `True`) relaxes §18.13's unconditional
`result.ok` assertion to an equality check. The contradiction-surfacing case
needs `validate_ok: false`: surfacing a hard contradiction means the spec is,
by definition, invalid — that is the behavior being pinned.

## Runner flow

```python
def test_golden(case_path, ontology):
    case = GoldenCase.model_validate(yaml.safe_load(case_path.read_text()))
    mock = _persona(case.laya)
    candidates = run_interpreter(case.input, ontology, laya=mock)
    spec, mcqs = run_mcq_loop(candidates, ontology,
                              user_answers=case.user_answers,
                              text=case.input,
                              laya=mock)
    diffs = spec_matches(spec, case.expected_spec)
    assert not diffs, f"{case_path.stem}: spec mismatch — {diffs}"
    for qtype in case.expect_question_types:
        assert any(q.type == qtype for q in mcqs), \
            f"{case_path.stem}: expected {qtype} question, got {[q.type for q in mcqs]}"
    for qtype in case.absent_question_types:
        assert not [q for q in mcqs if q.type == qtype], \
            f"{case_path.stem}: {qtype} should be absent"
    for target in case.absent_question_targets:
        assert not [q for q in mcqs if q.target == target], \
            f"{case_path.stem}: nothing should target {target}"
    assert len(mcqs) <= case.max_mcqs
    result = validate(spec, ontology)
    assert result.ok == case.validate_ok, \
        f"{case_path.stem}: validate ok={result.ok}, expected {case.validate_ok}"
```

Parametrization is §18.13's `pytest_generate_tests` over
`sorted(cases.glob("*.yaml"))`, ids = file stems. The test loads and validates
the YAML itself (so the schema error carries the filename and the runner keeps
using `case_path.stem` in every failure message).

`spec_matches` keeps §18.13's semantics but returns a list of mismatches
`(key, subkey, expected, actual)` instead of a bare bool, so failures print a
diff list. List comparison sorts by `json.dumps(x, sort_keys=True)` so a
list-of-dicts value (e.g. `buckets`) cannot crash `sorted()` with `TypeError`.

`validate(spec, ontology).ok` is asserted **unconditionally** for every case
(per §18.13). Cases that intentionally produce ill-validated specs belong in
unit tests, not golden cases.

## The 11 cases

Each case pins one behavior end-to-end. **All texts and expectations below were
pinned by running the real engine during plan authoring** (no guessed
assertions). Two vocabulary lessons are baked in:

- Exact-alias words also phrase-match (e.g. "stripe" and "payments" both hit
  the payments phrase rule), so Mechanism A cannot be isolated — case 1 pins
  the combined exact+phrase path instead.
- Role phrase rules are singular-only (`\b(admin|moderator|staff)\b`), so
  "Admins" never fires; case 9 uses "An admin".

| # | File | `laya` | Pins |
|---|------|--------|------|
| 1 | `alias_and_phrase_decide.yaml` | none | Exact alias ("stripe", "email password") + phrase decide `payments` and its provider; with `features.authentication: true` answered, the auth method alias also lands (fold runs after answers); validate ok; `choose_parameter` present |
| 2 | `laya_default_asks.yaml` | default | 0.5 signals → nothing decided (empty spec); `confirm_feature` + `clarify_unparsed` present |
| 3 | `laya_high_decides.yaml` | high | 0.95 signals → features + params auto-decided, validate ok; `choose_parameter` present, `confirm_feature`/`resolve_negation` absent |
| 4 | `negation_resolved_by_answer.yaml` | none | Conflicting phrase+negated payments signals + `features.payments: false` answer → `resolve_negation` absent; payments False; validate ok |
| 5 | `contradiction_surfaced.yaml` | none | auth+bookings answered, `bookings.mode: instant` → `resolve_contradiction` present; spec invalid by definition (`validate_ok: false`) |
| 6 | `contradiction_resolved.yaml` | none | Same but `owner_approval` → contradiction absent; validate ok |
| 7 | `unparsed_coverage_resolved.yaml` | default | Junk sentence, `unparsed.0: authentication` answered → auth decided; `clarify_unparsed` absent; validate ok |
| 8 | `dep_pruning.yaml` | default | auth answered, bookings/messaging weak → favorites' confirm pruned (`absent_question_targets: [features.favorites]`) while other confirms present |
| 9 | `roles_phrases.yaml` | none | "An admin can manage the platform." → `roles` enabled, `role_names: [admin]`, validate ok |
| 10 | `max_mcqs_cap.yaml` | default | 8 questions pre-cap (clarify + 6 confirms + choose_parameter), `max_mcqs: 4` → at most 4 returned |
| 11 | `empty_spec_junk_text.yaml` | none | Junk text, no candidates → empty valid spec; `clarify_unparsed` + `confirm_feature` still asked (coverage + auth are always askable) |

An "unsupported capability" case was considered and dropped: unknown-id
candidates cannot be produced through the public text pipeline (unit tests
construct them directly).

## Deviations from §18.13 (documented)

1. Persona flag (`laya:`) replaces hash-keyed `laya_responses`.
2. `text=case.input` passed to `run_mcq_loop`.
3. `GoldenCase` pydantic schema replaces raw dict access.
4. `spec_matches` returns collected mismatches instead of `bool`; list sorting
   is JSON-canonical so dict entries cannot crash it.
5. `expect_question_types` / `absent_question_types` added (not in §18.13).
6. The second `recompute_spec` call in §18.13's sketch is dropped:
   `run_mcq_loop` already returns a recomputed spec (calling it twice is a
   no-op; the sketch predated that).
7. `absent_question_targets` and `validate_ok` schema fields (§18.13 has no
   equivalent; needed for the pruning and contradiction-surfacing pins).
8. Persona `"none"` is an empty-answer mock double, not `laya=None` —
   `run_interpreter` unconditionally calls `predict`.

## Failure UX

- Malformed YAML → pydantic `ValidationError` naming the file, at collection
  time.
- Spec mismatches print the diff list; failing case identified by pytest id
  (the file stem).

## Definition of done

- Full suite green: 118 existing + 11 golden = **129 expected** (exact count
  pinned when the cases run).
- Zero compiler-code changes.
- Same review/push discipline as the MCQ phase: implementer + spec review +
  quality review per task, final whole-feature review, then push `master`.
