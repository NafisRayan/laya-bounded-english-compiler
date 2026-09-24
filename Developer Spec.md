# Backend Compiler — Developer Specification

**Version:** 1.10
**Status:** Implementation-ready
**Audience:** Backend/ML engineers building the system

**Changelog:**
- v1.1 — Added Section 18 (Test Suite Implementation)
- v1.2 — Patched 7 gaps
- v1.3 — Patched 4 gaps
- v1.4 — Patched 5 gaps
- v1.5 — Fixed `merge()` tier-collision bug
- v1.6 — Added realtime channel-feature coupling constraints
- v1.7 — Fixed `_spec()` test helper
- v1.8 — Corrected Laya integration (checkpoint, calibration, mock, env vars)
- **v1.9 — Fixed `predict_batch` signature (list-of-dicts, no `model=` kwarg); dropped `models={"english": None}` (breaks library default loading); aligned `MockLayaClient` envelope with real library shape (`model: "laya-rl-agent"`, `routing: {model, repo, reason}`, `usage: {input_tokens, output_tokens}`, `action: {act_probability}`); fixed `criteria[0]` → `next(iter(criteria))` to handle dict-valued criteria**
- **v1.10 — Made `_make_laya_answer` treat `act_probability` as a separate, pinnable quantity (real action head is independently trained, `agent.py:676`); `MockLayaClient.__init__` now documents why `super().__init__()` is skipped (it builds a real preloading Router) and sets explicit `router`/`calibration` placeholders so a future missed override fails loudly; added contract test that `act_probability` is independent of `noul`**

This document is self-contained. Every decision that would normally be a question is made here.

---

## 0. Product Definition & Scope

**What it is:** A deterministic compiler that takes a natural-language description of a backend and produces a working Supabase project. **Not an LLM wrapper.** It is a deterministic, template-based code generator with an NLP front end.

**Input:** Natural-language text (1–500 words) describing an app's backend needs.

**Output:** A deployed Supabase project with tables, RLS policies, auth config, storage buckets, edge functions, and realtime enabled — plus a JSON spec that can regenerate it.

**Core invariant:** The system must never silently omit a requirement it failed to understand. It either classifies with confidence, asks via MCQ, or flags unsupported.

**Out of scope for v1:** custom business logic beyond templates; data migration; multi-tenant orgs; non-Supabase targets.

**Terminology note:** "Generator" and "compiler" are used interchangeably. The composer is a template-based code generator built with compiler-backend rigor.

---

## 1. System Architecture

### 1.1 High-level pipeline

```
User text
  → Requirement Interpreter (aliases + rules + character-span negation + Laya)
  → Candidate requirements with confidence scores
  → Confidence gate (confident / ambiguous / unsupported)
  → MCQ Engine (for ambiguous, respecting dependency graph)
  → Backend Specification (IR)
  → Derivation (features → entities, buckets, edge_functions)
  → Validator (constraint satisfiability + derivation invariants)
  → User approval (UI)
  → Generator (fragment composition → SQL + function source)
  → Deployer (create project once, reuse on retry)
  → Error classifier → remediation MCQ → retry (max 3, same project)
```

### 1.2 Service decomposition

| Service | Responsibility | Tech |
|---|---|---|
| `api` | HTTP API, session state, user auth | FastAPI + Postgres |
| `interpreter` | Text → candidates (incl. negation) | Python, calls Laya |
| `laya-worker` | Batched Laya inference | Python, GPU or CPU |
| `mcq-engine` | Dependency graph, question selection | Python |
| `spec` | IR models + validator + derivation | Python + Pydantic |
| `generator` | Fragment composition → migrations + function source | Python + Jinja2 |
| `deployer` | Supabase Management API + CLI orchestration | Python + subprocess |
| `ontology-store` | Versioned ontology definitions | Postgres |

For MVP, all services can be one Python process. Split when load requires.

### 1.3 Repository layout

```
backend-compiler/
├── compiler/
│   ├── api/
│   ├── interpreter/
│   │   ├── aliases.py
│   │   ├── rules.py
│   │   ├── negation.py
│   │   ├── laya_client.py
│   │   ├── calibration.py
│   │   └── merge.py
│   ├── mcq/
│   │   ├── graph.py
│   │   └── selector.py
│   ├── spec/
│   │   ├── models.py
│   │   ├── derive.py
│   │   └── validator.py
│   ├── generator/
│   │   ├── composer.py
│   │   ├── ordering.py
│   │   ├── fragment_spec_map.py
│   │   ├── fragments/
│   │   └── edge_templates/
│   ├── deployer/
│   │   ├── deployer.py
│   │   ├── supabase_api.py
│   │   ├── auth_config.py
│   │   ├── storage_config.py
│   │   ├── realtime_config.py
│   │   ├── edge_functions.py
│   │   ├── cli.py
│   │   └── errors.py
│   └── ontology/
│       ├── loader.py
│       └── versions/v1/
│           ├── entities.yaml
│           ├── features.yaml
│           ├── roles.yaml
│           ├── rls.yaml
│           ├── constraints.yaml
│           └── calibration.json
├── tests/
├── pyproject.toml
└── .github/workflows/ci.yml
```

---

## 2. The Ontology

### 2.1 Entities (`entities.yaml`)

```yaml
version: 1
entities:
  users:
    managed_by: supabase_auth
    fields:
      id: {type: uuid, pk: true}
      email: {type: text, unique: true}
      created_at: {type: timestamptz, default: now()}

  profiles:
    fields:
      id: {type: uuid, pk: true, fk: users.id, on_delete: cascade}
      display_name: {type: text}
      avatar_url: {type: text, nullable: true}
      bio: {type: text, nullable: true}
      role: {type: text, default: "'user'"}
      created_at: {type: timestamptz, default: now()}
    auto_create_on: users.insert

  listings:
    fields:
      id: {type: uuid, pk: true, default: gen_random_uuid()}
      owner_id: {type: uuid, fk: users.id, on_delete: cascade}
      title: {type: text}
      description: {type: text}
      category: {type: text}
      price_cents: {type: integer}
      status: {type: text, default: "'draft'"}
      created_at: {type: timestamptz, default: now()}
      updated_at: {type: timestamptz, default: now()}
    indexes:
      - {columns: [owner_id]}
      - {columns: [category, status]}

  bookings:
    fields:
      id: {type: uuid, pk: true, default: gen_random_uuid()}
      listing_id: {type: uuid, fk: listings.id, on_delete: cascade}
      renter_id: {type: uuid, fk: users.id, on_delete: cascade}
      owner_id: {type: uuid, fk: users.id, on_delete: cascade}
      start_at: {type: timestamptz}
      end_at: {type: timestamptz}
      status: {type: text, default: "'pending'"}
      created_at: {type: timestamptz, default: now()}
    indexes:
      - {columns: [listing_id, start_at, end_at]}
      - {columns: [renter_id]}
      - {columns: [owner_id]}

  messages:
    fields:
      id: {type: uuid, pk: true, default: gen_random_uuid()}
      sender_id: {type: uuid, fk: users.id, on_delete: cascade}
      recipient_id: {type: uuid, fk: users.id, on_delete: cascade}
      booking_id: {type: uuid, fk: bookings.id, nullable: true, on_delete: set null}
      body: {type: text}
      created_at: {type: timestamptz, default: now()}
    indexes:
      - {columns: [sender_id, recipient_id]}
      - {columns: [booking_id]}

  payments:
    fields:
      id: {type: uuid, pk: true, default: gen_random_uuid()}
      booking_id: {type: uuid, fk: bookings.id, nullable: true, on_delete: set null}
      payer_id: {type: uuid, fk: users.id, on_delete: cascade}
      amount_cents: {type: integer}
      currency: {type: text, default: "'usd'"}
      provider: {type: text, default: "'stripe'"}
      provider_ref: {type: text}
      status: {type: text, default: "'pending'"}
      created_at: {type: timestamptz, default: now()}

  reviews:
    fields:
      id: {type: uuid, pk: true, default: gen_random_uuid()}
      booking_id: {type: uuid, fk: bookings.id, on_delete: cascade}
      author_id: {type: uuid, fk: users.id, on_delete: cascade}
      subject_id: {type: uuid, fk: users.id, on_delete: cascade}
      rating: {type: integer}
      body: {type: text}
      created_at: {type: timestamptz, default: now()}

  files:
    fields:
      id: {type: uuid, pk: true, default: gen_random_uuid()}
      owner_id: {type: uuid, fk: users.id, on_delete: cascade}
      bucket: {type: text}
      path: {type: text}
      mime_type: {type: text}
      size_bytes: {type: integer}
      created_at: {type: timestamptz, default: now()}

  verification_documents:
    fields:
      id: {type: uuid, pk: true, default: gen_random_uuid()}
      user_id: {type: uuid, fk: users.id, on_delete: cascade}
      document_type: {type: text}
      storage_path: {type: text}
      status: {type: text, default: "'pending'"}
      reviewed_by: {type: uuid, fk: users.id, nullable: true}
      reviewed_at: {type: timestamptz, nullable: true}
      created_at: {type: timestamptz, default: now()}

  favorites:
    fields:
      user_id: {type: uuid, fk: users.id, on_delete: cascade, pk: true}
      listing_id: {type: uuid, fk: listings.id, on_delete: cascade, pk: true}
      created_at: {type: timestamptz, default: now()}

  notifications:
    fields:
      id: {type: uuid, pk: true, default: gen_random_uuid()}
      user_id: {type: uuid, fk: users.id, on_delete: cascade}
      kind: {type: text}
      payload: {type: jsonb}
      read_at: {type: timestamptz, nullable: true}
      created_at: {type: timestamptz, default: now()}
    indexes:
      - {columns: [user_id, read_at]}
```

**Rules:**
- Every table gets `id uuid pk` unless `managed_by: supabase_auth` or composite PK.
- Every table gets `created_at timestamptz default now()` unless specified.
- Every FK gets an index automatically.
- `updated_at` triggers added only if the entity declares the field.

### 2.2 Features (`features.yaml`)

```yaml
features:
  authentication:
    requires: []
    activates_entities: [profiles]
    activates_edge_functions: []
    parameters:
      method:
        type: choice
        options: [email_password, magic_link, oauth_google, oauth_github]

  roles:
    requires: [authentication]
    activates_entities: []
    activates_edge_functions: []
    parameters:
      role_names: {type: list[string], min: 1, max: 5}

  bookings:
    requires: [authentication]
    activates_entities: [listings, bookings]
    activates_edge_functions: []
    parameters:
      mode: {type: choice, options: [instant, owner_approval, request_then_approval, time_slot]}

  messaging:
    requires: [authentication]
    activates_entities: [messages]
    activates_edge_functions: []
    parameters:
      trigger_event: {type: choice, options: [before_booking, after_request, after_approval, anytime]}

  payments:
    requires: [authentication]
    activates_entities: [payments]
    activates_edge_functions: [stripe_webhook]
    parameters:
      provider: {type: choice, options: [stripe]}

  reviews:
    requires: [bookings]
    activates_entities: [reviews]
    activates_edge_functions: []

  file_storage:
    requires: [authentication]
    activates_entities: [files]
    activates_edge_functions: []
    parameters:
      bucket_purpose: {type: choice, options: [avatars, listings, documents, mixed]}

  verification:
    requires: [authentication, file_storage]
    activates_entities: [verification_documents]
    activates_edge_functions: [verification_webhook]
    parameters:
      method: {type: choice, options: [email, phone, government_id, admin_approval, government_id_and_admin]}

  realtime:
    requires: [authentication]
    activates_entities: [notifications]
    activates_edge_functions: [notification_dispatch]
    parameters:
      channels:
        type: list[choice]
        options: [messages, notifications, bookings]

  favorites:
    requires: [authentication, bookings]
    activates_entities: [favorites]
    activates_edge_functions: []
```

**Activation rules:** a feature can only be enabled if all its `requires` are enabled. Enabling with unmet `requires` triggers a cascade MCQ. Disabling a required feature triggers a cascade warning.

### 2.3 Roles (`roles.yaml`)

```yaml
roles:
  guest: {authenticated: false}
  user: {authenticated: true}
  owner:
    authenticated: true
    derived_from: user
    condition: "exists(listings where owner_id = auth.uid())"
  renter:
    authenticated: true
    derived_from: user
  admin:
    authenticated: true
    assigned_by: "profiles.role = 'admin'"
  verifier:
    authenticated: true
    assigned_by: "profiles.role = 'verifier'"
```

Role conditions compile into SQL helper functions: `is_owner(uuid)`, `is_admin()`, etc.

### 2.4 RLS patterns (`rls.yaml`)

```yaml
rls_patterns:
  public_read:         {sql: "true"}
  authenticated_read:  {sql: "auth.uid() IS NOT NULL"}
  owner_only:          {sql: "auth.uid() = owner_id"}
  owner_or_admin:      {sql: "auth.uid() = owner_id OR is_admin()"}
  participant_only:    {sql: "auth.uid() IN (renter_id, owner_id)"}
  sender_or_recipient: {sql: "auth.uid() IN (sender_id, recipient_id)"}
  role_restricted:     {sql: "EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND role = '{role}')"}
```

