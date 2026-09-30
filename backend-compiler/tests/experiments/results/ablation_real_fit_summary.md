# Ablation results (50 golden cases, real english checkpoint)

Config | n | macro recall | macro precision | pooled recall | pooled precision | omissions | hallucinations | feature-exact | all-match | params (pinned) | MCQ count (mean) | ms (mean)
---|---|---|---|---|---|---|---|---|---|---|---|---
A only + MCQ | 50 | 0.702 | 0.960 | 0.550 | 1.000 | 58 | 0 | 21 | 21 | 16/26 | 6.58 | 0.4
A only (no MCQ) | 50 | 0.080 | 0.080 | 0.000 | 1.000 | 129 | 0 | 4 | 4 | 0/26 | 1.30 | 0.3
B only + MCQ | 50 | 0.972 | 1.000 | 0.922 | 1.000 | 10 | 0 | 48 | 42 | 19/26 | 6.70 | 0.3
B only (no MCQ) | 50 | 0.397 | 0.720 | 0.419 | 1.000 | 75 | 0 | 4 | 4 | 4/26 | 2.24 | 0.3
A+B (rules) + MCQ | 50 | 0.972 | 1.000 | 0.922 | 1.000 | 10 | 0 | 48 | 48 | 25/26 | 6.54 | 0.3
A+B (rules) (no MCQ) | 50 | 0.397 | 0.720 | 0.419 | 1.000 | 75 | 0 | 4 | 4 | 6/26 | 2.14 | 0.3
C only (Laya) + MCQ | 50 | 0.725 | 0.905 | 0.612 | 0.952 | 50 | 4 | 23 | 20 | 13/26 | 6.88 | 0.6
C only (Laya) (no MCQ) | 50 | 0.159 | 0.293 | 0.109 | 0.778 | 115 | 4 | 3 | 2 | 0/26 | 2.00 | 0.7
A+B+C (hybrid) + MCQ | 50 | 0.932 | 0.945 | 0.922 | 0.967 | 10 | 4 | 44 | 44 | 25/26 | 6.64 | 0.5
A+B+C (hybrid) (no MCQ) | 50 | 0.412 | 0.753 | 0.465 | 0.938 | 69 | 4 | 3 | 3 | 7/26 | 2.58 | 0.5

Laya source: **real** pinned `english` checkpoint (convaiinnovations/laya), shared LayaClient, same engine-pinned gold as the persona runs.
MCQ-off 'MCQ count' is the full residual question burden (untruncated): what the clarification loop would put to the user.