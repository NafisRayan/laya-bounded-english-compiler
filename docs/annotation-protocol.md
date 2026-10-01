# Independent annotation protocol (paper §4.4)

Goal: replace the engine-pinned golden expectations with independently
authored ground truth, so R1/R2/R3 numbers stop being in-sample. The
protocol is intentionally small — one annotator, one pass, one schema.

## Setup

1. The 50 inputs are split deterministically (`tests/golden/splits.yaml`,
   seed 20260930): **35 golden** (working set) and **15 held-out**. The
   held-out 15 must be annotated FIRST and not looked at again until the
   final measurement, so the held-out numbers stay honest.
2. Annotator reads only the `input` text of each case — **never** the
   engine's `expected_spec`, never the engine's outputs. The current case
   files stay untouched; annotations land in a NEW directory
   (`tests/annotation/`) so authoring bias is measurable by diff.

## Per-case annotation form

For each input, write YAML with the same schema the scorer consumes
(`tests/experiments/metrics.py::extract_labels`):

```yaml
# tests/annotation/<case_name>.yaml
case: booking_mode_request_then_approval
input: <paste the exact input text>
features:                 # every feature the input requires (true) or forbids (false)
  bookings: true
  payments: false
parameters:               # parameter:value only where the input pins a choice
  booking.mode: request_then_approval
roles: [owner, renter]    # only if the input names roles
buckets: [listings]       # only if the input explicitly describes file storage
edge_functions: []        # only if the input explicitly describes them (never inferred from features)
notes: anything ambiguous, in the annotator's own words
```

Rules:

- Under-specify rather than guess: omit a feature if the input is silent.
  The metrics treat omitted-from-gold as "should be disabled", so omission
  judgment matters and must be the annotator's, not the engine's.
- Contradictions in the input: record BOTH readings in `notes`, pick the
  more conservative one, move on — do not consult the engine.
- Time-box: ~4 minutes per case; flag anything over.

## Adjudication

After both annotation passes exist (engine-pinned vs independent):

1. Diff per case: any disagreement between the independent annotation and
   the engine-pinned gold is a finding — list it in
   `tests/annotation/DISAGREEMENTS.json` with one line each, and the
   rulings themselves go to `tests/annotation/ADJUDICATION.yaml`.
2. The paper reports metrics under BOTH gold sets. The independent set
   becomes primary only after the disagreements are adjudicated (ideally by
   a third reader).
3. Held-out cases are scored exactly once, after all measurement code is
   frozen, and never used for tuning.
4. Agreement re-reviews (rows where annotator and engine agree, invisible
   to the clash diff) run blind on stripped copies: blinding is
   load-bearing where prior rulings exist (the tier 1–2 checks) and
   trivial for mechanical/consistency checks (tier 3–4) — future
   reviewers get stripped copies regardless.

## Scoring

`extract_labels` consumes the same keys, so no scorer changes are needed:

```bash
python -m tests.experiments.run_ablation          # in-sample (existing)
python -m tests.experiments.run_calibration        # pairs, same corpus
# held-out scoring: point the runner at the annotation dir (to be wired when
# the annotation pass lands)
```