### 2.5 Constraints (`constraints.yaml`)

```yaml
constraints:
  - type: requires
    if: {feature: payments, value: true}
    then: {feature: authentication, value: true}
    message: "Payments requires authentication."

  - type: requires
    if: {feature: reviews, value: true}
    then: {feature: bookings, value: true}
    message: "Reviews require bookings."

  - type: requires
    if: {feature: verification, value: true}
    then: {feature: file_storage, value: true}
    message: "Verification requires file storage for documents."

  - type: requires
    if: {feature: favorites, value: true}
    then: {feature: bookings, value: true}
    message: "Favorites requires listings (via bookings)."

  - type: requires
    if: {feature: realtime, parameter: channels, contains: messages}
    then: {feature: messaging, value: true}
    message: "Realtime messaging requires the messaging feature."

  - type: requires
    if: {feature: realtime, parameter: channels, contains: bookings}
    then: {feature: bookings, value: true}
    message: "Realtime booking updates require the bookings feature."

  - type: contradicts
    if: {feature: bookings, parameter: mode, value: instant}
    then: {feature: verification, value: true}
    reason: "Instant booking is incompatible with owner verification."
    severity: hard

  - type: weakens
    if: {feature: messaging, parameter: trigger_event, value: anytime}
    then: {feature: authentication, value: true}
    reason: "Anytime messaging requires authenticated identities."
    severity: soft
```

---

## 3. Requirement Interpreter

**Input:** raw user text (string).
**Output:** `list[Candidate]` where `Candidate = {capability_id, value, confidence, source, evidence}`.

### 3.1 Three parallel mechanisms

**Mechanism A — Exact mappings.**

```python
# compiler/interpreter/aliases.py
EXACT_MAP = {
    "stripe": ("payments.provider", "stripe", 1.0),
    "google auth": ("authentication.method", "oauth_google", 1.0),
    "magic link": ("authentication.method", "magic_link", 1.0),
    "github auth": ("authentication.method", "oauth_github", 1.0),
    "email password": ("authentication.method", "email_password", 1.0),
}
```

**Mechanism B — Phrase patterns with character-span negation.**

```python
# compiler/interpreter/rules.py
PHRASE_RULES = [
    (r"\b(message|chat|dm|contact|talk to)\b.*\b(each other|users|owner|renter)\b",
     "messaging.enabled", True, 0.9),
    (r"\b(book|reserve|rent)\b.*\b(equipment|item|listing|property)\b",
     "bookings.enabled", True, 0.9),
    (r"\b(pay|charge|checkout|stripe)\b",
     "payments.enabled", True, 0.85),
    (r"\b(review|rate|rating|feedback)\b",
     "reviews.enabled", True, 0.85),
    (r"\b(upload|photo|image|file|document|avatar)\b",
     "file_storage.enabled", True, 0.8),
    (r"\b(verify|verification|kyc|id check|government id)\b",
     "verification.enabled", True, 0.8),
    (r"\b(admin|moderator|staff)\b",
     "roles.admin", True, 0.85),
    (r"\b(favorite|save for later|saved items|bookmark)\b",
     "favorites.enabled", True, 0.8),
]
```

**Mechanism C — Laya classification.** Batched `noul` questions. See §3.7 for client construction and envelope shape.

```python
questions = {
    f"needs_{item}": {
        "type": "noul",
        "instructions": f"Does this backend description require {item}? {description}",
    }
    for item in ontology.items
}
result = laya_client.predict(user_text, questions)
# result["answers"]["needs_listings"] == {
#     "type": "noul", "noul": 0.91,
#     "confidence": 0.91, "answer_confidence": 0.91,
#     "action": {"act_probability": 0.91}
# }
```

### 3.2 Negation detection (sentence-boundary clamped)

```python
# compiler/interpreter/negation.py
import re
from compiler.spec.models import Candidate
from compiler.interpreter.rules import PHRASE_RULES

NEGATION_PATTERNS = [
    r"\b(?:no|not|never|without|avoid|skip|except|none)\b",
    r"\b(?:don't|doesn't|won't|can't|cannot|isn't|aren't|wasn't|weren't)\b",
    r"\b(?:do not|does not|will not|can not|is not|are not|was not|were not)\b",
    r"\b(?:no need(?: for)?|don't need|do not need|don't want|do not want)\b",
    r"\b(?:shouldn't|should not|wouldn't|would not)\b",
]

NEGATION_EXCEPTIONS = [
    r"\bno matter\b",
    r"\bno doubt\b",
    r"\bnot only\b",
    r"\bnot to mention\b",
    r"\bneedless to say\b",
]

NEGATION_WINDOW_CHARS = 40
SENTENCE_BOUNDARY = re.compile(r"[.?!]\s+")


def _mask_exceptions(text: str) -> str:
    masked = text
    for exc in NEGATION_EXCEPTIONS:
        for m in re.finditer(exc, masked, flags=re.IGNORECASE):
            masked = masked[:m.start()] + (" " * (m.end() - m.start())) + masked[m.end():]
    return masked


def _clamp_window(text: str, start: int, end: int,
                  window_chars: int) -> tuple[int, int]:
    left = start
    for m in SENTENCE_BOUNDARY.finditer(text, 0, start):
        left = m.end()
    left = max(left, start - window_chars)

    right_match = SENTENCE_BOUNDARY.search(text, end)
    right = right_match.start() if right_match else len(text)
    right = min(right, end + window_chars)
    return left, right


def is_negated(text: str, match_start: int, match_end: int,
               window_chars: int = NEGATION_WINDOW_CHARS) -> bool:
    masked = _mask_exceptions(text.lower())
    win_start, win_end = _clamp_window(masked, match_start, match_end, window_chars)
    window = masked[win_start:win_end]
    for pattern in NEGATION_PATTERNS:
        if re.search(pattern, window):
            return True
    return False


def phrase_match_with_negation(text: str) -> list[Candidate]:
    candidates = []
    for pattern, capability_id, positive_value, confidence in PHRASE_RULES:
        for m in re.finditer(pattern, text, flags=re.IGNORECASE):
            negated = is_negated(text, m.start(), m.end())
            value = (not positive_value) if negated else positive_value
            source = "phrase_negated" if negated else "phrase"
            candidates.append(Candidate(
                capability_id=capability_id,
                value=value,
                confidence=confidence,
                source=source,
                evidence=text[m.start():m.end()],
            ))
    return candidates
```

**Tuning notes (Phase 4):**
- `NEGATION_WINDOW_CHARS` starts at 40, tuned against a labelled negation set.
- Pattern list expands as new false positives are found.
- Track precision/recall; DoD #9 requires ≥90% precision.

**Known limitations of `SENTENCE_BOUNDARY = r"[.?!]\s+"`:** decimals and abbreviations can split incorrectly; periods without trailing whitespace don't split. Both degrade gracefully. **Do not remove the clamp.**

### 3.3 Merge & conflict resolution

**Three priority tiers, highest-first:**
1. `exact`
2. `phrase` **and** `phrase_negated` (share one tier — conflicts surface as ambiguity)
3. `laya`

```python
# compiler/interpreter/merge.py
def merge(candidates_a, candidates_b, candidates_c):
    by_cap: dict[str, list[Candidate]] = {}
    for c in candidates_a + candidates_b + candidates_c:
        by_cap.setdefault(c.capability_id, []).append(c)

    merged = []
    for cap_id, cands in by_cap.items():
        for tier in (("exact",), ("phrase", "phrase_negated"), ("laya",)):
            same_tier = [c for c in cands if c.source in tier]
            if same_tier:
                values = {c.value for c in same_tier}
                if len(values) > 1:
                    merged.extend(same_tier)
                else:
                    merged.append(max(same_tier, key=lambda c: c.confidence))
                break
    return merged
```

**Guarantee:** no candidate silently dropped. Conflicts within a tier surface for `resolve_negation` MCQ.

### 3.4 Confidence thresholds

| Threshold | Meaning | Action |
|---|---|---|
| ≥ `AUTO_ACCEPT` (default 0.75) | Confident | Auto-accept |
| `MCQ_MIN` – `AUTO_ACCEPT` (default 0.35 – 0.75) | Ambiguous | MCQ |
| 0.20 – `MCQ_MIN` | Weak | MCQ (marked "not sure") |
| < 0.20 | Unsupported/absent | Flag if A/B matched; else ignore |

**Which Laya field feeds these thresholds:** use `answer_confidence` (§3.7), the ECE-calibrated quantity. Do not use `noul` directly.

### 3.5 Calibration (reframed in v1.8)

**Laya ships calibrated.** The library applies per-option-count and per-language temperature scaling internally and returns `answer_confidence` as the ECE-calibrated quantity. Therefore:

- **Do not fit a temperature by default.** Fitting on already-calibrated values double-scales, and `logit(0)`/`logit(1)` blow up.
- **Consume `answer_confidence` directly.**

**When to fit an extra temperature:** only if measured ECE on the golden set is ≥ 0.1 using shipped `answer_confidence`.

**Procedure if ECE ≥ 0.1:**

1. Run the base checkpoint on the golden test set (30–50 inputs).
2. Record `(answer_confidence, ground_truth_label)` per `noul` question.
3. Compute ECE with 10 bins.
4. If ECE < 0.1 → stop, no fitting. Use `answer_confidence` directly.
5. If ECE ≥ 0.1 → fit scalar `T` on **clipped** values:
   ```python
   calibrated = sigmoid(logit(clip(answer_confidence, 1e-6, 1 - 1e-6)) / T)
   ```
6. Persist per checkpoint in `calibration.json`:
   ```json
   {
     "english":      {"temperature": 1.0, "ece_before": 0.07, "ece_after": 0.07, "needs_fit": false},
     "multilingual": {"temperature": 1.0, "ece_before": 0.09, "ece_after": 0.09, "needs_fit": false}
   }
   ```
   Default `temperature: 1.0` is a no-op pass-through.

**Re-calibration triggers:** ontology version change, checkpoint change, golden set expansion, quarterly review, addition of non-English golden inputs.

### 3.6 Requirement coverage check

Every sentence must map to ≥1 candidate. Unmapped sentences become `clarify_unparsed` MCQs. Negated-unmapped sentences become `resolve_negation` candidates.

### 3.7 Laya client integration

**Checkpoint selection.** Pin `english` explicitly. Never auto-route.

| Checkpoint | When to use |
|---|---|
| **`english`** (default) | All v1 traffic |
| `multilingual` | Only when non-English golden inputs exist; needs own calibration entry |
| `laya-typed-decisions` | **Never** — task-specialized, wrong question-id schema |

```python
# compiler/interpreter/laya_client.py
import os
from laya import Router
from compiler.interpreter.calibration import apply_temperature, load_calibration


CHECKPOINT = "english"    # pinned; do not auto-route


class LayaClient:
    """
    Thin wrapper around the laya Router, pinned to the `english` checkpoint.

    Construction uses the library's documented Router API. We do NOT
    override `models` — the library's defaults already map english to
    the correct repo spec. Passing `models={"english": None}` overwrites
    the default with `None`, which then fails during preload.
    """

    def __init__(self, device: str | None = None):
        self.device = device or os.environ.get("LAYA_DEVICE", "cpu")
        # No `models=` override — library default is english →
        # ("convaiinnovations/laya", None). LRU caps at 2 loaded models,
        # irrelevant since we only use english.
        self.router = Router(device=self.device, preload=True)
        self.calibration = load_calibration()

    def predict(self, state: str, questions: dict) -> dict:
        """
        Call the Router with typed questions.

        Returns the library envelope unchanged:
            {
              "model":   "laya-rl-agent",
              "answers": { qid: { "type", "noul"|"choice", "confidence",
                                  "answer_confidence", "action": {...} }, ... },
              "usage":   {"input_tokens": ..., "output_tokens": ...},
              "routing": {"model": ..., "repo": ..., "reason": ...},
            }
        """
        return self.router.predict(state, questions, model=CHECKPOINT)

    def predict_batch(self, states: list[str], questions: dict) -> list[dict]:
        """
        Batched inference.

        Router.predict_batch takes a Sequence[Dict], where each item
        carries state/questions (and optionally model). There is no
        `model=` kwarg on predict_batch.
        """
        requests = [
            {"state": s, "questions": questions, "model": CHECKPOINT}
            for s in states
        ]
        return self.router.predict_batch(requests)

    def calibrated_confidence(self, answer: dict) -> float:
        """
        Return the calibrated confidence for an answer.

        Laya already calibrates via answer_confidence. We only apply
        an extra temperature if ECE measured ≥ 0.1 on the golden set.
        """
        raw = answer["answer_confidence"]
        T = self.calibration[CHECKPOINT]["temperature"]
        if T == 1.0:
            return raw
        return apply_temperature(raw, T)
```

**Environment variables used by this module:** `LAYA_DEVICE` (our own var, mapped to `Router(device=...)`). The library reads `HF_TOKEN` automatically when downloading weights.

---

## 4. MCQ Engine

### 4.1 Dependency graph

