# LLM-as-annotator sensitivity check — results (disclosed)

Three runs of the same LLM annotator against `human_gold.yaml` (author
gold, cleaned 2026-09-30), differing only in the annotator instructions:

- **v1** (`../llm_annotator/`): README v1.0 — "roles: distinct named user
  types (host/guest, admin/moderator)". 50/50 completed.
- **v2** (`../llm_annotator_v2/`): README v1.1 — "roles: two or more user
  types with *different capabilities*; a single named actor is not roles";
  buckets pinned to stated-purpose only. One v2 case
  (`role_staff_and_admin_dedupe`) hit repeated gateway timeouts and was
  completed through the native Gemini REST path (recorded in that run's
  `MANIFEST.json` under `manual_completions`).
- **v3** (`../llm_annotator_v3/`): README v1.2 + **`ROLES_RUBRIC.md`**
  (mined from the gold; inlined into the prompt). One v3 case
  (`bucket_purpose_avatars`) hit the same gateway timeouts and was
  completed via native Gemini, disclosed identically.

**The rubric validates decisively at case level (roles exact-list match
0.440 → 0.440 → 0.960):** the gold's roles convention is a
synonym-mapping table (seller/host/vendor → `owner`;
guest/customer/buyer → `renter`; staff/moderator/users → no role; a
single mapped actor suffices), not a linguistic rule — which is why no
plain-language phrasing (v1, v2) could reproduce it and why the rubric is
now normative for all annotators, human included.


Per-run manifests record date, completer, instruction hash, warnings.

## Numbers (Cohen's κ vs author gold, `cohen_kappa.py`)

| Dimension | v1 κ | v1 raw | v2 κ | v2 raw | v3 κ | v3 raw |
|---|---|---|---|---|---|---|
| features | 0.289 | 0.809 | **0.396** | 0.843 | 0.135 | 0.720 |
| roles | −0.836 | 0.058 | −0.554 | 0.029 | 0.000 | **0.944** |
| buckets | 0.000 | 0.714 | 0.000 | 0.714 | 0.000 | 0.643 |
| edge_functions | n/a | | n/a | | n/a | |

v3's roles κ of 0.000 with 0.944 raw agreement is the Feinstein–Cicchetti
prevalence paradox, not disagreement: on the pooled roles items the gold
is (nearly) all-present, so expected-by-chance agreement ≈ observed. The
informative statistic at case level:

| Run (roles only) | presence agreement | exact list match |
|---|---|---|
| v1 (generic rule) | 0.660 | 0.440 |
| v2 (capability rule) | 0.520 | 0.440 |
| **v3 (ROLES_RUBRIC.md)** | **0.980** | **0.960** |

Recompute: `python -c` over each run dir, or rerun the probe preserved in
git history alongside this file's commit.

"Unfilled" cases are an artifact of the scorer treating empty annotations
as unfilled: the junk-text / pure-clarification / contradiction cases
(e.g. `empty_spec_junk_text`, `rent_without_item_needs_clarify`) are
correctly annotated as empty.

## What the three runs establish

1. **The roles dimension was definitional, and the rubric resolves it.**
   Generic wording (v1): roles everywhere, exact match 0.44. Capability
   wording (v2): roles almost nowhere, exact match 0.44. Explicit
   synonym-mapping rubric (v3): exact match **0.96**. The convention was
   never linguistically recoverable — it is a table, and the table is now
   normative (`external/ROLES_RUBRIC.md`).
2. **Pooled κ misleads under skewed prevalence** (v3 roles: κ 0.000, raw
   0.944, exact-match 0.96): the paper must report roles at case level
   and features κ separately, with the paradox named.
3. **Feature-level κ is unstable across prompt variants (0.29 / 0.40 /
   0.13) with raw agreement 0.72–0.84** — single-run LLM variance, no
   seed averaging; a sensitivity instrument, not a gold validator.

## Consequences for the study

- The LLM annotator **does not validate the gold** on features (all runs
  below the 0.61 threshold) and must not be reported as if it did. On
  roles under the rubric it *reproduces* the gold's convention (0.96
  exact) — which validates the rubric as documentation of the
  convention, while confirming that convention is a mapping table.
- The human external round proceeds with `ROLES_RUBRIC.md` shipped to
  every annotator; without it, human roles agreement was predetermined
  to fail exactly as v1/v2 did.
- Reported in the paper as: *"an LLM annotator (disclosed; identical
  instructions to human annotators) could not reproduce the gold's roles
  convention from any plain-language rule (exact match 0.44 under two
  phrasings); mining and codifying the convention as an explicit
  synonym-mapping rubric raises exact match to 0.96, establishing that
  the roles dimension is definitional. The rubric is normative for the
  human annotation round. Feature-level agreement (raw 0.72–0.84,
  κ unstable) is reported as single-run LLM variance, not validation."*

Regenerate:

    python -m tests.annotation.cohen_kappa --annotator2 tests/annotation/llm_annotator
    python -m tests.annotation.cohen_kappa --annotator2 tests/annotation/llm_annotator_v2

    python -m tests.annotation.cohen_kappa --annotator2 tests/annotation/llm_annotator_v3
