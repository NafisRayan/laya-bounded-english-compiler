# Ablation results (golden cases, real english checkpoint)

Config | n | macro recall | macro precision | pooled recall | pooled precision | omissions | hallucinations | feature-exact | all-match | params (pinned) | MCQ count (mean) | ms (mean)
---|---|---|---|---|---|---|---|---|---|---|---|---
A only + MCQ | 15 | 0.663 | 0.933 | 0.525 | 0.913 | 19 | 2 | 5 | 2 | 3/9 | 7.00 | 0.4
A only (no MCQ) | 15 | 0.067 | 0.067 | 0.000 | 1.000 | 40 | 0 | 1 | 1 | 0/9 | 1.33 | 0.2
B only + MCQ | 15 | 0.920 | 0.944 | 0.900 | 0.947 | 4 | 2 | 10 | 1 | 2/9 | 7.20 | 0.3
B only (no MCQ) | 15 | 0.357 | 0.733 | 0.400 | 1.000 | 24 | 0 | 1 | 1 | 0/9 | 2.13 | 0.2
A+B (rules) + MCQ | 15 | 0.920 | 0.944 | 0.900 | 0.947 | 4 | 2 | 10 | 2 | 3/9 | 7.07 | 0.2
A+B (rules) (no MCQ) | 15 | 0.357 | 0.733 | 0.400 | 1.000 | 24 | 0 | 1 | 1 | 0/9 | 2.07 | 0.2
C only (Laya) + MCQ | 15 | 0.707 | 0.872 | 0.625 | 0.862 | 15 | 4 | 4 | 0 | 2/9 | 7.40 | 0.5
C only (Laya) (no MCQ) | 15 | 0.156 | 0.244 | 0.150 | 0.750 | 34 | 2 | 0 | 0 | 0/9 | 2.07 | 0.4
A+B+C (hybrid) + MCQ | 15 | 0.909 | 0.872 | 0.950 | 0.905 | 2 | 4 | 9 | 1 | 3/9 | 7.27 | 0.5
A+B+C (hybrid) (no MCQ) | 15 | 0.391 | 0.778 | 0.500 | 0.909 | 20 | 2 | 0 | 0 | 0/9 | 2.60 | 0.4

Laya source: **real** pinned `english` checkpoint (convaiinnovations/laya), shared LayaClient. scoring gold: **adjudicated human annotation** (tests/annotation/human_gold.yaml) cases: **held_out** set.
MCQ-off 'MCQ count' is the full residual question burden (untruncated): what the clarification loop would put to the user.