```python
# compiler/mcq/selector.py
def next_questions(spec: PartialSpec, ontology: Ontology) -> list[Question]:
    candidates = []
    for feature in ontology.features:
        if feature.id not in spec.decided_features:
            if all(dep in spec.enabled_features for dep in feature.requires):
                candidates.append(Question.for_feature(feature))
        elif feature.id in spec.enabled_features:
            for param in feature.parameters:
                if param.id not in spec.decided_parameters:
                    candidates.append(Question.for_parameter(feature, param))
    return candidates
```

### 4.2 Question types

| Type | Source | UI |
|---|---|---|
| `confirm_feature` | Ambiguous feature detection | Yes/No + confidence indicator |
| `choose_parameter` | Ambiguous parameter | Radio buttons (<20 options); for `list[choice]`, checkboxes |
| `resolve_contradiction` | Hard constraint violation | 2–4 options |
| `resolve_negation` | Conflicting True/False (from `merge` ambiguity) | 2–3 options |
| `clarify_unparsed` | Unparsed sentence | Dropdown of ontology items |
| `confirm_weak` | Soft constraint warning | Continue / change |

### 4.3 Question ordering

1. `resolve_contradiction`
2. `resolve_negation`
3. `clarify_unparsed`
4. `confirm_feature` (confidence < `MCQ_MIN`)
5. `confirm_feature` (`MCQ_MIN` ≤ confidence < `AUTO_ACCEPT`)
6. `choose_parameter` (topological by feature depth)

### 4.4 UX rules

- Max 3 questions visible at once.
- Every question has "I don't know, pick a default".
- Users can go back and change any answer.

---

## 5. Backend Specification (IR)

### 5.1 Schema

```python
from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel


class BackendSpec(BaseModel):
    version: Literal["1.0"]
    ontology_version: int
    created_at: datetime

    features: dict[str, bool]
    parameters: dict[str, Any]
    roles: list[str]
    rls_overrides: dict[str, str]

    entities: list[str] = []
    buckets: list[BucketSpec] = []
    edge_functions: list[str] = []

    decisions: list[Decision]
    defaulted: list[str]
    unsupported: list[str]

    project_ref: str | None = None
    deployed_at: datetime | None = None


class BucketSpec(BaseModel):
    name: str
    public: bool
    rls_pattern: str
    file_size_limit_mb: int = 10


class Decision(BaseModel):
    capability_id: str
    value: Any
    confidence: float
    source: Literal["exact", "phrase", "phrase_negated", "laya", "user", "default"]
    evidence: str | None
```

### 5.2 Spec lifecycle

`Draft → Validated → Approved → Generated → Deployed` or `Failed`. Immutable after approval; remediation creates a new version.

### 5.3 Derivation

```python
# compiler/spec/derive.py
TABLE_BACKED_REALTIME_CHANNELS = {"messages", "notifications", "bookings"}


def derive_entities(spec: BackendSpec, ontology: Ontology) -> list[str]:
    entities: set[str] = set()
    for feature_id, enabled in spec.features.items():
        if not enabled:
            continue
        if feature_id == "realtime":
            channels = set(spec.parameters.get("realtime.channels", []))
            if not (channels & TABLE_BACKED_REALTIME_CHANNELS):
                continue
        entities.update(ontology.features[feature_id].activates_entities)
    return sorted(entities)


def derive_buckets(spec: BackendSpec) -> list[BucketSpec]:
    if not spec.features.get("file_storage"):
        return []
    purpose = spec.parameters.get("file_storage.bucket_purpose", "mixed")
    mapping = {
        "avatars":   [BucketSpec(name="avatars", public=True, rls_pattern="owner_only")],
        "listings":  [BucketSpec(name="listings", public=True, rls_pattern="owner_only")],
        "documents": [BucketSpec(name="documents", public=False, rls_pattern="owner_only")],
        "mixed": [
            BucketSpec(name="avatars", public=True, rls_pattern="owner_only"),
            BucketSpec(name="listings", public=True, rls_pattern="owner_only"),
            BucketSpec(name="documents", public=False, rls_pattern="owner_only"),
        ],
    }
    buckets = list(mapping[purpose])
    if spec.features.get("verification"):
        buckets.append(BucketSpec(name="verification", public=False, rls_pattern="owner_only"))
    return buckets


def derive_edge_functions(spec: BackendSpec, ontology: Ontology) -> list[str]:
    fns: set[str] = set()
    for feature_id, enabled in spec.features.items():
        if enabled:
            fns.update(ontology.features[feature_id].activates_edge_functions)

    if spec.features.get("realtime"):
        channels = set(spec.parameters.get("realtime.channels", []))
        if not (channels & TABLE_BACKED_REALTIME_CHANNELS):
            fns.discard("notification_dispatch")

    if spec.features.get("payments") and spec.parameters.get("payments.provider") != "stripe":
        fns.discard("stripe_webhook")

    return sorted(fns)


def recompute_spec(spec: BackendSpec, ontology: Ontology) -> BackendSpec:
    return spec.model_copy(update={
        "entities": derive_entities(spec, ontology),
        "buckets": derive_buckets(spec),
        "edge_functions": derive_edge_functions(spec, ontology),
    })
```

**Invariants enforced in validator (§6):** `entities`, `buckets`, `edge_functions` must always equal their derived values. **Any `BackendSpec` constructed in test code must pass through `recompute_spec` before assertion.**

---

## 6. Validator

### 6.1 Checks

| Check | Action |
|---|---|
| Feature requires unmet | Hard reject |
| Hard constraint violated | Hard reject |
| Soft constraint violated | Warn |
| Role referenced but not defined | Hard reject |
| Entity referenced in RLS but not in `entities` | Hard reject |
| Parameter value (scalar or list member) not in ontology options | Hard reject |
| `list[string]` parameter violates min/max bounds | Hard reject |
| Circular feature dependencies | Hard reject |
| `entities` does not match derivation | Hard reject (invariant) |
| `buckets` does not match derivation | Hard reject (invariant) |
| `edge_functions` does not match derivation | Hard reject (invariant) |
| Realtime channel selected without backing feature | Hard reject (via §2.5) |

### 6.2 Implementation

```python
# compiler/spec/validator.py
from compiler.spec.derive import derive_entities, derive_buckets, derive_edge_functions


def _constraint_matches(constraint, spec) -> bool:
    cond = constraint.if_
    feature_id = cond["feature"]

    if "parameter" not in cond:
        return spec.features.get(feature_id) == cond["value"]

    if not spec.features.get(feature_id):
        return False
    key = f"{feature_id}.{cond['parameter']}"
    if key not in spec.parameters:
        return False
    actual = spec.parameters[key]

    if "contains" in cond:
        return isinstance(actual, list) and cond["contains"] in actual
    return actual == cond["value"]


def validate(spec: BackendSpec, ontology: Ontology) -> ValidationResult:
    errors = []
    warnings = []

    expected_entities = derive_entities(spec, ontology)
    if sorted(spec.entities) != expected_entities:
        errors.append(EntityDerivationError(expected_entities, spec.entities))

    expected_buckets = derive_buckets(spec)
    if sorted(b.name for b in spec.buckets) != sorted(b.name for b in expected_buckets):
        errors.append(BucketDerivationError(expected_buckets, spec.buckets))

    expected_fns = derive_edge_functions(spec, ontology)
    if sorted(spec.edge_functions) != expected_fns:
        errors.append(EdgeFunctionDerivationError(expected_fns, spec.edge_functions))

    for constraint in ontology.constraints:
        if _constraint_matches(constraint, spec):
            if constraint.type == "contradicts" and constraint.severity == "hard":
                errors.append(ValidationError(constraint))
            elif constraint.type == "weakens":
                warnings.append(ValidationWarning(constraint))
            elif constraint.type == "requires":
                then = constraint.then
                if "parameter" in then:
                    key = f"{then['feature']}.{then['parameter']}"
                    if spec.parameters.get(key) != then["value"]:
                        errors.append(ValidationError(constraint))
                else:
                    if spec.features.get(then["feature"]) != then["value"]:
                        errors.append(ValidationError(constraint))

    for feature_id, enabled in spec.features.items():
        if enabled:
            feature = ontology.features[feature_id]
            for req in feature.requires:
                if not spec.features.get(req, False):
                    errors.append(MissingDependency(feature_id, req))

    for key, value in spec.parameters.items():
        feature_id, param_id = key.split(".", 1)
        feature = ontology.features.get(feature_id)
        if not feature or param_id not in feature.parameters:
            errors.append(UnknownParameter(key))
            continue
        param = feature.parameters[param_id]
        ptype = param["type"]

        if ptype == "choice":
            if value not in param["options"]:
                errors.append(InvalidParameterValue(key, value))

        elif ptype == "list[choice]":
            if not isinstance(value, list):
                errors.append(InvalidParameterValue(key, value))
            else:
                for item in value:
                    if item not in param["options"]:
                        errors.append(InvalidParameterValue(key, item))

        elif ptype == "list[string]":
            if not isinstance(value, list):
                errors.append(InvalidParameterValue(key, value))
            else:
                if "min" in param and len(value) < param["min"]:
                    errors.append(InvalidParameterLength(key, len(value),
                                                         param["min"], param.get("max")))
                if "max" in param and len(value) > param["max"]:
                    errors.append(InvalidParameterLength(key, len(value),
                                                         param["min"], param["max"]))
                for item in value:
                    if not isinstance(item, str) or not item.strip():
                        errors.append(InvalidParameterValue(key, item))

    return ValidationResult(ok=len(errors) == 0, errors=errors, warnings=warnings)
```

---

## 7. Fragment Composition Engine

### 7.1 Fragment types

| Fragment type | Produces |
|---|---|
| `table` | `CREATE TABLE`, indexes |
| `rls` | `ENABLE ROW LEVEL SECURITY` + policies |
| `trigger` | `CREATE TRIGGER` |
| `function` | `CREATE FUNCTION` (role helpers) |
| `bucket` | Storage bucket + RLS on `storage.objects` |
| `edge_function` | Edge function source stub (scaffolded separately, §8.7) |
| `realtime` | `ALTER PUBLICATION supabase_realtime ADD TABLE` with idempotent DO block |

### 7.2 Fragment interface

```yaml
id: table_listings
type: table
requires: [function_is_admin]
provides: [entity.listings]
sql: |
  CREATE TABLE IF NOT EXISTS listings (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    ...
  );
  CREATE INDEX IF NOT EXISTS listings_owner_id_idx ON listings(owner_id);
```

Realtime fragments declare their backing table:

```yaml
id: realtime_messages
type: realtime
requires: [table_messages]
provides: [realtime.messages]
sql: |
  DO $$
  BEGIN
    IF NOT EXISTS (
      SELECT 1 FROM pg_publication_tables
      WHERE pubname = 'supabase_realtime' AND tablename = 'messages'
    ) THEN
      ALTER PUBLICATION supabase_realtime ADD TABLE messages;
    END IF;
  END $$;
```

Same pattern for `realtime_bookings`, `realtime_notifications`.

### 7.3 Composition algorithm

```python
# compiler/generator/composer.py
def compose(spec: BackendSpec, ontology: Ontology) -> list[Migration]:
    spec = recompute_spec(spec, ontology)

    fragments = []
    if spec.features.get("authentication"):
        fragments.append(load("function_is_admin"))
        fragments.append(load("function_is_owner"))
    for entity in spec.entities:
        fragments.append(load(f"table_{entity}"))
        fragments.extend(rls_for(entity, spec, ontology))
    for bucket in spec.buckets:
        fragments.append(load(f"bucket_{bucket.name}"))
    if spec.features.get("realtime"):
        for channel in spec.parameters.get("realtime.channels", []):
            fragments.append(load(f"realtime_{channel}"))
    if spec.features.get("verification"):
        fragments.append(load("trigger_verification_status"))

    ordered = topo_sort(fragments, key="requires")
    conflicts = detect_conflicts(ordered)
    if conflicts:
        raise CompositionError(conflicts)

    migrations = []
    for i, frag in enumerate(ordered):
        migrations.append(Migration(
            filename=f"{i:04d}_{frag.id}.sql",
            sql=render(frag.sql, spec=spec, ontology=ontology),
        ))
    return migrations
```

### 7.4 Conflict detection

1. Duplicate object names
2. Trigger collisions
3. RLS policy name collisions → prefix with fragment id
4. FK cycles → DFS detect
5. Ordering violations
6. Duplicate bucket names

**Policy naming:** `{table}_{operation}_{fragment_id}`.

### 7.5 Idempotency

Every migration uses `IF NOT EXISTS` / `DROP POLICY IF EXISTS` / `DROP TRIGGER IF EXISTS` / `DO $$ ... $$` guards.

---

## 8. Supabase Generator & Deployer

### 8.1 Project creation

```python
# compiler/deployer/supabase_api.py
def create_project(name: str, region: str, org_slug: str, db_pass: str) -> str:
    resp = requests.post(
        "https://api.supabase.com/v1/projects",
        headers={"Authorization": f"Bearer {SUPABASE_ACCESS_TOKEN}"},
        json={
            "name": name,
            "organization_slug": org_slug,
            "region_selection": {"type": "smartGroup", "code": region},
            "db_pass": db_pass,
        },
    )
    resp.raise_for_status()
    return resp.json()["ref"]
```

