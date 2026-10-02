# Ablation results (golden cases, real english checkpoint)

Config | n | macro recall | macro precision | pooled recall | pooled precision | omissions | hallucinations | feature-exact | all-match | params (pinned) | MCQ count (mean) | ms (mean)
---|---|---|---|---|---|---|---|---|---|---|---|---
A only + MCQ | 15 | 1.000 | 1.000 | 1.000 | 1.000 | 0 | 0 | 15 | 8 | 8/9 | 2.47 | 0.4
A only (no MCQ) | 15 | 0.133 | 0.133 | 0.000 | 1.000 | 25 | 0 | 2 | 1 | 0/9 | 1.33 | 0.2
B only + MCQ | 15 | 1.000 | 1.000 | 1.000 | 1.000 | 0 | 0 | 15 | 8 | 8/9 | 2.47 | 0.2
B only (no MCQ) | 15 | 0.681 | 0.800 | 0.640 | 1.000 | 9 | 0 | 8 | 3 | 0/9 | 2.13 | 0.2
A+B (rules) + MCQ | 15 | 1.000 | 1.000 | 1.000 | 1.000 | 0 | 0 | 15 | 8 | 8/9 | 2.47 | 0.2
A+B (rules) (no MCQ) | 15 | 0.681 | 0.800 | 0.640 | 1.000 | 9 | 0 | 8 | 3 | 0/9 | 2.07 | 0.2
C only (Laya) + MCQ | 15 | 0.933 | 0.911 | 1.000 | 0.926 | 0 | 2 | 13 | 7 | 8/9 | 2.60 | 0.5
C only (Laya) (no MCQ) | 15 | 0.167 | 0.178 | 0.120 | 0.600 | 22 | 2 | 1 | 0 | 0/9 | 1.73 | 0.5
A+B+C (hybrid) + MCQ | 15 | 0.933 | 0.911 | 1.000 | 0.926 | 0 | 2 | 13 | 7 | 8/9 | 2.60 | 0.5
A+B+C (hybrid) (no MCQ) | 15 | 0.681 | 0.778 | 0.720 | 0.900 | 7 | 2 | 7 | 2 | 0/9 | 2.40 | 0.4

Laya source: **real** pinned `english` checkpoint (convaiinnovations/laya), shared LayaClient. scoring gold: **adjudicated human annotation** (tests/annotation/human_gold.yaml) cases: **held_out** set.
MCQ-off 'MCQ count' is the full residual question burden (untruncated): what the clarification loop would put to the user.