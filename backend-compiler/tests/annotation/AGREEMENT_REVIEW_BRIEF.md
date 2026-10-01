# Agreement-bias re-review — instructions for the independent reviewer

You are the fresh pair of eyes this project's measurement protocol calls for.
Everything you need is in this file and the two worklist files. Expected effort:
**~2.5–3 hours** for the required tiers, +1 optional hour.

## What this project is (3 sentences)

A compiler turns plain-English app descriptions ("renters book equipment,
owners get paid through Stripe") into a precise backend spec, which is then
deployed to Supabase. To grade the compiler, the team needs a *ground-truth*
reading of every description ("human gold"). The clashes between the team's
own reading and the compiler were adjudicated by an independent third reader —
but rows where the two readers **agreed** were never checked, because there
was no clash to flag. That blind spot is called **agreement bias**: both
readers can agree on something the sentence never says. You are checking it.

## The only evidence: the input sentence

Every row gives you `input` (the sentence) and an item currently in (or
removed from) the gold. Your question for every row is exactly one thing:

> **Does this sentence say — or clearly imply — this item?**

Three rules, same as every prior pass:

1. **Only the sentence counts.** Not what apps usually have, not what the
   tool can build, not what seems sensible for a real product.
2. **Not mentioned = doesn't belong.** If the sentence doesn't say it or
   clearly imply it, it must not be in the gold.
3. **Genuinely torn is a real verdict.** If a reasonable person could read
   the sentence either way, say `ambiguous` — that is an answer, not a dodge.

One policy is already settled corpus-wide and is **not** yours to re-litigate:
`edge_functions` (webhooks, notification dispatch) were removed everywhere,
because no sentence in the corpus mentions that class of infrastructure.
They will not appear in your worklist.

## What the item kinds mean

- `features` — e.g. `bookings:True` / `payments:False`: the sentence requires
  (True) or forbids (False) this capability.
- `parameters` — e.g. `['bookings.mode', 'request_then_approval']`: the
  sentence pins a *specific value*. Ask the harder question: does the
  sentence pin **this value**, or just the general topic? A sentence can
  mention bookings without pinning the mode.
- `roles` — a named user type (`owner`, `renter`, `admin`…). In the gold only
  if the sentence names it or a very close equivalent.
- `buckets` — storage buckets (`listings`, `documents`…), only if the
  sentence describes uploads/storage of that thing.

A lexical anchor is **necessary but not sufficient**: the word "verification"
appearing in a sentence anchors a *verification feature*, but it does not by
itself pin a specific method value. Judge the item, not the word match.

## Blinding protocol — follow it exactly

**Phase A (blind):** open `AGREEMENT_REVIEW_PHASE_A.yaml` and judge every
tier 1–3 row from its sentence alone. While Phase A is incomplete, do NOT
open: `LINTER_RULINGS.md`, `AGREEMENT_REVIEW_WORKLIST.yaml`,
`ADJUDICATION.yaml`, `Paper.md`, `anchor_lint_engine.txt`, or any
`expected_spec` in `tests/golden/cases/`. Record your Phase A verdicts in your
report file *before* looking at any of those.

**Phase B (diff):** after Phase A is saved, open
`AGREEMENT_REVIEW_WORKLIST.yaml` (same rows, plus the prior rulings) and
`LINTER_RULINGS.md`. List every row where your verdict disagrees with the
prior ruling. Do not edit your Phase A verdicts — the diff *is* the finding.

## The tiers

| Tier | Rows | What it is | Verdict vocabulary | Required |
|---|---|---|---|---|
| 1 | 82 | Items the linter flagged as word-missing, kept in gold on the judgment that the sentence *implies* them | `confirm_keep` / `recommend_drop` / `ambiguous` | **yes** |
| 2 | 5 | Judgment drops already applied to gold | `confirm_drop` / `recommend_restore` | **yes** |
| 3 | 34 | Anchored parameters + negated features — the value/faithfulness check | `keep` / `recommend_drop` / `ambiguous` | **yes** |
| 4 | 63 | Anchored features/roles/buckets — full sweep | same as tier 3 | optional |

Tier 1 is the heart of the pass: for every one of those 82 rows, the item's
own word does not appear in the sentence, so someone decided the sentence
*implies* it. Your job is to agree or disagree, row by row, from the sentence.

## Report format — one file, machine-checkable

Write `tests/annotation/AGREEMENT_REVIEW_REPORT.yaml` (create it; do not
modify any other file). Schema:

```yaml
reviewer: <your name>
date: <yyyy-mm-dd>
minutes_spent_phase_a: <int>
phase_a_completed_blind: true   # only write true if it is
rows:
  - tier: 1
    case: bucket_purpose_avatars
    kind: features
    item: "authentication:True"
    verdict: ambiguous            # your Phase A verdict
    reason: "sentence says 'sign up' — registration act, but no login method named"
    confidence: medium            # high | medium | low
  # ... one entry per tier 1-3 row (tier 4 if attempted), same fields
phase_b_diffs:
  - case: <case>
    item: <item>
    my_verdict: <yours>
    prior_ruling: <keep|drop>
    comment: <one line>
notes: <anything you noticed, including process complaints>
```

The `reason` field must **quote the words from the sentence that decided
your verdict**. A reason like "seems right" is not usable; "sentence says
'upload a profile photo'" is.

## Hard constraints

- **Do not edit any existing file.** Your report file is the only write.
- **Do not run the test suite, experiments, or any scoring script.** The
  held-out set has been scored exactly once under a frozen protocol; nothing
  you do may trigger or appear to trigger a re-measurement.
- **Do not "fix" gold** even when you are sure — a `recommend_drop` verdict
  is a recommendation. The team decides application, with disclosure either
  way; your independence is worth more than a fast edit.
- If a sentence is ambiguous *to you*, that is data — record `ambiguous`.

## What happens with your report

The third reader (who made the prior rulings, non-blind) will validate it:
re-judge every Phase B disagreement and spot-check ~10% of your agreements,
then hand the team a final note. Any gold change and whether a re-score is
warranted is the team's decision — your name goes on the review, not on the
gold. If you finish all required tiers, the paper's "agreement bias only
partially measured" disclosure upgrades to "measured" — that is the prize.

## File map

- `tests/annotation/AGREEMENT_REVIEW_PHASE_A.yaml` — your Phase A worklist
- `tests/annotation/AGREEMENT_REVIEW_WORKLIST.yaml` — Phase B (with rulings)
- `tests/annotation/human_gold.yaml` — the gold under review (read-only)
- `tests/annotation/anchor_lint_human.txt` — the mechanical linter report (safe anytime)
- `tests/annotation/LINTER_RULINGS.md` — Phase B only
- Your output: `tests/annotation/AGREEMENT_REVIEW_REPORT.yaml`