### 8.2 Wait for readiness

```python
def wait_for_healthy(ref: str, timeout: int = 600) -> None:
    start = time.time()
    while time.time() - start < timeout:
        resp = requests.get(
            f"https://api.supabase.com/v1/projects/{ref}/health",
            headers={"Authorization": f"Bearer {SUPABASE_ACCESS_TOKEN}"},
        )
        if all(s["status"] == "ACTIVE_HEALTHY" for s in resp.json()):
            return
        time.sleep(10)
    raise TimeoutError(f"Project {ref} did not become healthy in {timeout}s")
```

### 8.3 Apply migrations

```python
import os
import shutil
from pathlib import Path


def link_project(ref: str, db_pass: str) -> None:
    env = os.environ.copy()
    env["SUPABASE_DB_PASSWORD"] = db_pass
    subprocess.run(
        ["supabase", "link", "--project-ref", ref],
        check=True, capture_output=True, text=True, env=env,
    )


def apply_migrations(ref: str, db_pass: str, migrations: list[Migration]) -> None:
    migrations_dir = Path("supabase/migrations")

    # CRITICAL: clear stale migration files from previous attempts
    if migrations_dir.exists():
        shutil.rmtree(migrations_dir)
    migrations_dir.mkdir(parents=True, exist_ok=True)

    for m in migrations:
        (migrations_dir / m.filename).write_text(m.sql)

    env = os.environ.copy()
    env["SUPABASE_DB_PASSWORD"] = db_pass
    result = subprocess.run(
        ["supabase", "db", "push", "--include-all"],
        check=False, capture_output=True, text=True, env=env,
    )
    if result.returncode != 0:
        raise MigrationError(result.stderr)
```

### 8.4 Auth configuration

```python
# compiler/deployer/auth_config.py
def configure_auth(ref: str, spec: BackendSpec) -> None:
    method = spec.parameters.get("authentication.method", "email_password")
    payload = {"external_email_enabled": True}

    if method == "oauth_google":
        payload["external_google_enabled"] = True
    elif method == "magic_link":
        payload["mailer_autoconfirm"] = True
    elif method == "oauth_github":
        payload["external_github_enabled"] = True

    requests.patch(
        f"https://api.supabase.com/v1/projects/{ref}/config/auth",
        headers={"Authorization": f"Bearer {SUPABASE_ACCESS_TOKEN}"},
        json=payload,
    ).raise_for_status()
```

### 8.5 Realtime configuration

Handled inside migrations (see §7.2).

### 8.6 Storage buckets

Buckets are created via SQL migration. Fragment `bucket_avatars`:

```sql
INSERT INTO storage.buckets (id, name, public, file_size_limit)
VALUES ('avatars', 'avatars', true, 10485760)
ON CONFLICT (id) DO NOTHING;

DROP POLICY IF EXISTS avatars_select_public ON storage.objects;
CREATE POLICY avatars_select_public ON storage.objects
  FOR SELECT USING (bucket_id = 'avatars');

DROP POLICY IF EXISTS avatars_insert_owner ON storage.objects;
CREATE POLICY avatars_insert_owner ON storage.objects
  FOR INSERT WITH CHECK (
    bucket_id = 'avatars' AND auth.uid()::text = (storage.foldername(name))[1]
  );
```

### 8.7 Edge functions

```python
# compiler/deployer/edge_functions.py
import os
import shutil
import subprocess
from pathlib import Path

TEMPLATES = Path(__file__).parent.parent / "generator" / "edge_templates"


def scaffold_edge_functions(spec: BackendSpec) -> None:
    base = Path("supabase/functions")
    if base.exists():
        for d in base.iterdir():
            if d.is_dir() and d.name in _managed_function_names():
                shutil.rmtree(d)
    base.mkdir(parents=True, exist_ok=True)

    for fn_name in spec.edge_functions:
        template_src = TEMPLATES / f"{fn_name}.ts"
        if not template_src.exists():
            raise ValueError(f"no template for edge function {fn_name}")
        dest_dir = base / fn_name
        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy(template_src, dest_dir / "index.ts")


def deploy_edge_functions(ref: str, spec: BackendSpec) -> None:
    if not spec.edge_functions:
        return
    scaffold_edge_functions(spec)
    env = os.environ.copy()
    env["SUPABASE_DB_PASSWORD"] = os.environ.get("SUPABASE_DB_PASSWORD", "")
    for fn_name in spec.edge_functions:
        subprocess.run(
            ["supabase", "functions", "deploy", fn_name, "--project-ref", ref],
            check=True, capture_output=True, text=True, env=env,
        )


def _managed_function_names() -> set[str]:
    return {p.stem for p in TEMPLATES.glob("*.ts")}
```

`edge_templates/` ships with: `stripe_webhook.ts`, `verification_webhook.ts`, `notification_dispatch.ts`.

### 8.8 Full deployment orchestration

```python
def deploy_spec(spec: BackendSpec, ref: str, db_pass: str) -> DeployResult:
    migrations = compose(spec, ontology)
    apply_migrations(ref, db_pass, migrations)
    configure_auth(ref, spec)
    deploy_edge_functions(ref, spec)
    return DeployResult(success=True, ref=ref)
```

---

## 9. Error Taxonomy & Remediation

### 9.1 Error categories

| Category | Detection | Remediation | Reuse project? |
|---|---|---|---|
| `fk_ordering` | "foreign key constraint" | Reorder migrations | Yes |
| `sql_syntax` | "syntax error" | Isolate fragment, flag bug | Yes |
| `duplicate_object` | "already exists" | Add `IF NOT EXISTS` | Yes |
| `rls_conflict` | "policy already exists" | Drop-then-create | Yes |
| `permission_denied` | "permission denied" | Flag for human | Yes |
| `quota_exceeded` | "quota" / "limit" | Flag for human | No (escalate) |
| `transient` | timeout, 5xx | Retry with backoff | Yes |
| `extension_missing` | "extension does not exist" | Add `CREATE EXTENSION` | Yes |
| `unknown` | Doesn't match | Flag for human | Yes |

### 9.2 Remediation loop — project reuse

```python
# compiler/deployer/deployer.py
def deploy_with_remediation(spec: BackendSpec, max_attempts: int = 3) -> DeployResult:
    ref = None
    db_pass = generate_db_pass()

    for attempt in range(max_attempts):
        try:
            if ref is None:
                ref = create_project(
                    name=project_name(spec), region=REGION,
                    org_slug=ORG_SLUG, db_pass=db_pass,
                )
                wait_for_healthy(ref)
                link_project(ref, db_pass)

            return deploy_spec(spec, ref, db_pass)

        except MigrationError as e:
            category = classify_error(e)

            if category == "transient":
                time.sleep(2 ** attempt)
                continue

            remediation = remediation_options(category, spec, e)
            if not remediation:
                return DeployResult(success=False, error=e,
                                    category=category, ref=ref)

            answer = present_mcq(remediation)
            spec = apply_remediation(spec, category, answer)

    return DeployResult(success=False, error="max attempts exceeded", ref=ref)
```

### 9.3 Remediation MCQ examples

**`fk_ordering`:** reorder / combine / remove relationship.
**`quota_exceeded`:** upgrade / remove features / manual.
**`extension_missing`:** enable / skip.

### 9.4 Retry cap

Maximum 3 attempts per error category.

---

## 10. Testing Strategy

### 10.1 Test tiers

| Tier | What | Frequency |
|---|---|---|
| Unit | Rules, Laya client, validators, derivation, negation, merge | Every commit |
| Fragment | Each fragment renders valid SQL | Every commit |
| Composition | Pairwise fragment combinations | Every commit |
| Golden | Input → expected spec | Every commit |
| Idempotency | Same spec twice → identical output | Every commit |
| Migration cleanup | Stale files removed between attempts | Every commit |
| Negation precision | ≥90% precision on labelled negation set | Every commit |
| ECE | < 0.1 on shipped `answer_confidence`; assert improvement only if fit performed | Every commit after Phase 4 |
| End-to-end | Full pipeline against real Supabase | Nightly |
| Load | 100 concurrent specs | Weekly |

### 10.2 Golden test set

Maintain 30–50 hand-crafted inputs.

### 10.3 Golden input format

```yaml
- id: golden_001_airbnb_cameras
  input: "Build an Airbnb-like marketplace for renting photography equipment..."
  expected_spec:
    features: {authentication: true, bookings: true, ...}
    parameters:
      "bookings.mode": owner_approval
    entities: [profiles, listings, bookings, messages, payments, reviews, verification_documents]
    edge_functions: [stripe_webhook, verification_webhook]
  max_mcqs: 4
```

### 10.4 Coverage metrics

Capability detection, ambiguity detection, negation precision, merge correctness, derivation correctness, final-spec correctness, MCQ count, time-to-spec, deployment success, idempotency, ECE on `answer_confidence`.

---

## 11. Build Order

### Phase 1 — Foundation (weeks 1–3)
Ontology loader, spec models, all three derivations, merge implementation, validator (including `contains` predicate), golden test framework.

### Phase 2 — Composition engine (weeks 4–7)
Fragment templates, topo sort, conflict detection, migration emitter, pairwise tests.

### Phase 3 — Deployer (weeks 8–10)
Management API client, CLI wrapper, auth config, bucket config, edge function scaffolding, migration directory cleanup, error classifier, remediation loop with project reuse.

### Phase 4 — Interpreter + ECE measurement + negation tuning (weeks 11–15)
Exact maps, phrase rules, character-span negation with sentence-boundary clamping, Laya client pinned to `english`, **ECE measurement on `answer_confidence`** (fit temperature only if ECE ≥ 0.1), merge, coverage check.

### Phase 5 — MCQ engine (weeks 16–18)
Dependency graph, selector, ordering, `resolve_negation` type, API endpoints.

### Phase 6 — UI + polish (weeks 19–22)
MCQ frontend, blueprint review, spec diff, error UX.

### Phase 7 — Optional fine-tuning (weeks 23+)
Synthetic data, Laya fine-tune, re-calibrate ECE per checkpoint.

---

## 12. Tech Stack

| Component | Choice |
|---|---|
| Language | Python 3.11+ |
| API | FastAPI |
| Data models | Pydantic v2 |
| Ontology storage | YAML in repo, loaded to Postgres |
| State store | Postgres |
| Templates | Jinja2 |
| Laya | `laya` PyPI package (≥ 0.3.20) |
| Laya runtime | GPU if available, else CPU |
| Supabase client | `requests` + CLI subprocess (v2.x) |
| Testing | pytest + pytest-asyncio |
| Frontend | Next.js (or any) |

---

## 13. Environment Variables

```
SUPABASE_ACCESS_TOKEN=...
SUPABASE_ORG_SLUG=...
DATABASE_URL=postgres://...

# Laya — our own vars, mapped to the library's Router API in laya_client.py
LAYA_DEVICE=cpu                    # passed to Router(device=...)
LAYA_CHECKPOINT=english            # one of: english | multilingual
HF_TOKEN=...                       # read by the laya library when downloading weights

# Confidence thresholds — provisional defaults, re-tune after ECE measurement (§3.5)
CONFIDENCE_AUTO_ACCEPT=0.75
CONFIDENCE_MCQ_MIN=0.35
CONFIDENCE_WEAK_MIN=0.20

NEGATION_WINDOW_CHARS=40

EDGE_FUNCTION_TEMPLATES_PATH=compiler/generator/edge_templates

MAX_DEPLOY_ATTEMPTS=3
LOG_LEVEL=INFO
```

**Note:** `LAYA_DEVICE` and `LAYA_CHECKPOINT` are our own variables, mapped explicitly in `compiler/interpreter/laya_client.py`. The library reads `HF_TOKEN` itself.

---

## 14. API Endpoints

```
POST /v1/sessions
POST /v1/sessions/{id}/interpret
POST /v1/sessions/{id}/answer
GET  /v1/sessions/{id}/spec
POST /v1/sessions/{id}/approve
POST /v1/sessions/{id}/deploy
GET  /v1/sessions/{id}/deploy/status
POST /v1/sessions/{id}/remediate
GET  /v1/sessions/{id}/logs
```

Sessions expire after 7 days.

---

## 15. Definition of Done

1. User can paste 1–3 sentences → working Supabase project.
2. ≤10 MCQs for complex spec, ≤3 for simple.
3. Golden set ≥90% final-spec correctness.
4. Idempotency 100%.
5. Deployment success ≥80% first attempt, ≥95% with remediation.
6. No silent requirement omissions on golden set.
7. ≥5 error categories auto-remediated.
8. All fragment pairwise tests pass.
9. Negation precision ≥90%.
10. Entity derivation invariant holds on 100% of specs.
11. ECE < 0.1 on held-out set for the `english` checkpoint (or `needs_fit: false` recorded with ECE < 0.1).
12. Deployer delivers full output promise.
13. Edge functions derived and scaffolded.
14. Stale migration files cleared between attempts.
15. Negation false-positive regression suite passes.
16. Bucket and edge-function derivation invariants hold.
17. `list[choice]` and `list[string]` validated.
18. `merge()` surfaces `phrase`/`phrase_negated` conflicts.
19. `realtime` with empty channels does not create `notifications` table.
20. Realtime channel without backing feature rejected at spec time.
21. All validator tests pass; `_spec()` populates derived fields via `recompute_spec`.
22. Laya client pinned to `english`; no `laya-typed-decisions` usage anywhere in the codebase.
23. **`MockLayaClient` returns the library envelope shape: top-level `model` (constant `"laya-rl-agent"`), `answers`, `usage` (`input_tokens`/`output_tokens`), `routing` (`model`/`repo`/`reason`); per-answer `type`, `noul`|`choice`, `confidence`, `answer_confidence`, `action` (`act_probability`). Verified by `tests/unit/test_laya_client.py`.**
24. **`Router.predict_batch` is called as a list of `{state, questions, model}` dicts, with no `model=` kwarg.**
25. **`Router` is constructed without a `models=` override so the library's default checkpoint resolution applies.**

