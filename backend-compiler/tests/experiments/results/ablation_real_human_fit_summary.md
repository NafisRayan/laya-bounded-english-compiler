# Ablation results (golden cases, real english checkpoint)

Config | n | macro recall | macro precision | pooled recall | pooled precision | omissions | hallucinations | feature-exact | all-match | params (pinned) | MCQ count (mean) | ms (mean)
---|---|---|---|---|---|---|---|---|---|---|---|---
A only + MCQ | 35 | 1.000 | 1.000 | 1.000 | 1.000 | 0 | 0 | 35 | 21 | 19/20 | 2.94 | 0.4
A only (no MCQ) | 35 | 0.143 | 0.143 | 0.000 | 1.000 | 56 | 0 | 5 | 3 | 0/20 | 1.29 | 0.3
B only + MCQ | 35 | 1.000 | 1.000 | 1.000 | 1.000 | 0 | 0 | 35 | 21 | 19/20 | 2.94 | 0.3
B only (no MCQ) | 35 | 0.701 | 0.771 | 0.679 | 1.000 | 18 | 0 | 21 | 6 | 2/20 | 2.29 | 0.2
A+B (rules) + MCQ | 35 | 1.000 | 1.000 | 1.000 | 1.000 | 0 | 0 | 35 | 21 | 19/20 | 2.94 | 0.3
A+B (rules) (no MCQ) | 35 | 0.701 | 0.771 | 0.679 | 1.000 | 18 | 0 | 21 | 6 | 4/20 | 2.17 | 0.2
C only (Laya) + MCQ | 35 | 1.000 | 0.986 | 1.000 | 0.982 | 0 | 1 | 34 | 21 | 19/20 | 3.11 | 0.6
C only (Laya) (no MCQ) | 35 | 0.380 | 0.486 | 0.214 | 0.923 | 44 | 1 | 11 | 4 | 0/20 | 2.11 | 0.6
A+B+C (hybrid) + MCQ | 35 | 1.000 | 0.986 | 1.000 | 0.982 | 0 | 1 | 34 | 21 | 19/20 | 3.11 | 0.5
A+B+C (hybrid) (no MCQ) | 35 | 0.796 | 0.900 | 0.768 | 0.977 | 13 | 1 | 22 | 7 | 5/20 | 2.66 | 0.5

Laya source: **real** pinned `english` checkpoint (convaiinnovations/laya), shared LayaClient. scoring gold: **adjudicated human annotation** (tests/annotation/human_gold.yaml) cases: **golden** set.
MCQ-off 'MCQ count' is the full residual question burden (untruncated): what the clarification loop would put to the user.