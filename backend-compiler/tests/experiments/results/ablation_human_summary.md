# Ablation results (golden cases, mock Laya personas)

Config | n | macro recall | macro precision | pooled recall | pooled precision | omissions | hallucinations | feature-exact | all-match | params (pinned) | MCQ count (mean) | ms (mean)
---|---|---|---|---|---|---|---|---|---|---|---|---
A only + MCQ | 35 | 1.000 | 1.000 | 1.000 | 1.000 | 0 | 0 | 35 | 21 | 19/21 | 2.94 | 0.2
A only (no MCQ) | 35 | 0.143 | 0.143 | 0.000 | 1.000 | 57 | 0 | 5 | 3 | 0/21 | 1.29 | 0.2
B only + MCQ | 35 | 1.000 | 1.000 | 1.000 | 1.000 | 0 | 0 | 35 | 21 | 19/21 | 2.94 | 0.2
B only (no MCQ) | 35 | 0.687 | 0.771 | 0.667 | 1.000 | 19 | 0 | 20 | 6 | 2/21 | 2.29 | 0.2
A+B (rules) + MCQ | 35 | 1.000 | 1.000 | 1.000 | 1.000 | 0 | 0 | 35 | 21 | 19/21 | 2.94 | 0.2
A+B (rules) (no MCQ) | 35 | 0.687 | 0.771 | 0.667 | 1.000 | 19 | 0 | 20 | 6 | 3/21 | 2.17 | 0.2
C only (Laya) + MCQ | 35 | 1.000 | 0.951 | 1.000 | 0.770 | 0 | 17 | 33 | 20 | 19/21 | 3.09 | 0.3
C only (Laya) (no MCQ) | 35 | 0.200 | 0.151 | 0.053 | 0.150 | 54 | 17 | 5 | 3 | 0/21 | 1.69 | 0.2
A+B+C (hybrid) + MCQ | 35 | 1.000 | 0.951 | 1.000 | 0.770 | 0 | 17 | 33 | 20 | 19/21 | 3.09 | 0.2
A+B+C (hybrid) (no MCQ) | 35 | 0.701 | 0.723 | 0.684 | 0.696 | 18 | 17 | 19 | 6 | 4/21 | 2.46 | 0.2

Personas used: **none** (43), **default** (5), **high** (2). scoring gold: **adjudicated human annotation** (tests/annotation/human_gold.yaml) cases: **golden** set.
MCQ-off 'MCQ count' is the full residual question burden (untruncated): what the clarification loop would put to the user.