---

## 16. Open Decisions (Defaults)

| Item | Default |
|---|---|
| Region strategy | `smartGroup` / `americas` |
| DB password | 32-char random, encrypted at rest, passed via env |
| Project naming | `{user_slug}-{app_slug}-{short_hash}` |
| Cleanup on failure | Keep project, mark failed |
| Session TTL | 7 days |
| Spec versioning | Immutable after approval |
| Calibration checkpoint file | `compiler/ontology/versions/v1/calibration.json` |
| Negation window size | 40 chars, clamped at sentence boundaries |
| Edge function overwrite policy | Only manage files under known template names |
| Laya checkpoint | `english` (pinned, not auto-routed) |

---

## 17. Contacts & Escalation

- Laya → `github.com/NandhaKishorM/laya`
- Supabase → `supabase.com/docs/reference/api`
- Ontology → this document

**If something is not specified here, it is an engineering judgment call. Make the call, write a test, and update this document.**

---

## 18. Test Suite Implementation

### 18.1 Directory structure

```
tests/
├── conftest.py
├── fixtures/
│   ├── ontology.yaml
│   ├── specs/
│   ├── laya_responses/
│   └── golden_calibration/
├── unit/
│   ├── test_interpreter.py
│   ├── test_negation.py
│   ├── test_merge.py
│   ├── test_derive.py
│   ├── test_edge_derivation.py
│   ├── test_validator.py
│   ├── test_mcq.py
│   ├── test_composer.py
│   ├── test_laya_client.py
│   └── test_errors.py
├── golden/
│   ├── cases/
│   └── test_golden.py
├── integration/
│   ├── test_idempotency.py
│   ├── test_fragment_matrix.py
│   ├── test_remediation.py
│   ├── test_migration_cleanup.py
│   └── test_ece_measurement.py
├── e2e/
│   └── test_full_pipeline.py
└── load/
    └── locustfile.py
```

### 18.2 Shared fixtures (`tests/conftest.py`)

```python
"""Shared fixtures for all tests."""
import json
import os
import time
from pathlib import Path
from typing import Iterator

import pytest
import requests

from compiler.ontology.loader import Ontology, load_ontology
from compiler.spec.models import BackendSpec, Decision, BucketSpec
from compiler.spec.derive import recompute_spec
from compiler.interpreter.laya_client import LayaClient


FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def ontology() -> Ontology:
    return load_ontology(FIXTURES / "ontology.yaml")


@pytest.fixture
def minimal_spec(ontology) -> BackendSpec:
    spec = BackendSpec(
        version="1.0", ontology_version=1, created_at="2025-01-01T00:00:00Z",
        features={"authentication": True},
        parameters={"authentication.method": "email_password"},
        roles=["user"], rls_overrides={},
        entities=[], buckets=[], edge_functions=[],
        decisions=[
            Decision(capability_id="authentication.enabled",
                     value=True, confidence=0.95, source="user", evidence=None),
        ],
        defaulted=[], unsupported=[],
    )
    return recompute_spec(spec, ontology)


@pytest.fixture
def marketplace_spec(ontology) -> BackendSpec:
    spec = BackendSpec(
        version="1.0", ontology_version=1, created_at="2025-01-01T00:00:00Z",
        features={
            "authentication": True, "bookings": True, "messaging": True,
            "payments": True, "file_storage": True,
        },
        parameters={
            "authentication.method": "email_password",
            "bookings.mode": "owner_approval",
            "messaging.trigger_event": "after_request",
            "payments.provider": "stripe",
            "file_storage.bucket_purpose": "listings",
        },
        roles=["user", "owner", "renter"], rls_overrides={},
        entities=[], buckets=[], edge_functions=[],
        decisions=[], defaulted=[], unsupported=[],
    )
    return recompute_spec(spec, ontology)


def _first_choice(criteria) -> str:
    """
    v1.9 — criteria may be either a list of option labels or a dict
    {label: description}. Return the first label in either case.
    """
    if isinstance(criteria, dict):
        return next(iter(criteria))
    if isinstance(criteria, (list, tuple)):
        return criteria[0]
    raise TypeError(f"unsupported criteria type: {type(criteria)}")


def _make_laya_answer(qtype: str, value, act_probability: float = 0.5) -> dict:
    """
    v1.10 — mirrors the real laya envelope for a single answer.

    Real single-predict shape (agent.py:699-707, 660-675):
      {
        "type":              "noul" | "choice",
        "noul" | "choice":   <raw value>,
        "confidence":        <max(p, 1-p)>,
        "answer_confidence": <ECE-calibrated>,
        "action":            {"act_probability": <float>},
      }

    `act_probability` comes from a SEPARATE action head (`act[r, 0]`)
    trained independently of the option logits (agent.py:676). It is
    NOT `noul`/`confidence` and must not be conflated with them. The
    mock does not simulate the action head, so this defaults to a
    fixed, documented value; a contract test that depends on the act
    value must pin it explicitly.
    """
    if qtype == "noul":
        p = float(value)
        return {
            "type": "noul",
            "noul": p,
            "confidence": max(p, 1 - p),
            "answer_confidence": max(p, 1 - p),
            "action": {"act_probability": act_probability},
        }
    if qtype == "choice":
        return {
            "type": "choice",
            "choice": value,
            "confidence": 1.0,
            "answer_confidence": 1.0,
            "action": {"act_probability": act_probability},
        }
    raise ValueError(f"unknown qtype {qtype}")


class MockLayaClient(LayaClient):
    """
    v1.9 — returns the real library envelope, matching both top-level
    and per-answer shapes.

    Real top-level shape (router.py:435, 557; agent.py:817):
      {
        "model":   "laya-rl-agent",                  # constant
        "answers": { qid: {...}, ... },
        "usage":   {"input_tokens": ..., "output_tokens": ...},
        "routing": {"model": ..., "repo": ..., "reason": ...},
      }

    The mock is a contract test double: if the interpreter reads a
    field, the mock must supply it. If it doesn't, the wiring bug
    goes unnoticed. The mock does not simulate the action head
    (agent.py:676 — a separately trained head), so mock answers use
    the fixed default `act_probability` from `_make_laya_answer`,
    which is independent of `noul`/`confidence`.
    """

    CONSTANT_MODEL = "laya-rl-agent"

    def __init__(self, responses: dict[str, dict] | None = None,
                 checkpoint: str = "english",
                 repo: str = "convaiinnovations/laya"):
        # v1.10 — super().__init__() is deliberately NOT called: it builds a
        # real Router with preload=True (downloads ~800MB of weights) and
        # loads calibration.json. Every LayaClient method that touches that
        # state is overridden below, so the mock never needs it. The None
        # placeholders make a future LayaClient method that forgets to
        # override fail loudly at dev time (AttributeError) instead of
        # silently using a parent that was never constructed.
        self.router = None
        self.calibration = None
        self.responses = responses or {}
        self.checkpoint = checkpoint
        self.repo = repo
        self.calls: list[tuple[str, dict]] = []

    def predict(self, state: str, questions: dict) -> dict:
        self.calls.append((state, questions))
        key = self._key(state, questions)
        if key in self.responses:
            return self.responses[key]

        answers = {}
        for qid, q in questions.items():
            if q["type"] == "noul":
                answers[qid] = _make_laya_answer("noul", 0.5)
            elif q["type"] == "choice":
                answers[qid] = _make_laya_answer("choice", _first_choice(q["criteria"]))
        return self._envelope(answers)

    def predict_batch(self, states: list[str], questions: dict) -> list[dict]:
        return [self.predict(s, questions) for s in states]

    def calibrated_confidence(self, answer: dict) -> float:
        # Mock: pass-through; ECE test uses this
        return answer["answer_confidence"]

    def _envelope(self, answers: dict) -> dict:
        return {
            "model": self.CONSTANT_MODEL,
            "answers": answers,
            "usage": {"input_tokens": 0, "output_tokens": 0},
            "routing": {
                "model": self.checkpoint,
                "repo": self.repo,
                "reason": "pinned",
            },
        }

    @staticmethod
    def _key(state: str, questions: dict) -> str:
        import hashlib
        blob = json.dumps({"state": state, "questions": questions}, sort_keys=True)
        return hashlib.sha256(blob.encode()).hexdigest()[:16]


@pytest.fixture
def mock_laya() -> MockLayaClient:
    return MockLayaClient()


@pytest.fixture
def mock_laya_high_confidence() -> MockLayaClient:
    class HighConf(MockLayaClient):
        def predict(self, state, questions):
            answers = {}
            for qid, q in questions.items():
                if q["type"] == "noul":
                    answers[qid] = _make_laya_answer("noul", 0.95)
                elif q["type"] == "choice":
                    answers[qid] = _make_laya_answer("choice", _first_choice(q["criteria"]))
            return self._envelope(answers)
    return HighConf()


@pytest.fixture(scope="session")
def supabase_token() -> str:
    token = os.environ.get("SUPABASE_ACCESS_TOKEN_TEST")
    if not token:
        pytest.skip("SUPABASE_ACCESS_TOKEN_TEST not set")
    return token


@pytest.fixture
def temp_supabase_project(supabase_token) -> Iterator[dict]:
    name = f"compiler-test-{int(time.time())}"
    resp = requests.post(
        "https://api.supabase.com/v1/projects",
        headers={"Authorization": f"Bearer {supabase_token}"},
        json={
            "name": name,
            "organization_slug": os.environ["SUPABASE_ORG_SLUG_TEST"],
            "region_selection": {"type": "smartGroup", "code": "americas"},
            "db_pass": "test-password-1234567890",
        },
    )
    resp.raise_for_status()
    ref = resp.json()["ref"]

    start = time.time()
    while time.time() - start < 600:
        h = requests.get(
            f"https://api.supabase.com/v1/projects/{ref}/health",
            headers={"Authorization": f"Bearer {supabase_token}"},
        ).json()
        if all(s["status"] == "ACTIVE_HEALTHY" for s in h):
            break
        time.sleep(10)
    else:
        pytest.fail("Project did not become healthy")

    yield {"ref": ref, "token": supabase_token}

    requests.delete(
        f"https://api.supabase.com/v1/projects/{ref}",
        headers={"Authorization": f"Bearer {supabase_token}"},
    )


@pytest.fixture(scope="session")
def local_postgres() -> Iterator[str]:
    from testcontainers.postgres import PostgresContainer
    with PostgresContainer("postgres:15") as pg:
        yield pg.get_connection_url()


@pytest.fixture
def fresh_db(local_postgres) -> Iterator[str]:
    import psycopg
    with psycopg.connect(local_postgres, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
            cur.execute("CREATE SCHEMA IF NOT EXISTS auth;")
            cur.execute("CREATE TABLE auth.users (id uuid PRIMARY KEY);")
            cur.execute(
                "CREATE OR REPLACE FUNCTION auth.uid() RETURNS uuid "
                "LANGUAGE sql AS $$ SELECT NULL::uuid $$;"
            )
            cur.execute("CREATE SCHEMA IF NOT EXISTS storage;")
            cur.execute("""
                CREATE TABLE storage.buckets (
                    id text PRIMARY KEY, name text, public boolean,
                    file_size_limit bigint
                );
            """)
            cur.execute("""
                CREATE TABLE storage.objects (
                    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                    bucket_id text, name text
                );
            """)
            cur.execute("""
                CREATE OR REPLACE FUNCTION storage.foldername(text)
                RETURNS text[] LANGUAGE sql AS $$ SELECT string_to_array($1, '/') $$;
            """)
    yield local_postgres
```

### 18.3 Negation tests

