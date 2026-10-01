# Ablation results (golden cases, real english checkpoint)

Config | n | macro recall | macro precision | pooled recall | pooled precision | omissions | hallucinations | feature-exact | all-match | params (pinned) | MCQ count (mean) | ms (mean)
---|---|---|---|---|---|---|---|---|---|---|---|---
A only + MCQ | 35 | 0.346 | 0.321 | 0.316 | 0.375 | 39 | 30 | 5 | 4 | 9/21 | 6.40 | 0.3
A only (no MCQ) | 35 | 0.143 | 0.143 | 0.000 | 1.000 | 57 | 0 | 5 | 3 | 0/21 | 1.29 | 0.2
B only + MCQ | 35 | 0.814 | 0.585 | 0.895 | 0.630 | 6 | 30 | 7 | 2 | 9/21 | 6.49 | 0.2
B only (no MCQ) | 35 | 0.687 | 0.771 | 0.667 | 1.000 | 19 | 0 | 20 | 6 | 2/21 | 2.29 | 0.2
A+B (rules) + MCQ | 35 | 0.814 | 0.585 | 0.895 | 0.630 | 6 | 30 | 7 | 4 | 13/21 | 6.31 | 0.2
A+B (rules) (no MCQ) | 35 | 0.687 | 0.771 | 0.667 | 1.000 | 19 | 0 | 20 | 6 | 3/21 | 2.17 | 0.2
C only (Laya) + MCQ | 35 | 0.558 | 0.455 | 0.561 | 0.500 | 25 | 32 | 4 | 1 | 7/21 | 6.80 | 0.5
C only (Laya) (no MCQ) | 35 | 0.445 | 0.529 | 0.333 | 0.864 | 38 | 3 | 12 | 3 | 0/21 | 2.31 | 0.5
A+B+C (hybrid) + MCQ | 35 | 0.843 | 0.604 | 0.947 | 0.628 | 3 | 32 | 6 | 3 | 13/21 | 6.46 | 0.4
A+B+C (hybrid) (no MCQ) | 35 | 0.806 | 0.886 | 0.807 | 0.939 | 11 | 3 | 22 | 6 | 4/21 | 2.80 | 0.4

Laya source: **real** pinned `english` checkpoint (convaiinnovations/laya), shared LayaClient. scoring gold: **adjudicated human annotation** (tests/annotation/human_gold.yaml) cases: **golden** set.
MCQ-off 'MCQ count' is the full residual question burden (untruncated): what the clarification loop would put to the user.