# Ablation results (golden cases, mock Laya personas)

Config | n | macro recall | macro precision | pooled recall | pooled precision | omissions | hallucinations | feature-exact | all-match | params (pinned) | MCQ count (mean) | ms (mean)
---|---|---|---|---|---|---|---|---|---|---|---|---
A only + MCQ | 35 | 0.346 | 0.321 | 0.316 | 0.375 | 39 | 30 | 5 | 4 | 9/21 | 6.40 | 0.1
A only (no MCQ) | 35 | 0.143 | 0.143 | 0.000 | 1.000 | 57 | 0 | 5 | 3 | 0/21 | 1.29 | 0.1
B only + MCQ | 35 | 0.814 | 0.585 | 0.895 | 0.630 | 6 | 30 | 7 | 2 | 9/21 | 6.49 | 0.1
B only (no MCQ) | 35 | 0.687 | 0.771 | 0.667 | 1.000 | 19 | 0 | 20 | 6 | 2/21 | 2.29 | 0.1
A+B (rules) + MCQ | 35 | 0.814 | 0.585 | 0.895 | 0.630 | 6 | 30 | 7 | 4 | 13/21 | 6.31 | 0.1
A+B (rules) (no MCQ) | 35 | 0.687 | 0.771 | 0.667 | 1.000 | 19 | 0 | 20 | 6 | 3/21 | 2.17 | 0.1
C only (Laya) + MCQ | 35 | 0.404 | 0.330 | 0.368 | 0.309 | 36 | 47 | 5 | 2 | 7/21 | 6.89 | 0.1
C only (Laya) (no MCQ) | 35 | 0.200 | 0.151 | 0.053 | 0.150 | 54 | 17 | 5 | 3 | 0/21 | 1.69 | 0.1
A+B+C (hybrid) + MCQ | 35 | 0.829 | 0.536 | 0.912 | 0.525 | 5 | 47 | 6 | 4 | 14/21 | 6.60 | 0.1
A+B+C (hybrid) (no MCQ) | 35 | 0.701 | 0.723 | 0.684 | 0.696 | 18 | 17 | 19 | 6 | 4/21 | 2.46 | 0.1

Personas used: **none** (43), **default** (5), **high** (2). scoring gold: **adjudicated human annotation** (tests/annotation/human_gold.yaml) cases: **golden** set.
MCQ-off 'MCQ count' is the full residual question burden (untruncated): what the clarification loop would put to the user.