```python
# tests/unit/test_negation.py
import pytest
from compiler.interpreter.negation import is_negated, phrase_match_with_negation


@pytest.mark.parametrize("text,start,end,expected", [
    ("please don't charge users with Stripe", 20, 27, True),
    ("no payments needed", 0, 2, True),
    ("we do not want reviews", 11, 18, True),
    ("avoid checkout", 6, 14, True),
    ("users can message each other", 10, 17, False),
    ("payments via Stripe", 0, 8, False),
    ("No matter what, users can message each other", 28, 35, False),
    ("Not only do users message, but they share files", 24, 31, False),
    ("There is no doubt users can message each other", 31, 38, False),
    ("Needless to say, users can message each other", 28, 35, False),
    ("Users should really, truly, absolutely not message each other", 50, 57, True),
])
def test_is_negated(text, start, end, expected):
    assert is_negated(text, start, end) == expected


def test_negation_does_not_bleed_across_sentence_boundary():
    text = "Users can message each other. No payments."
    import re
    m = re.search(r"message", text)
    assert not is_negated(text, m.start(), m.end())


def test_negation_across_sentence_with_same_sentence_negator():
    text = "Users cannot message each other. Payments work."
    import re
    m = re.search(r"message", text)
    assert is_negated(text, m.start(), m.end())


def test_multi_word_negators_are_not_dead_code():
    for text in ["no need for payments", "we do not need payments",
                 "we don't need payments", "no need payments"]:
        candidates = phrase_match_with_negation(text)
        assert any(c.capability_id == "payments.enabled" and c.value is False
                   for c in candidates), f"failed on: {text}"


def test_no_matter_exception_does_not_flip():
    text = "No matter what, users can message each other"
    candidates = phrase_match_with_negation(text)
    msg = [c for c in candidates if c.capability_id == "messaging.enabled"]
    assert all(c.value is True for c in msg)


def test_negation_source_tagged():
    text = "we don't need payments"
    candidates = phrase_match_with_negation(text)
    negated = [c for c in candidates if c.capability_id == "payments.enabled"]
    assert any(c.source == "phrase_negated" for c in negated)
```

### 18.4 Entity derivation tests

```python
# tests/unit/test_derive.py
from compiler.spec.derive import derive_entities, derive_buckets, recompute_spec
from compiler.spec.models import BackendSpec


def _spec(ontology, **kwargs):
    base = dict(
        version="1.0", ontology_version=1, created_at="2025-01-01T00:00:00Z",
        features={}, parameters={}, roles=[], rls_overrides={},
        entities=[], buckets=[], edge_functions=[],
        decisions=[], defaulted=[], unsupported=[],
    )
    base.update(kwargs)
    return recompute_spec(BackendSpec(**base), ontology)


def test_derive_entities_minimal(ontology):
    spec = _spec(ontology, features={"authentication": True})
    assert derive_entities(spec, ontology) == ["profiles"]


def test_derive_entities_marketplace(ontology):
    spec = _spec(ontology, features={
        "authentication": True, "bookings": True, "messaging": True,
        "payments": True, "file_storage": True,
    })
    entities = derive_entities(spec, ontology)
    for expected in ("listings", "bookings", "messages", "payments", "files"):
        assert expected in entities


def test_recompute_updates_entities(ontology):
    spec = _spec(ontology, features={"authentication": True, "bookings": True})
    assert "listings" in spec.entities


def test_entity_derivation_invariant_enforced(ontology):
    from compiler.spec.validator import validate
    spec = _spec(ontology, features={"authentication": True})
    spec = spec.model_copy(update={"entities": ["wizard_table"]})
    assert not validate(spec, ontology).ok


def test_realtime_with_table_channel_derives_notifications(ontology):
    spec = _spec(ontology,
        features={"authentication": True, "realtime": True},
        parameters={"realtime.channels": ["notifications"]},
    )
    assert "notifications" in derive_entities(spec, ontology)


def test_realtime_with_empty_channels_does_not_derive_notifications(ontology):
    spec = _spec(ontology,
        features={"authentication": True, "realtime": True},
        parameters={"realtime.channels": []},
    )
    assert "notifications" not in derive_entities(spec, ontology)


def test_derive_buckets_listings_purpose(ontology):
    spec = _spec(ontology,
        features={"authentication": True, "file_storage": True},
        parameters={"file_storage.bucket_purpose": "listings"},
    )
    assert any(b.name == "listings" for b in derive_buckets(spec))


def test_derive_buckets_mixed_includes_verification(ontology):
    spec = _spec(ontology,
        features={"authentication": True, "file_storage": True, "verification": True},
        parameters={"file_storage.bucket_purpose": "mixed",
                    "verification.method": "government_id"},
    )
    assert "verification" in {b.name for b in derive_buckets(spec)}


def test_bucket_derivation_invariant_enforced(ontology):
    from compiler.spec.validator import validate
    from compiler.spec.models import BucketSpec
    spec = _spec(ontology,
        features={"authentication": True, "file_storage": True},
        parameters={"file_storage.bucket_purpose": "avatars"},
    )
    spec = spec.model_copy(update={
        "buckets": [BucketSpec(name="ghost", public=True, rls_pattern="owner_only")]
    })
    assert not validate(spec, ontology).ok
```

### 18.5 Edge function derivation tests

```python
# tests/unit/test_edge_derivation.py
from compiler.spec.derive import derive_edge_functions, recompute_spec
from compiler.spec.models import BackendSpec


def _spec(ontology, **kwargs):
    base = dict(
        version="1.0", ontology_version=1, created_at="2025-01-01T00:00:00Z",
        features={}, parameters={}, roles=[], rls_overrides={},
        entities=[], buckets=[], edge_functions=[],
        decisions=[], defaulted=[], unsupported=[],
    )
    base.update(kwargs)
    return recompute_spec(BackendSpec(**base), ontology)


def test_no_edge_functions_for_minimal_app(ontology):
    spec = _spec(ontology, features={"authentication": True})
    assert derive_edge_functions(spec, ontology) == []


def test_stripe_derives_webhook(ontology):
    spec = _spec(ontology,
        features={"authentication": True, "payments": True},
        parameters={"payments.provider": "stripe"},
    )
    assert "stripe_webhook" in derive_edge_functions(spec, ontology)


def test_verification_derives_webhook(ontology):
    spec = _spec(ontology,
        features={"authentication": True, "file_storage": True, "verification": True},
        parameters={"file_storage.bucket_purpose": "documents",
                    "verification.method": "government_id"},
    )
    assert "verification_webhook" in derive_edge_functions(spec, ontology)


def test_realtime_with_table_channel_derives_notification_dispatch(ontology):
    spec = _spec(ontology,
        features={"authentication": True, "realtime": True},
        parameters={"realtime.channels": ["notifications"]},
    )
    assert "notification_dispatch" in derive_edge_functions(spec, ontology)


def test_realtime_with_empty_channels_drops_notification_dispatch(ontology):
    spec = _spec(ontology,
        features={"authentication": True, "realtime": True},
        parameters={"realtime.channels": []},
    )
    assert "notification_dispatch" not in derive_edge_functions(spec, ontology)


def test_recompute_sets_edge_functions(ontology):
    spec = _spec(ontology,
        features={"authentication": True, "payments": True},
        parameters={"payments.provider": "stripe"},
    )
    assert "stripe_webhook" in spec.edge_functions


def test_edge_function_derivation_invariant_enforced(ontology):
    from compiler.spec.validator import validate
    spec = _spec(ontology, features={"authentication": True})
    spec = spec.model_copy(update={"edge_functions": ["ghost_webhook"]})
    assert not validate(spec, ontology).ok
```

### 18.6 Merge tests

```python
# tests/unit/test_merge.py
from compiler.interpreter.merge import merge
from compiler.spec.models import Candidate


def test_merge_positive_and_negative_phrase_flags_ambiguity():
    b = [
        Candidate("payments.enabled", True,  0.85, "phrase",         "s1"),
        Candidate("payments.enabled", False, 0.85, "phrase_negated", "s2"),
    ]
    merged = merge([], b, [])
    assert len(merged) == 2
    assert {c.value for c in merged} == {True, False}


def test_merge_only_positive_phrase():
    b = [Candidate("payments.enabled", True, 0.85, "phrase", "s1")]
    merged = merge([], b, [])
    assert len(merged) == 1
    assert merged[0].value is True


def test_merge_only_negative_phrase():
    b = [Candidate("payments.enabled", False, 0.85, "phrase_negated", "s1")]
    merged = merge([], b, [])
    assert len(merged) == 1
    assert merged[0].value is False


def test_merge_exact_beats_phrase_and_negated_phrase():
    a = [Candidate("payments.enabled", True, 1.0, "exact", None)]
    b = [
        Candidate("payments.enabled", False, 0.9, "phrase_negated", "s1"),
        Candidate("payments.enabled", True,  0.9, "phrase",         "s2"),
    ]
    c = [Candidate("payments.enabled", True, 0.7, "laya", None)]
    merged = merge(a, b, c)
    assert len(merged) == 1
    assert merged[0].source == "exact"


def test_merge_laya_only_when_no_phrase():
    c = [Candidate("reviews.enabled", True, 0.7, "laya", None)]
    merged = merge([], [], c)
    assert len(merged) == 1
    assert merged[0].source == "laya"


def test_merge_disjoint_capabilities():
    a = [Candidate("payments.provider", "stripe", 1.0, "exact", None)]
    b = [Candidate("messaging.enabled", True, 0.9, "phrase", "s1")]
    c = [Candidate("reviews.enabled", True, 0.7, "laya", None)]
    merged = merge(a, b, c)
    assert len(merged) == 3


def test_merge_two_exact_same_value_picks_highest_confidence():
    a = [
        Candidate("payments.provider", "stripe", 1.0, "exact", "s1"),
        Candidate("payments.provider", "stripe", 0.9, "exact", "s2"),
    ]
    merged = merge(a, [], [])
    assert len(merged) == 1
    assert merged[0].confidence == 1.0


def test_merge_two_exact_different_values_flags_ambiguity():
    a = [
        Candidate("authentication.method", "oauth_google", 1.0, "exact", "s1"),
        Candidate("authentication.method", "magic_link",   1.0, "exact", "s2"),
    ]
    merged = merge(a, [], [])
    assert len(merged) == 2
```

### 18.7 Unit tests — interpreter

```python
# tests/unit/test_interpreter.py
import pytest
from compiler.interpreter.aliases import exact_match
from compiler.interpreter.rules import phrase_match
from compiler.interpreter.merge import check_coverage
from compiler.spec.models import Candidate


def test_exact_map_stripe():
    candidates = exact_match("I want to use Stripe for payments")
    assert any(c.capability_id == "payments.provider" and c.value == "stripe"
               for c in candidates)


def test_exact_map_case_insensitive():
    assert exact_match("STRIPE") == exact_match("stripe")


def test_exact_map_no_match():
    assert exact_match("something unrelated") == []


@pytest.mark.parametrize("text,expected", [
    ("users can message each other", "messaging.enabled"),
    ("owners can talk to renters", "messaging.enabled"),
    ("people should be able to contact users", "messaging.enabled"),
])
def test_phrase_messaging(text, expected):
    candidates = phrase_match(text)
    assert any(c.capability_id == expected for c in candidates)


def test_coverage_unparsed_sentence_flagged():
    text = "Users can message each other. Owners can reject bad actors."
    mapped = [Candidate("messaging.enabled", True, 0.9, "phrase", "s1")]
    unparsed = check_coverage(text, mapped)
    assert len(unparsed) == 1
    assert "reject bad actors" in unparsed[0]
```

### 18.8 Unit tests — Laya client contract

