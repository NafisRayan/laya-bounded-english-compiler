# Ablation results (golden cases, real english checkpoint)

Config | n | macro recall | macro precision | pooled recall | pooled precision | omissions | hallucinations | feature-exact | all-match | params (pinned) | MCQ count (mean) | ms (mean)
---|---|---|---|---|---|---|---|---|---|---|---|---
A only + MCQ | 35 | 0.592 | 0.848 | 0.518 | 0.896 | 40 | 5 | 11 | 6 | 9/21 | 6.40 | 0.3
A only (no MCQ) | 35 | 0.086 | 0.086 | 0.000 | 1.000 | 83 | 0 | 3 | 3 | 0/21 | 1.29 | 0.2
B only + MCQ | 35 | 0.881 | 0.916 | 0.916 | 0.938 | 7 | 5 | 27 | 7 | 9/21 | 6.49 | 0.2
B only (no MCQ) | 35 | 0.427 | 0.714 | 0.458 | 1.000 | 45 | 0 | 3 | 3 | 2/21 | 2.29 | 0.2
A+B (rules) + MCQ | 35 | 0.881 | 0.916 | 0.916 | 0.938 | 7 | 5 | 27 | 10 | 12/21 | 6.31 | 0.2
A+B (rules) (no MCQ) | 35 | 0.427 | 0.714 | 0.458 | 1.000 | 45 | 0 | 3 | 3 | 2/21 | 2.17 | 0.2
C only (Laya) + MCQ | 35 | 0.704 | 0.848 | 0.687 | 0.891 | 26 | 7 | 15 | 5 | 7/21 | 6.80 | 0.5
C only (Laya) (no MCQ) | 35 | 0.274 | 0.500 | 0.241 | 0.909 | 63 | 2 | 3 | 2 | 0/21 | 2.31 | 0.5
A+B+C (hybrid) + MCQ | 35 | 0.890 | 0.911 | 0.952 | 0.919 | 4 | 7 | 25 | 9 | 12/21 | 6.46 | 0.4
A+B+C (hybrid) (no MCQ) | 35 | 0.513 | 0.843 | 0.566 | 0.959 | 36 | 2 | 3 | 3 | 3/21 | 2.80 | 0.4

Laya source: **real** pinned `english` checkpoint (convaiinnovations/laya), shared LayaClient. scoring gold: **adjudicated human annotation** (tests/annotation/human_gold.yaml) cases: **golden** set.
MCQ-off 'MCQ count' is the full residual question burden (untruncated): what the clarification loop would put to the user.