# Ablation results (golden cases, mock Laya personas)

Config | n | macro recall | macro precision | pooled recall | pooled precision | omissions | hallucinations | feature-exact | all-match | params (pinned) | MCQ count (mean) | ms (mean)
---|---|---|---|---|---|---|---|---|---|---|---|---
A only + MCQ | 35 | 1.000 | 1.000 | 1.000 | 1.000 | 0 | 0 | 35 | 21 | 19/20 | 2.94 | 0.2
A only (no MCQ) | 35 | 0.143 | 0.143 | 0.000 | 1.000 | 56 | 0 | 5 | 3 | 0/20 | 1.29 | 0.1
B only + MCQ | 35 | 1.000 | 1.000 | 1.000 | 1.000 | 0 | 0 | 35 | 21 | 19/20 | 2.94 | 0.1
B only (no MCQ) | 35 | 0.701 | 0.771 | 0.679 | 1.000 | 18 | 0 | 21 | 6 | 2/20 | 2.29 | 0.1
A+B (rules) + MCQ | 35 | 1.000 | 1.000 | 1.000 | 1.000 | 0 | 0 | 35 | 21 | 19/20 | 2.94 | 0.1
A+B (rules) (no MCQ) | 35 | 0.701 | 0.771 | 0.679 | 1.000 | 18 | 0 | 21 | 6 | 4/20 | 2.17 | 0.1
C only (Laya) + MCQ | 35 | 1.000 | 0.951 | 1.000 | 0.767 | 0 | 17 | 33 | 20 | 19/20 | 3.09 | 0.2
C only (Laya) (no MCQ) | 35 | 0.200 | 0.151 | 0.054 | 0.150 | 53 | 17 | 5 | 3 | 0/20 | 1.69 | 0.1
A+B+C (hybrid) + MCQ | 35 | 1.000 | 0.951 | 1.000 | 0.767 | 0 | 17 | 33 | 20 | 19/20 | 3.09 | 0.1
A+B+C (hybrid) (no MCQ) | 35 | 0.715 | 0.723 | 0.696 | 0.696 | 17 | 17 | 20 | 6 | 5/20 | 2.46 | 0.1

Personas used: **none** (43), **default** (5), **high** (2). scoring gold: **adjudicated human annotation** (tests/annotation/human_gold.yaml) cases: **golden** set.
MCQ-off 'MCQ count' is the full residual question burden (untruncated): what the clarification loop would put to the user.