```python
# tests/unit/test_laya_client.py
"""
Contract test between MockLayaClient and the interpreter's consumption
of answer fields.

Verifies:
  - Mock returns the same top-level shape as the real library envelope
    (model / answers / usage / routing).
  - Each answer carries type, noul/choice, confidence, answer_confidence,
    action.
  - The interpreter reads answer_confidence (not bare noul) when
    computing candidate confidence.
  - Router.predict_batch is invoked as list-of-dicts, not list-of-strings
    with a model= kwarg.
  - Router is constructed without a models= override.
"""
import pytest
from compiler.interpreter.laya_client import LayaClient, CHECKPOINT
from tests.conftest import MockLayaClient, _make_laya_answer, _first_choice


def test_mock_returns_full_envelope():
    mock = MockLayaClient()
    resp = mock.predict("some state", {
        "q1": {"type": "noul", "instructions": "..."},
        "q2": {"type": "choice", "instructions": "...", "criteria": ["a", "b"]},
    })
    assert "model" in resp
    assert "answers" in resp
    assert "usage" in resp
    assert "routing" in resp
    assert resp["answers"]["q1"]["type"] == "noul"
    assert "noul" in resp["answers"]["q1"]
    assert "confidence" in resp["answers"]["q1"]
    assert "answer_confidence" in resp["answers"]["q1"]
    assert "action" in resp["answers"]["q1"]
    assert resp["answers"]["q2"]["type"] == "choice"
    assert "choice" in resp["answers"]["q2"]


def test_top_level_model_is_constant():
    """v1.9 — real library returns the constant 'laya-rl-agent' at top level."""
    mock = MockLayaClient()
    resp = mock.predict("s", {"q": {"type": "noul", "instructions": "..."}})
    assert resp["model"] == "laya-rl-agent"


def test_routing_has_real_keys():
    """v1.9 — real routing has model/repo/reason, not checkpoint/auto_routed."""
    mock = MockLayaClient()
    resp = mock.predict("s", {"q": {"type": "noul", "instructions": "..."}})
    assert set(resp["routing"].keys()) >= {"model", "repo", "reason"}


def test_usage_has_real_keys():
    """v1.9 — real usage has input_tokens/output_tokens."""
    mock = MockLayaClient()
    resp = mock.predict("s", {"q": {"type": "noul", "instructions": "..."}})
    assert set(resp["usage"].keys()) >= {"input_tokens", "output_tokens"}


def test_action_has_act_probability():
    """v1.9 — real action carries act_probability."""
    mock = MockLayaClient()
    resp = mock.predict("s", {"q": {"type": "noul", "instructions": "..."}})
    assert "act_probability" in resp["answers"]["q"]["action"]


def test_act_probability_is_independent_of_noul():
    """v1.10 — the action head is a separate trained quantity (agent.py:676);
    a caller-pinned act_probability must be preserved verbatim, not recomputed
    from noul/confidence."""
    a = _make_laya_answer("noul", 0.9, act_probability=0.4)
    assert a["noul"] == 0.9
    assert a["confidence"] == 0.9
    assert a["action"]["act_probability"] == 0.4
    assert a["action"]["act_probability"] != a["noul"]


def test_mock_constructs_without_network():
    """v1.10 — MockLayaClient must never build the real Router (which preloads
    and downloads weights). router/calibration are explicit None placeholders."""
    mock = MockLayaClient()
    assert mock.router is None
    assert mock.calibration is None
    assert mock.predict("s", {"q": {"type": "noul", "instructions": "..."}})[
        "model"] == "laya-rl-agent"


def test_criteria_dict_supported():
    """v1.9 — criteria may be a dict {label: description}; _first_choice handles it."""
    assert _first_choice({"a": "A", "b": "B"}) == "a"
    assert _first_choice(["a", "b"]) == "a"


def test_default_checkpoint_is_english():
    assert CHECKPOINT == "english"


def test_client_never_uses_typed_decisions():
    import compiler.interpreter.laya_client as lc
    src = open(lc.__file__).read()
    assert "laya-typed-decisions" not in src


def test_client_does_not_override_models():
    """
    v1.9 — Router must be constructed without a models= override so
    the library's default checkpoint resolution applies. Passing
    models={"english": None} overwrites the default with None and
    breaks preload.
    """
    import compiler.interpreter.laya_client as lc
    src = open(lc.__file__).read()
    assert "models=" not in src, \
        "LayaClient must not pass models= to Router(); library defaults apply"


def test_interpreter_consumes_answer_confidence():
    """
    The interpreter must use answer_confidence as the calibrated
    confidence. Given noul=0.9 and answer_confidence=0.6, the candidate
    confidence surfaced should be 0.6.
    """
    from compiler.interpreter.pipeline import candidates_from_laya_response

    mock_resp = {
        "model": "laya-rl-agent",
        "answers": {
            "needs_listings": {
                "type": "noul",
                "noul": 0.9,
                "confidence": 0.9,
                "answer_confidence": 0.6,
                "action": {"act_probability": 0.9},
            }
        },
        "usage": {"input_tokens": 0, "output_tokens": 0},
        "routing": {"model": "english", "repo": "convaiinnovations/laya", "reason": "pinned"},
    }
    candidates = candidates_from_laya_response(mock_resp)
    c = next(c for c in candidates if c.capability_id == "needs_listings")
    assert c.confidence == pytest.approx(0.6), \
        "interpreter must read answer_confidence, not noul"
```

### 18.9 Unit tests — validator

```python
# tests/unit/test_validator.py
"""
_spec() calls recompute_spec so derived fields (entities, buckets,
edge_functions) are consistent with features/parameters.
"""
from compiler.spec.validator import validate
from compiler.spec.derive import recompute_spec
from compiler.spec.models import BackendSpec


def _spec(ontology, **kwargs):
    base = dict(
        version="1.0", ontology_version=1, created_at="2025-01-01T00:00:00Z",
        features={}, parameters={}, roles=[], rls_overrides={},
        entities=[], buckets=[], edge_functions=[],
        decisions=[], defaulted=[], unsupported=[],
    )
    base.update(kwargs)
    return recompute_spec(BackendSpec(**base), ontology)


def test_valid_minimal_spec(minimal_spec, ontology):
    result = validate(minimal_spec, ontology)
    assert result.ok
    assert result.errors == []


def test_valid_marketplace_spec(marketplace_spec, ontology):
    assert validate(marketplace_spec, ontology).ok


def test_missing_dependency_rejected(ontology):
    spec = _spec(ontology,
        features={"payments": True, "authentication": False},
        parameters={"payments.provider": "stripe"},
    )
    assert not validate(spec, ontology).ok


def test_hard_constraint_instant_booking_with_verification(ontology):
    spec = _spec(ontology,
        features={"authentication": True, "bookings": True,
                  "verification": True, "file_storage": True},
        parameters={"bookings.mode": "instant",
                    "verification.method": "government_id_and_admin",
                    "file_storage.bucket_purpose": "mixed"},
    )
    assert not validate(spec, ontology).ok


def test_soft_constraint_anytime_messaging_warns(ontology):
    spec = _spec(ontology,
        features={"authentication": True, "messaging": True},
        parameters={"messaging.trigger_event": "anytime"},
    )
    result = validate(spec, ontology)
    assert result.ok, f"unexpected errors: {result.errors}"
    assert len(result.warnings) >= 1


def test_list_choice_invalid_member_rejected(ontology):
    spec = _spec(ontology,
        features={"authentication": True, "realtime": True},
        parameters={"realtime.channels": ["notifications", "ghost_channel"]},
    )
    assert not validate(spec, ontology).ok


def test_list_choice_valid_members_accepted(ontology):
    spec = _spec(ontology,
        features={"authentication": True, "realtime": True},
        parameters={"realtime.channels": ["notifications"]},
    )
    assert validate(spec, ontology).ok


def test_list_string_below_min_rejected(ontology):
    spec = _spec(ontology,
        features={"authentication": True, "roles": True},
        parameters={"roles.role_names": []},
    )
    assert not validate(spec, ontology).ok


def test_list_string_above_max_rejected(ontology):
    spec = _spec(ontology,
        features={"authentication": True, "roles": True},
        parameters={"roles.role_names": ["a", "b", "c", "d", "e", "f"]},
    )
    assert not validate(spec, ontology).ok


def test_list_string_empty_member_rejected(ontology):
    spec = _spec(ontology,
        features={"authentication": True, "roles": True},
        parameters={"roles.role_names": ["admin", "  "]},
    )
    assert not validate(spec, ontology).ok


def test_realtime_messages_channel_without_messaging_feature_rejected(ontology):
    spec = _spec(ontology,
        features={"authentication": True, "realtime": True, "messaging": False},
        parameters={"realtime.channels": ["messages"]},
    )
    result = validate(spec, ontology)
    assert not result.ok
    assert any("messaging" in str(e).lower() for e in result.errors)


def test_realtime_bookings_channel_without_bookings_feature_rejected(ontology):
    spec = _spec(ontology,
        features={"authentication": True, "realtime": True, "bookings": False},
        parameters={"realtime.channels": ["bookings"]},
    )
    result = validate(spec, ontology)
    assert not result.ok
    assert any("booking" in str(e).lower() for e in result.errors)


def test_realtime_messages_channel_with_messaging_feature_accepted(ontology):
    spec = _spec(ontology,
        features={"authentication": True, "realtime": True, "messaging": True},
        parameters={"realtime.channels": ["messages"],
                    "messaging.trigger_event": "after_request"},
    )
    assert validate(spec, ontology).ok


def test_realtime_notifications_channel_needs_no_backing_feature(ontology):
    spec = _spec(ontology,
        features={"authentication": True, "realtime": True},
        parameters={"realtime.channels": ["notifications"]},
    )
    assert validate(spec, ontology).ok
```

### 18.10 Unit tests — MCQ engine

```python
# tests/unit/test_mcq.py
from compiler.mcq.selector import next_questions, Question
from compiler.mcq.graph import order_questions
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


def _q(type_, feature_id):
    return Question(type=type_, feature_id=feature_id, parameter_id=None,
                    options=[], confidence=0.5)
```

### 18.11 Unit tests — composer

```python
# tests/unit/test_composer.py
from compiler.generator.composer import compose
from compiler.generator.ordering import topo_sort


def test_compose_minimal_spec(minimal_spec, ontology):
    migrations = compose(minimal_spec, ontology)
    assert len(migrations) > 0
    assert all(m.filename.endswith(".sql") for m in migrations)


def test_compose_marketplace_spec(marketplace_spec, ontology):
    combined = "\n".join(m.sql for m in compose(marketplace_spec, ontology))
    assert "CREATE TABLE IF NOT EXISTS listings" in combined
    assert "CREATE TABLE IF NOT EXISTS bookings" in combined
    assert "CREATE TABLE IF NOT EXISTS messages" in combined
    assert "INSERT INTO storage.buckets" in combined


def test_realtime_empty_channels_no_notifications_table(ontology):
    from compiler.spec.models import BackendSpec
    from compiler.spec.derive import recompute_spec
    spec = recompute_spec(BackendSpec(
        version="1.0", ontology_version=1, created_at="2025-01-01T00:00:00Z",
        features={"authentication": True, "realtime": True},
        parameters={"realtime.channels": []},
        roles=["user"], rls_overrides={},
        entities=[], buckets=[], edge_functions=[],
        decisions=[], defaulted=[], unsupported=[],
    ), ontology)
    combined = "\n".join(m.sql for m in compose(spec, ontology))
    assert "notifications" not in combined


def test_realtime_fragment_present_when_enabled(ontology):
    from compiler.spec.models import BackendSpec
    from compiler.spec.derive import recompute_spec
    spec = recompute_spec(BackendSpec(
        version="1.0", ontology_version=1, created_at="2025-01-01T00:00:00Z",
        features={"authentication": True, "messaging": True, "realtime": True},
        parameters={"realtime.channels": ["messages"],
                    "messaging.trigger_event": "after_request"},
        roles=["user"], rls_overrides={},
        entities=[], buckets=[], edge_functions=[],
        decisions=[], defaulted=[], unsupported=[],
    ), ontology)
    combined = "\n".join(m.sql for m in compose(spec, ontology))
    assert "supabase_realtime" in combined


def test_all_migrations_have_if_not_exists(marketplace_spec, ontology):
    for m in compose(marketplace_spec, ontology):
        for line in m.sql.splitlines():
            if "CREATE TABLE" in line:
                assert "IF NOT EXISTS" in line
            if "CREATE INDEX" in line:
                assert "IF NOT EXISTS" in line


def test_topological_sort_respects_requires(ontology):
    from compiler.generator.composer import load
    a = load("function_is_admin")
    b = load("rls_listings_owner")
    ordered = topo_sort([b, a], key="requires")
    assert ordered.index(a) < ordered.index(b)
```

### 18.12 Unit tests — error classifier

```python
# tests/unit/test_errors.py
import pytest
from compiler.deployer.errors import classify_error, MigrationError


@pytest.mark.parametrize("message,expected", [
    ('ERROR: insert or update on table "bookings" violates foreign key constraint',
     "fk_ordering"),
    ('ERROR: syntax error at or near "CREAT"', "sql_syntax"),
    ('ERROR: relation "listings" already exists', "duplicate_object"),
    ('ERROR: policy "select_owner" for table "listings" already exists', "rls_conflict"),
    ('ERROR: permission denied to create extension "pgcrypto"', "permission_denied"),
    ('ERROR: exceeded max number of tables for plan', "quota_exceeded"),
    ('ERROR: extension "pg_graphql" does not exist', "extension_missing"),
    ('HTTP 503 Service Unavailable', "transient"),
    ('Connection timed out', "transient"),
    ('something nobody has seen before', "unknown"),
])
def test_classify_error(message, expected):
    assert classify_error(MigrationError(message)) == expected
```

### 18.13 Golden test runner

```python
# tests/golden/test_golden.py
import json
from pathlib import Path

import pytest
import yaml

from compiler.interpreter.pipeline import run_interpreter
from compiler.mcq.pipeline import run_mcq_loop
from compiler.spec.validator import validate
from compiler.spec.derive import recompute_spec
from tests.conftest import MockLayaClient


CASES = sorted((Path(__file__).parent / "cases").glob("*.yaml"))


def pytest_generate_tests(metafunc):
    if "case" in metafunc.fixturenames:
        metafunc.parametrize("case", CASES, ids=[c.stem for c in CASES])


def test_golden(case, ontology):
    data = yaml.safe_load(case.read_text())
    mock = MockLayaClient(responses=data.get("laya_responses", {}))

    candidates = run_interpreter(data["input"], ontology, laya=mock)
    spec, mcqs = run_mcq_loop(
        candidates, ontology,
        user_answers=data.get("user_answers", {}),
        laya=mock,
    )
    spec = recompute_spec(spec, ontology)

    assert spec_matches(spec, data["expected_spec"])
    assert len(mcqs) <= data.get("max_mcqs", 10)

    result = validate(spec, ontology)
    assert result.ok, f"Spec failed validation: {result.errors}"


def spec_matches(actual, expected: dict) -> bool:
    actual_dict = actual.model_dump()
    for key, expected_val in expected.items():
        if isinstance(expected_val, dict):
            actual_val = actual_dict.get(key, {})
            for k, v in expected_val.items():
                if actual_val.get(k) != v:
                    return False
        elif isinstance(expected_val, list):
            if sorted(actual_dict.get(key, [])) != sorted(expected_val):
                return False
        else:
            if actual_dict.get(key) != expected_val:
                return False
    return True
```

