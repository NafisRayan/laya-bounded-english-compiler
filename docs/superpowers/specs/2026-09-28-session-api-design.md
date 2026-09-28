# Session API — design

- **Date:** 2026-09-28
- **Status:** Approved design, ready for implementation planning
- **Source spec:** `Developer Spec.md` §11 Phase 5 ("API endpoints"), §14 (endpoint list), §12 (tech stack), DoD #1 / #2
- **Depends on:** `compiler/interpreter/pipeline.py::run_interpreter`, `compiler/mcq/pipeline.py::run_mcq_loop`, `compiler/interpreter/laya_client.py::LayaClient` (lazy-import), `compiler/ontology/loader.py::load_ontology`, `compiler/spec/validator.py::validate`, `tests/conftest.py::MockLayaClient`

## Purpose

Expose the interpreted-session loop (`text → MCQs → BackendSpec`) as an HTTP
API behind the §14 endpoint list. This is the service the Phase 6 frontend
consumes and the last piece separating DoD #1 ("paste 1–3 sentences → working
Supabase project") from a running product. The API is a thin, stateless
wrapper over the already-complete interpreter/MCQ/validate pipeline — no new
modeling logic lives here.

## Design decisions (confirmed with user)

1. **All 9 §14 endpoints; deploy-side stubbed.** `sessions`, `interpret`,
   `answer`, `spec`, `approve` are real. The four deploy-side endpoints
   (`deploy`, `deploy/status`, `remediate`, `logs`) return **501 Not
   Implemented** — the deployer is Phase 3 and does not exist yet. Stubs keep
   the §14 URL surface stable now; the deployer fills them later.
2. **FastAPI + uvicorn** (per §12). New runtime deps: `fastapi`, `uvicorn`;
   `httpx` is required by Starlette's `TestClient` (test-time). Sync `def`
   endpoints (FastAPI runs them in its threadpool). **No async, no
   pytest-asyncio** — deviation from §12's "pytest + pytest-asyncio" (nothing
   in this layer is awaitable).
3. **Stateless re-run.** A session stores only `{text, answers}`. Every
   `interpret`/`answer`/`spec` call re-runs `run_interpreter(text)` then
   `run_mcq_loop(text, answers, client)` and returns the freshly computed
   result. Consistent with the engine's single-pass design; idempotent; no
   speculative caching or server-side partial state to drift. The engine's
   ignore-invalid-answer semantics (§4.3, `run_mcq_loop` step 1 +
   `_parameter_answer_ok`) make stale/partial `answers` degrade gracefully.
   Text is locked after first `interpret` (see endpoint semantics) so a
   session's questions always correspond to one source string.
4. **In-memory session store behind an interface.** `SessionStore` protocol +
   `InMemorySessionStore` (dict + `RLock`, 7-day TTL with lazy eviction on
   access). **Deviation from §12 "State store: Postgres"** — no Postgres exists
   in the venv project, and sessions are short-lived interpret→answer flows; a
   Postgres-backed store implementing the same interface slots in at deployer
   time with no API changes.
5. **Dependency injection via `create_app`.** `create_app(client, sessions,
   ontology)` wires the routes. Tests inject `MockLayaClient` + a fresh store
   + the fixture ontology. The default wiring constructs the real `LayaClient`
   **lazily** (first interpreter call); if the `laya` package is missing it
   raises a **503** instead of failing startup — matching the module's
   deferred-import philosophy (`laya_client.py:23`).

## Architecture

```
compiler/api/__init__.py               # NEW — exports create_app
compiler/api/schemas.py                # NEW — pydantic request/response models
compiler/api/store.py                  # NEW — SessionStore protocol + InMemorySessionStore
compiler/api/app.py                    # NEW — create_app(), router, endpoint handlers
tests/unit/test_session_store.py       # NEW — store semantics + TTL
tests/integration/test_session_api.py  # NEW — TestClient end-to-end over the 9 routes
```

No changes to existing compiler modules. Production code added is only the
`compiler/api/` package (plus three new venv deps).

## Session model

```python
class Session:
    id: str            # uuid4().hex (32 chars)
    created_at: datetime  # timezone-aware UTC
    status: Literal["new", "collecting", "complete", "approved"]
    text: str | None
    answers: dict[str, Any]      # keyed by Question.target; union merge
    max_mcqs: int = 10           # clamped [1, 10]; set at interpret; re-runs reuse it
```

`SessionStore` (protocol): `create() -> Session` · `get(id) -> Session | None`
(evicts expired entries on access) · `save(session)`. `InMemorySessionStore`
implements it with `RLock`; expiry checks `now − created_at > 7 days` and drops
the entry (**404** at the route layer).

## Endpoint semantics

