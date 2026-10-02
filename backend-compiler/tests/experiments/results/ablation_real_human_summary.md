# Ablation results (golden cases, real english checkpoint)

Config | n | macro recall | macro precision | pooled recall | pooled precision | omissions | hallucinations | feature-exact | all-match | params (pinned) | MCQ count (mean) | ms (mean)
---|---|---|---|---|---|---|---|---|---|---|---|---
A only + MCQ | 35 | 1.000 | 1.000 | 1.000 | 1.000 | 0 | 0 | 35 | 21 | 19/20 | 2.94 | 0.3
A only (no MCQ) | 35 | 0.143 | 0.143 | 0.000 | 1.000 | 56 | 0 | 5 | 3 | 0/20 | 1.29 | 0.3
B only + MCQ | 35 | 1.000 | 1.000 | 1.000 | 1.000 | 0 | 0 | 35 | 21 | 19/20 | 2.94 | 0.2
B only (no MCQ) | 35 | 0.701 | 0.771 | 0.679 | 1.000 | 18 | 0 | 21 | 6 | 2/20 | 2.29 | 0.2
A+B (rules) + MCQ | 35 | 1.000 | 1.000 | 1.000 | 1.000 | 0 | 0 | 35 | 21 | 19/20 | 2.94 | 0.2
A+B (rules) (no MCQ) | 35 | 0.701 | 0.771 | 0.679 | 1.000 | 18 | 0 | 21 | 6 | 4/20 | 2.17 | 0.2
C only (Laya) + MCQ | 35 | 0.971 | 0.943 | 1.000 | 0.949 | 0 | 3 | 32 | 19 | 19/20 | 3.14 | 0.6
C only (Laya) (no MCQ) | 35 | 0.445 | 0.529 | 0.339 | 0.864 | 37 | 3 | 12 | 3 | 0/20 | 2.31 | 0.6
A+B+C (hybrid) + MCQ | 35 | 0.971 | 0.943 | 1.000 | 0.949 | 0 | 3 | 32 | 19 | 19/20 | 3.14 | 0.5
A+B+C (hybrid) (no MCQ) | 35 | 0.820 | 0.886 | 0.821 | 0.939 | 10 | 3 | 22 | 6 | 5/20 | 2.80 | 0.5

Laya source: **real** pinned `english` checkpoint (convaiinnovations/laya), shared LayaClient. scoring gold: **adjudicated human annotation** (tests/annotation/human_gold.yaml) cases: **golden** set.
MCQ-off 'MCQ count' is the full residual question burden (untruncated): what the clarification loop would put to the user.