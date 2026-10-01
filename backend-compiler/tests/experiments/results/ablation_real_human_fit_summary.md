# Ablation results (golden cases, real english checkpoint)

Config | n | macro recall | macro precision | pooled recall | pooled precision | omissions | hallucinations | feature-exact | all-match | params (pinned) | MCQ count (mean) | ms (mean)
---|---|---|---|---|---|---|---|---|---|---|---|---
A only + MCQ | 35 | 0.592 | 0.848 | 0.518 | 0.896 | 40 | 5 | 11 | 6 | 9/21 | 6.40 | 0.3
A only (no MCQ) | 35 | 0.086 | 0.086 | 0.000 | 1.000 | 83 | 0 | 3 | 3 | 0/21 | 1.29 | 0.2
B only + MCQ | 35 | 0.881 | 0.916 | 0.916 | 0.938 | 7 | 5 | 27 | 7 | 9/21 | 6.49 | 0.2
B only (no MCQ) | 35 | 0.427 | 0.714 | 0.458 | 1.000 | 45 | 0 | 3 | 3 | 2/21 | 2.29 | 0.2
A+B (rules) + MCQ | 35 | 0.881 | 0.916 | 0.916 | 0.938 | 7 | 5 | 27 | 10 | 12/21 | 6.31 | 0.2
A+B (rules) (no MCQ) | 35 | 0.427 | 0.714 | 0.458 | 1.000 | 45 | 0 | 3 | 3 | 2/21 | 2.17 | 0.2
C only (Laya) + MCQ | 35 | 0.693 | 0.879 | 0.627 | 0.912 | 31 | 5 | 16 | 6 | 7/21 | 6.77 | 0.5
C only (Laya) (no MCQ) | 35 | 0.246 | 0.457 | 0.157 | 1.000 | 70 | 0 | 4 | 3 | 0/21 | 2.11 | 0.4
A+B+C (hybrid) + MCQ | 35 | 0.905 | 0.945 | 0.940 | 0.940 | 5 | 5 | 27 | 10 | 12/21 | 6.43 | 0.4
A+B+C (hybrid) (no MCQ) | 35 | 0.510 | 0.857 | 0.530 | 1.000 | 39 | 0 | 4 | 4 | 3/21 | 2.66 | 0.4

Laya source: **real** pinned `english` checkpoint (convaiinnovations/laya), shared LayaClient. scoring gold: **adjudicated human annotation** (tests/annotation/human_gold.yaml) cases: **golden** set.
MCQ-off 'MCQ count' is the full residual question burden (untruncated): what the clarification loop would put to the user.