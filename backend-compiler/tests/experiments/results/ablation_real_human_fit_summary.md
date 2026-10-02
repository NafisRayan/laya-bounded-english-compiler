# Ablation results (golden cases, real english checkpoint)

Config | n | macro recall | macro precision | pooled recall | pooled precision | omissions | hallucinations | feature-exact | all-match | params (pinned) | MCQ count (mean) | ms (mean)
---|---|---|---|---|---|---|---|---|---|---|---|---
A only + MCQ | 35 | 1.000 | 1.000 | 1.000 | 1.000 | 0 | 0 | 35 | 21 | 19/21 | 2.94 | 0.3
A only (no MCQ) | 35 | 0.143 | 0.143 | 0.000 | 1.000 | 57 | 0 | 5 | 3 | 0/21 | 1.29 | 0.2
B only + MCQ | 35 | 1.000 | 1.000 | 1.000 | 1.000 | 0 | 0 | 35 | 21 | 19/21 | 2.94 | 0.2
B only (no MCQ) | 35 | 0.687 | 0.771 | 0.667 | 1.000 | 19 | 0 | 20 | 6 | 2/21 | 2.29 | 0.1
A+B (rules) + MCQ | 35 | 1.000 | 1.000 | 1.000 | 1.000 | 0 | 0 | 35 | 21 | 19/21 | 2.94 | 0.2
A+B (rules) (no MCQ) | 35 | 0.687 | 0.771 | 0.667 | 1.000 | 19 | 0 | 20 | 6 | 3/21 | 2.17 | 0.2
C only (Laya) + MCQ | 35 | 1.000 | 0.990 | 1.000 | 0.983 | 0 | 1 | 34 | 21 | 19/21 | 3.09 | 0.4
C only (Laya) (no MCQ) | 35 | 0.380 | 0.486 | 0.211 | 0.923 | 45 | 1 | 11 | 4 | 0/21 | 2.11 | 0.4
A+B+C (hybrid) + MCQ | 35 | 1.000 | 0.990 | 1.000 | 0.983 | 0 | 1 | 34 | 21 | 19/21 | 3.09 | 0.4
A+B+C (hybrid) (no MCQ) | 35 | 0.782 | 0.900 | 0.754 | 0.977 | 14 | 1 | 22 | 7 | 4/21 | 2.66 | 0.3

Laya source: **real** pinned `english` checkpoint (convaiinnovations/laya), shared LayaClient. scoring gold: **adjudicated human annotation** (tests/annotation/human_gold.yaml) cases: **golden** set.
MCQ-off 'MCQ count' is the full residual question burden (untruncated): what the clarification loop would put to the user.