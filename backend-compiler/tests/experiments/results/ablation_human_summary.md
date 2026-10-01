# Ablation results (golden cases, mock Laya personas)

Config | n | macro recall | macro precision | pooled recall | pooled precision | omissions | hallucinations | feature-exact | all-match | params (pinned) | MCQ count (mean) | ms (mean)
---|---|---|---|---|---|---|---|---|---|---|---|---
A only + MCQ | 35 | 0.592 | 0.848 | 0.518 | 0.896 | 40 | 5 | 11 | 6 | 9/21 | 6.40 | 0.1
A only (no MCQ) | 35 | 0.086 | 0.086 | 0.000 | 1.000 | 83 | 0 | 3 | 3 | 0/21 | 1.29 | 0.1
B only + MCQ | 35 | 0.881 | 0.916 | 0.916 | 0.938 | 7 | 5 | 27 | 7 | 9/21 | 6.49 | 0.1
B only (no MCQ) | 35 | 0.427 | 0.714 | 0.458 | 1.000 | 45 | 0 | 3 | 3 | 2/21 | 2.29 | 0.1
A+B (rules) + MCQ | 35 | 0.881 | 0.916 | 0.916 | 0.938 | 7 | 5 | 27 | 10 | 12/21 | 6.31 | 0.1
A+B (rules) (no MCQ) | 35 | 0.427 | 0.714 | 0.458 | 1.000 | 45 | 0 | 3 | 3 | 2/21 | 2.17 | 0.1
C only (Laya) + MCQ | 35 | 0.649 | 0.859 | 0.566 | 0.691 | 36 | 21 | 11 | 4 | 7/21 | 6.89 | 0.2
C only (Laya) (no MCQ) | 35 | 0.143 | 0.097 | 0.048 | 0.200 | 79 | 16 | 3 | 3 | 0/21 | 1.69 | 0.1
A+B+C (hybrid) + MCQ | 35 | 0.910 | 0.870 | 0.940 | 0.788 | 5 | 21 | 27 | 10 | 13/21 | 6.60 | 0.1
A+B+C (hybrid) (no MCQ) | 35 | 0.456 | 0.669 | 0.482 | 0.714 | 43 | 16 | 3 | 3 | 3/21 | 2.46 | 0.1

Personas used: **none** (43), **default** (5), **high** (2). scoring gold: **adjudicated human annotation** (tests/annotation/human_gold.yaml) cases: **golden** set.
MCQ-off 'MCQ count' is the full residual question burden (untruncated): what the clarification loop would put to the user.