| Endpoint | Success | Failure modes |
|---|---|---|
| `POST /v1/sessions` | `201` `{id, created_at, status}` (status `new`) | — |
| `POST …/interpret` body `{text, max_mcqs?}` | `200` `{status, questions, remaining}`; sets `text`, status `collecting` | `404` unknown id; `409` if `text` already set and `answers` nonempty (text lock); `422` empty text; `503` laya unavailable |
| `POST …/answer` body `{answers}` | `200` `{status, questions, remaining, finished}`; merges answers (repeat target replaces), re-runs; status → `complete` when `remaining == 0` | `404`; `409` if `text` unset (must interpret first); `503` |
| `GET …/spec` | `200` `{spec, validation, open_questions}`; re-runs with current answers | `404`; `409` if `text` unset; `503` |
| `POST …/approve` | `200` `{status: "approved"}`; requires `complete`, marks approved, **no deploy action** | `404`; `409` if not `complete` (open questions remain) |
| `POST …/deploy` | `501` | — |
| `GET …/deploy/status` | `501` | — |
| `POST …/remediate` | `501` | — |
| `GET …/logs` | `501` | — |

`remaining` = `len(ordered_questions)` after the engine's `[:max_mcqs]` cap
(`run_mcq_loop` line 276). `max_mcqs` optional in interpret body, default 10,
clamped to `[1, 10]` (DoD #2: ≤10 complex, ≤3 simple). `questions` serialize as
`Question.model_dump()` **plus the computed `target`** (a `@property`, not a
model field — `selector.py:36`) so the frontend can echo answers back by
target. `spec` is `BackendSpec.model_dump()`; `validation` is
`{ok, errors: [str], warnings: [str]}` (messages only — `ValidationIssue` is
not directly serializable). Stale/invalid targets in `answers` are dropped by
the engine, so unanswered or malformed answers simply leave their question
open.

## Data flow

```
interpret/answer/spec call
  └─ session = sessions.get(id)            # lazy TTL eviction → 404 if gone
     └─ scan = run_interpreter(text, ontology, laya)      # mechanisms A+B+C, merge
        └─ spec, mcqs = run_mcq_loop(scan, ontology, user_answers=answers, text=text, laya=client, max_mcqs)
           └─ validate(spec, ontology)     # only for GET /spec
```

Laya is resolved lazily once per call: `client()` provider is invoked on first
use; `ImportError`/construction failure → `503 {"detail": "laya unavailable"}`.

## Error handling summary

- `404` — unknown/expired session id (all id-route handlers)
- `409` — state violations: interpret-after-answers, answer/spec-before-interpret, approve-while-open
- `422` — FastAPI request validation (empty `text`, missing body)
- `501` — the four deploy-side stubs
- `503` — `laya` client construction failure at request time

## Testing

- **`tests/unit/test_session_store.py`** (~5 tests): create assigns id/status; get/save round trip; unknown id → None; **TTL lazy eviction** (save a `Session` with `created_at` backdated past TTL → `get` returns None); fresh session survives `get`.
- **`tests/integration/test_session_api.py`** (~12 tests, FastAPI `TestClient`, `MockLayaClient`, fresh in-memory store per test): (1) happy path — create → interpret `"We need bookings and messaging"` (default client: **exactly 2 questions**, `clarify_unparsed unparsed.0` + `confirm_feature features.authentication`, empirically pinned) → answer the pinned combined set (resolve `unparsed.0 = authentication`, disable the six laya-confirmed features, choose `authentication.method = email_password`) → `remaining == 0`, `finished` true, status `complete` → `GET /spec` `validation.ok == True` → `approve` → `200 approved`; (2) interpret idempotence — 409 on second interpret once answers exist, 200 when answers still empty; (3) answer before interpret → 409; (4) spec before interpret → 409; (5) approve on incomplete → 409, approve without text → 409; (6) every 501 stub sampled (4 endpoints, correct HTTP verb); (7) unknown id → 404 on all 4 id-routes (valid bodies); (8) 422 empty text; (9) 503 via a client provider that raises; (10) stale answer dropped — unknown `features.*` target leaves the same 2 questions open; (11) `max_mcqs` clamp — 1 → 1 question, 50 → clamped to 10 (2 < 10, unchanged), 0 → clamped up to 1; (12) `GET /spec` before completion lists the 2 open questions and validates ok. Expected counts pinned during planning.

Target full-suite count: **140 → ~157**.

## Deviations from Developer Spec.md (documented)

1. **§12 "State store: Postgres" → in-memory `InMemorySessionStore`** behind a `SessionStore` interface; Postgres implementation deferred to deployer.
2. **§12 "pytest + pytest-asyncio" → sync `TestClient`** (FastAPI sync `def` endpoints); no async dependency added.
3. **§14 deploy-side endpoints stubbed `501`** — deployer is Phase 3, not built; §14 specifies the list, not semantics, so stub bodies are this doc's definition.
4. **§14 session-flow semantics (order, text lock, approve gating) are this doc's definition** — the spec lists endpoints only.