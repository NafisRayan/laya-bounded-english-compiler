# Ablation results (50 golden cases, real english checkpoint)

Config | n | macro recall | macro precision | pooled recall | pooled precision | omissions | hallucinations | feature-exact | all-match | params (pinned) | MCQ count (mean) | ms (mean)
---|---|---|---|---|---|---|---|---|---|---|---|---
A only + MCQ | 50 | 0.702 | 0.960 | 0.550 | 1.000 | 58 | 0 | 21 | 21 | 16/26 | 6.58 | 0.3
A only (no MCQ) | 50 | 0.080 | 0.080 | 0.000 | 1.000 | 129 | 0 | 4 | 4 | 0/26 | 1.30 | 0.2
B only + MCQ | 50 | 0.972 | 1.000 | 0.922 | 1.000 | 10 | 0 | 48 | 42 | 19/26 | 6.70 | 0.2
B only (no MCQ) | 50 | 0.397 | 0.720 | 0.419 | 1.000 | 75 | 0 | 4 | 4 | 4/26 | 2.24 | 0.2
A+B (rules) + MCQ | 50 | 0.972 | 1.000 | 0.922 | 1.000 | 10 | 0 | 48 | 48 | 25/26 | 6.54 | 0.2
A+B (rules) (no MCQ) | 50 | 0.397 | 0.720 | 0.419 | 1.000 | 75 | 0 | 4 | 4 | 6/26 | 2.14 | 0.2
C only (Laya) + MCQ | 50 | 0.730 | 0.858 | 0.651 | 0.903 | 45 | 9 | 20 | 16 | 13/26 | 6.98 | 0.5
C only (Laya) (no MCQ) | 50 | 0.174 | 0.313 | 0.163 | 0.700 | 108 | 9 | 2 | 1 | 0/26 | 2.24 | 0.4
A+B+C (hybrid) + MCQ | 50 | 0.912 | 0.898 | 0.922 | 0.930 | 10 | 9 | 39 | 39 | 25/26 | 6.70 | 0.4
A+B+C (hybrid) (no MCQ) | 50 | 0.404 | 0.713 | 0.481 | 0.873 | 67 | 9 | 2 | 2 | 7/26 | 2.74 | 0.4

Laya source: **real** pinned `english` checkpoint (convaiinnovations/laya), shared LayaClient, same engine-pinned gold as the persona runs.
MCQ-off 'MCQ count' is the full residual question burden (untruncated): what the clarification loop would put to the user.