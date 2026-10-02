# Ablation results (golden cases, real english checkpoint)

Config | n | macro recall | macro precision | pooled recall | pooled precision | omissions | hallucinations | feature-exact | all-match | params (pinned) | MCQ count (mean) | ms (mean)
---|---|---|---|---|---|---|---|---|---|---|---|---
A only + MCQ | 35 | 1.000 | 1.000 | 1.000 | 1.000 | 0 | 0 | 35 | 21 | 19/21 | 2.94 | 0.3
A only (no MCQ) | 35 | 0.143 | 0.143 | 0.000 | 1.000 | 57 | 0 | 5 | 3 | 0/21 | 1.29 | 0.2
B only + MCQ | 35 | 1.000 | 1.000 | 1.000 | 1.000 | 0 | 0 | 35 | 21 | 19/21 | 2.94 | 0.2
B only (no MCQ) | 35 | 0.687 | 0.771 | 0.667 | 1.000 | 19 | 0 | 20 | 6 | 2/21 | 2.29 | 0.2
A+B (rules) + MCQ | 35 | 1.000 | 1.000 | 1.000 | 1.000 | 0 | 0 | 35 | 21 | 19/21 | 2.94 | 0.2
A+B (rules) (no MCQ) | 35 | 0.687 | 0.771 | 0.667 | 1.000 | 19 | 0 | 20 | 6 | 3/21 | 2.17 | 0.2
C only (Laya) + MCQ | 35 | 0.971 | 0.948 | 1.000 | 0.950 | 0 | 3 | 32 | 19 | 19/21 | 3.11 | 0.5
C only (Laya) (no MCQ) | 35 | 0.445 | 0.529 | 0.333 | 0.864 | 38 | 3 | 12 | 3 | 0/21 | 2.31 | 0.4
A+B+C (hybrid) + MCQ | 35 | 0.971 | 0.948 | 1.000 | 0.950 | 0 | 3 | 32 | 19 | 19/21 | 3.11 | 0.4
A+B+C (hybrid) (no MCQ) | 35 | 0.806 | 0.886 | 0.807 | 0.939 | 11 | 3 | 22 | 6 | 4/21 | 2.80 | 0.4

Laya source: **real** pinned `english` checkpoint (convaiinnovations/laya), shared LayaClient. scoring gold: **adjudicated human annotation** (tests/annotation/human_gold.yaml) cases: **golden** set.
MCQ-off 'MCQ count' is the full residual question burden (untruncated): what the clarification loop would put to the user.