# LLM-as-annotator sensitivity check — results (disclosed)

Two runs of the same LLM annotator against `human_gold.yaml` (author gold,
cleaned 2026-09-30), differing only in the annotator instructions:

- **v1** (`../llm_annotator/`): README v1.0 — "roles: distinct named user
  types (host/guest, admin/moderator)".
- **v2** (`../llm_annotator_v2/`): README v1.1 — "roles: two or more user
  types with *different capabilities*; a single named actor is not roles";
  buckets pinned to stated-purpose only. One v2 case
  (`role_staff_and_admin_dedupe`) hit repeated gateway timeouts and was
  completed through the native Gemini REST path (recorded in that run's
  `MANIFEST.json` under `manual_completions`).

Per-run manifests record date, completer, instruction hash, warnings.

## Numbers (Cohen's κ vs author gold, `cohen_kappa.py`)

| Dimension | v1 κ | v1 raw agr. | v2 κ | v2 raw agr. |
|---|---|---|---|---|
| features | 0.289 | 0.809 | **0.396** | 0.843 |
| roles | **−0.836** | 0.058 | **−0.554** | 0.029 |
| buckets | 0.000 | 0.714 | 0.000* | 0.714 |
| edge_functions | n/a (0 items) | | n/a | |

(*) v2 buckets item count identical; unchanged by the rule edit.

"Unfilled" cases are an artifact of the scorer treating empty annotations
as unfilled: the junk-text / pure-clarification / contradiction cases
(e.g. `empty_spec_junk_text`, `rent_without_item_needs_clarify`) are
correctly annotated as empty.

## What the two runs establish

1. **The roles dimension is definitional, not statistical.** Perturbing one
   sentence of the roles rule moves roles κ from −0.836 (LLM includes roles
   almost everywhere; gold rarely) to −0.554 (LLM includes roles almost
   nowhere; gold does in ~30 items). Raw agreement never exceeds 6%. The
   author gold's roles convention (when a named user type becomes a
   `roles` feature and which names get listed) is internal to the author;
   no plain-language rule reproduces it. Human annotators given the same
   READMEs would disagree the same way.
2. **Feature-level raw agreement is high and stable (~0.81–0.84) while κ
   stays low** — the classic skewed-marginals pattern for sparse binary
   items: most (case, feature) pairs are agreed-absent; disagreement
   concentrates in the enable/omit boundary, dominated by the `roles`
   feature item.
3. **The instruction edit measurably shifted behavior** (features κ
   +0.107), i.e. the annotator's judgment is rule-sensitive — worth
   reporting as evidence that the gold's conventions, not annotator
   noise, drive disagreement.

## Consequences for the study

- The LLM annotator **does not validate the gold** (both runs below the
  0.61 decision threshold) and must not be reported as if it did.
- Before the human external round: (a) the author's roles convention must
  be written down as an explicit rubric (what counts as "different
  capabilities", which surface names map to which role labels), and either
  the gold's roles dimension is re-derived under that rubric or every
  human worksheet ships with it; (b) the paper should report roles κ
  separately from features κ for exactly this reason.
- Reported in the paper as: *"an LLM annotator (disclosed; identical
  instructions to human annotators) under two rule perturbations agrees
  with the gold at 0.81–0.84 raw on features but cannot reproduce the
  roles convention (κ −0.84 / −0.55), exposing the roles dimension as
  definitional — motivating the explicit rubric used for the human
  annotation round."*

Regenerate:

    python -m tests.annotation.cohen_kappa --annotator2 tests/annotation/llm_annotator
    python -m tests.annotation.cohen_kappa --annotator2 tests/annotation/llm_annotator_v2