### 18.14 Idempotency harness

```python
# tests/integration/test_idempotency.py
import hashlib

import pytest
import psycopg

from compiler.generator.composer import compose


def _hash_migrations(migrations):
    blob = "\n--SPLIT--\n".join(m.sql for m in migrations)
    return hashlib.sha256(blob.encode()).hexdigest()


@pytest.mark.parametrize("spec_fixture", ["minimal_spec", "marketplace_spec"])
def test_compile_twice_identical(spec_fixture, request, ontology):
    spec = request.getfixturevalue(spec_fixture)
    first = _hash_migrations(compose(spec, ontology))
    second = _hash_migrations(compose(spec, ontology))
    assert first == second


def test_migrations_apply_twice_cleanly(marketplace_spec, ontology, fresh_db):
    migrations = compose(marketplace_spec, ontology)
    with psycopg.connect(fresh_db, autocommit=True) as conn:
        for m in migrations:
            conn.execute(m.sql)
    with psycopg.connect(fresh_db, autocommit=True) as conn:
        for m in migrations:
            conn.execute(m.sql)


def test_policy_drop_create_present(marketplace_spec, ontology):
    import re
    combined = "\n".join(m.sql for m in compose(marketplace_spec, ontology))
    creates = re.findall(r"CREATE POLICY (\w+)", combined)
    drops = re.findall(r"DROP POLICY IF EXISTS (\w+)", combined)
    assert set(creates).issubset(set(drops))
```

### 18.15 Migration cleanup test

```python
# tests/integration/test_migration_cleanup.py
from compiler.deployer.deployer import apply_migrations
from compiler.generator.composer import compose
from compiler.spec.derive import recompute_spec


def test_apply_migrations_clears_stale_files(tmp_path, monkeypatch,
                                              marketplace_spec, ontology):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "compiler.deployer.deployer.subprocess.run",
        lambda *a, **k: type("R", (), {"returncode": 0, "stderr": ""})(),
    )

    migrations_1 = compose(marketplace_spec, ontology)
    assert len(migrations_1) >= 5
    try:
        apply_migrations("ref", "pass", migrations_1)
    except Exception:
        pass

    written_1 = sorted(p.name for p in (tmp_path / "supabase/migrations").iterdir())
    assert len(written_1) == len(migrations_1)

    small_spec = marketplace_spec.model_copy(update={
        "features": {**marketplace_spec.features, "messaging": False},
    })
    small_spec = recompute_spec(small_spec, ontology)
    migrations_2 = compose(small_spec, ontology)
    assert len(migrations_2) < len(migrations_1)

    try:
        apply_migrations("ref", "pass", migrations_2)
    except Exception:
        pass

    written_2 = sorted(p.name for p in (tmp_path / "supabase/migrations").iterdir())
    expected = {m.filename for m in migrations_2}
    assert set(written_2) == expected, \
        f"stale files remain: {set(written_2) - expected}"
```

### 18.16 Error-injection harness with project reuse

```python
# tests/integration/test_remediation.py
import pytest
from compiler.deployer import deployer
from compiler.deployer.errors import MigrationError


@pytest.mark.parametrize("error_message,expected_category,should_retry", [
    ('relation "listings" already exists', "duplicate_object", True),
    ('policy "x" already exists', "rls_conflict", True),
    ('foreign key constraint "bookings_listing_id_fkey"', "fk_ordering", True),
    ('extension "pgcrypto" does not exist', "extension_missing", True),
    ('HTTP 503', "transient", True),
    ('permission denied to create extension', "permission_denied", False),
    ('exceeded max number of tables for plan', "quota_exceeded", False),
    ('syntax error at or near "XYZ"', "sql_syntax", False),
])
def test_remediation_category(monkeypatch, marketplace_spec,
                              error_message, expected_category, should_retry):
    attempts = {"apply": 0, "create": 0}

    def fake_create(*a, **k):
        attempts["create"] += 1
        return "fake-ref"

    def fake_apply(ref, db_pass, migrations):
        attempts["apply"] += 1
        raise MigrationError(error_message)

    monkeypatch.setattr(deployer, "create_project", fake_create)
    monkeypatch.setattr(deployer, "wait_for_healthy", lambda *a, **k: None)
    monkeypatch.setattr(deployer, "link_project", lambda *a, **k: None)
    monkeypatch.setattr(deployer, "apply_migrations", fake_apply)
    monkeypatch.setattr(deployer, "present_mcq", lambda opts: opts[0]["value"])

    result = deployer.deploy_with_remediation(marketplace_spec)

    assert attempts["create"] == 1
    if should_retry:
        assert attempts["apply"] >= 2
    assert result.category == expected_category


def test_max_attempts_cap_reuses_project(monkeypatch, marketplace_spec):
    attempts = {"apply": 0, "create": 0}

    def fake_create(*a, **k):
        attempts["create"] += 1
        return "ref"

    def fake_apply(ref, db_pass, migrations):
        attempts["apply"] += 1
        raise MigrationError('relation "listings" already exists')

    monkeypatch.setattr(deployer, "create_project", fake_create)
    monkeypatch.setattr(deployer, "wait_for_healthy", lambda *a, **k: None)
    monkeypatch.setattr(deployer, "link_project", lambda *a, **k: None)
    monkeypatch.setattr(deployer, "apply_migrations", fake_apply)
    monkeypatch.setattr(deployer, "present_mcq", lambda opts: opts[0]["value"])

    result = deployer.deploy_with_remediation(marketplace_spec, max_attempts=3)
    assert attempts["apply"] == 3
    assert attempts["create"] == 1
    assert not result.success
```

### 18.17 ECE measurement test

```python
# tests/integration/test_ece_measurement.py
"""
Laya already returns ECE-calibrated answer_confidence. We do NOT fit
an extra temperature by default. This test measures ECE on shipped
answer_confidence and only asserts improvement IF an extra temperature
was fit (i.e., ECE >= 0.1 and needs_fit is true).
"""
import json
from pathlib import Path

import numpy as np

from compiler.interpreter.calibration import apply_temperature, fit_temperature


FIXTURES = Path(__file__).parent.parent / "fixtures" / "golden_calibration"


def test_ece_on_shipped_answer_confidence_is_acceptable():
    data = json.loads((FIXTURES / "calibration_set.json").read_text())
    answer_confidences = np.array([d["answer_confidence"] for d in data])
    labels = np.array([d["label"] for d in data])

    ece = expected_calibration_error(answer_confidences, labels, n_bins=10)
    assert ece < 0.1, (
        f"ECE on shipped answer_confidence is {ece:.3f}, "
        f"which exceeds the 0.1 threshold. See §3.5 for the fitting procedure."
    )


def test_fit_temperature_only_improves_if_needed():
    data = json.loads((FIXTURES / "calibration_set.json").read_text())
    answer_confidences = np.array([d["answer_confidence"] for d in data])
    labels = np.array([d["label"] for d in data])

    ece_shipped = expected_calibration_error(answer_confidences, labels, n_bins=10)
    if ece_shipped < 0.1:
        return

    clipped = np.clip(answer_confidences, 1e-6, 1 - 1e-6)
    T = fit_temperature(clipped, labels)
    calibrated = apply_temperature(clipped, T)
    ece_after = expected_calibration_error(calibrated, labels, n_bins=10)

    assert ece_after < ece_shipped


def expected_calibration_error(probs, labels, n_bins=10):
    bins = np.linspace(0, 1, n_bins + 1)
    ece = 0.0
    for i in range(n_bins):
        lo, hi = bins[i], bins[i + 1]
        mask = (probs >= lo) & (probs < hi)
        if mask.sum() == 0:
            continue
        ece += (mask.sum() / len(probs)) * abs(probs[mask].mean() - labels[mask].mean())
    return ece
```

### 18.18 Fragment pairwise matrix

```python
# tests/integration/test_fragment_matrix.py
import itertools

import pytest
import psycopg

from compiler.generator.fragments import list_all_fragments
from compiler.generator.composer import compose


ALL_FRAGMENTS = list_all_fragments()


@pytest.mark.parametrize("pair", list(itertools.combinations(ALL_FRAGMENTS, 2)))
def test_pair_applies(pair, ontology, fresh_db):
    frag_a, frag_b = pair
    spec = _spec_for_fragments([frag_a, frag_b])
    for m in compose(spec, ontology):
        with psycopg.connect(fresh_db, autocommit=True) as conn:
            conn.execute(m.sql)


def _spec_for_fragments(fragment_ids):
    from compiler.generator.fragment_spec_map import spec_for
    return spec_for(fragment_ids)
```

### 18.19 End-to-end test

```python
# tests/e2e/test_full_pipeline.py
import pytest
import requests

from compiler.interpreter.pipeline import run_interpreter
from compiler.mcq.pipeline import run_mcq_loop
from compiler.spec.validator import validate
from compiler.generator.composer import compose
from compiler.deployer.deployer import deploy_spec


@pytest.mark.slow
def test_full_pipeline_creates_working_project(
    ontology, mock_laya_high_confidence, temp_supabase_project
):
    user_input = (
        "Build an Airbnb-like marketplace for renting photography equipment. "
        "Owners list equipment, renters book them, owners need verification, "
        "users can message each other, payments use Stripe."
    )

    candidates = run_interpreter(user_input, ontology, laya=mock_laya_high_confidence)
    spec, mcqs = run_mcq_loop(candidates, ontology, user_answers={},
                              laya=mock_laya_high_confidence)

    assert validate(spec, ontology).ok
    assert len(compose(spec, ontology)) > 0

    ref = temp_supabase_project["ref"]
    result = deploy_spec(spec, ref, "test-password-1234567890")
    assert result.success

    tables = requests.get(
        f"https://api.supabase.com/v1/projects/{ref}/database/query",
        headers={"Authorization": f"Bearer {temp_supabase_project['token']}"},
        json={"query": "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"},
    ).json()
    names = {t["tablename"] for t in tables}
    assert {"listings", "bookings", "messages"} <= names

    buckets = requests.get(
        f"https://api.supabase.com/v1/projects/{ref}/database/query",
        headers={"Authorization": f"Bearer {temp_supabase_project['token']}"},
        json={"query": "SELECT id FROM storage.buckets"},
    ).json()
    assert "listings" in {b["id"] for b in buckets}
```

### 18.20 CI configuration

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_PASSWORD: postgres
        ports: ["5432:5432"]
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip
      - run: pip install -e ".[dev]"
      - run: ruff check compiler tests
      - run: mypy compiler
      - name: Unit + golden + idempotency + fragment matrix
        run: |
          pytest tests/unit tests/golden tests/integration \
            --cov=compiler --cov-report=xml --cov-fail-under=80 \
            -x -q
        env:
          DATABASE_URL: postgres://postgres:postgres@localhost:5432/postgres
      - uses: codecov/codecov-action@v4
        with:
          files: coverage.xml

  e2e:
    if: github.event_name == 'schedule' || github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    needs: test
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -e ".[dev]"
      - run: pytest tests/e2e --run-slow -q
        env:
          SUPABASE_ACCESS_TOKEN_TEST: ${{ secrets.SUPABASE_ACCESS_TOKEN_TEST }}
          SUPABASE_ORG_SLUG_TEST: ${{ secrets.SUPABASE_ORG_SLUG_TEST }}
```

### 18.21 Coverage thresholds

```toml
# pyproject.toml
[tool.coverage.run]
source = ["compiler"]
omit = ["compiler/api/*"]

[tool.coverage.report]
fail_under = 80
exclude_lines = [
  "pragma: no cover",
  "raise NotImplementedError",
  "if TYPE_CHECKING:",
]
```

**Module-level targets (code review, not CI):**

| Module | Target |
|---|---|
| `interpreter/*` | 90% |
| `interpreter/negation.py` | 95% |
| `interpreter/merge.py` | 95% |
| `interpreter/laya_client.py` | 90% |
| `spec/validator.py` | 95% |
| `spec/derive.py` | 95% |
| `mcq/*` | 85% |
| `generator/*` | 85% |
| `deployer/errors.py` | 95% |
| `deployer/edge_functions.py` | 85% |
| `deployer/deployer.py` | 70% |

### 18.22 Running tests locally

```bash
pytest tests/unit tests/golden tests/integration -q
pytest --run-slow tests/e2e -q
pytest tests/unit/test_laya_client.py -v
pytest tests/unit/test_merge.py -v
pytest tests/unit/test_negation.py -v
pytest tests/unit/test_derive.py -v
pytest tests/unit/test_edge_derivation.py -v
pytest tests/unit/test_validator.py -v
pytest tests/integration/test_migration_cleanup.py -v
pytest --cov=compiler --cov-report=term-missing
```

---

## 19. Contacts & Escalation

- Laya → `github.com/NandhaKishorM/laya`
- Supabase → `supabase.com/docs/reference/api`
- Ontology → this document

**If something is not specified here, it is an engineering judgment call. Make the call, write a test, and update this document.**
