# Ablation results (50 golden cases, mock Laya personas)

Config | n | macro recall | macro precision | pooled recall | pooled precision | omissions | hallucinations | feature-exact | all-match | params (pinned) | MCQ count (mean) | ms (mean)
---|---|---|---|---|---|---|---|---|---|---|---|---
A only + MCQ | 50 | 0.702 | 0.960 | 0.550 | 1.000 | 58 | 0 | 21 | 21 | 16/26 | 6.58 | 0.3
A only (no MCQ) | 50 | 0.080 | 0.080 | 0.000 | 1.000 | 129 | 0 | 4 | 4 | 0/26 | 1.30 | 0.2
B only + MCQ | 50 | 0.972 | 1.000 | 0.922 | 1.000 | 10 | 0 | 48 | 42 | 19/26 | 6.70 | 0.3
B only (no MCQ) | 50 | 0.397 | 0.720 | 0.419 | 1.000 | 75 | 0 | 4 | 4 | 4/26 | 2.24 | 0.2
A+B (rules) + MCQ | 50 | 0.972 | 1.000 | 0.922 | 1.000 | 10 | 0 | 48 | 48 | 25/26 | 6.54 | 0.3
A+B (rules) (no MCQ) | 50 | 0.397 | 0.720 | 0.419 | 1.000 | 75 | 0 | 4 | 4 | 6/26 | 2.14 | 0.2
C only (Laya) + MCQ | 50 | 0.742 | 0.984 | 0.643 | 0.912 | 46 | 8 | 22 | 19 | 13/26 | 6.94 | 0.3
C only (Laya) (no MCQ) | 50 | 0.120 | 0.104 | 0.093 | 0.600 | 117 | 8 | 5 | 5 | 0/26 | 1.58 | 0.3
A+B+C (hybrid) + MCQ | 50 | 1.000 | 0.984 | 1.000 | 0.942 | 0 | 8 | 49 | 49 | 26/26 | 6.74 | 0.4
A+B+C (hybrid) (no MCQ) | 50 | 0.425 | 0.704 | 0.496 | 0.889 | 65 | 8 | 5 | 5 | 7/26 | 2.34 | 0.3

Personas used: **none** (43), **default** (5), **high** (2).
MCQ-off 'MCQ count' is the full residual question burden (untruncated): what the clarification loop would put to the user.