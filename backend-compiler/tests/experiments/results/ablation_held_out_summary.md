# Ablation results (golden cases, real english checkpoint)

Config | n | macro recall | macro precision | pooled recall | pooled precision | omissions | hallucinations | feature-exact | all-match | params (pinned) | MCQ count (mean) | ms (mean)
---|---|---|---|---|---|---|---|---|---|---|---|---
A only + MCQ | 15 | 0.356 | 0.311 | 0.269 | 0.304 | 19 | 16 | 2 | 2 | 3/9 | 7.00 | 0.4
A only (no MCQ) | 15 | 0.133 | 0.133 | 0.000 | 1.000 | 26 | 0 | 2 | 1 | 0/9 | 1.33 | 0.2
B only + MCQ | 15 | 0.803 | 0.547 | 0.846 | 0.579 | 4 | 16 | 2 | 1 | 2/9 | 7.20 | 0.2
B only (no MCQ) | 15 | 0.647 | 0.800 | 0.615 | 1.000 | 10 | 0 | 7 | 3 | 0/9 | 2.13 | 0.2
A+B (rules) + MCQ | 15 | 0.803 | 0.547 | 0.846 | 0.579 | 4 | 16 | 2 | 2 | 3/9 | 7.07 | 0.2
A+B (rules) (no MCQ) | 15 | 0.647 | 0.800 | 0.615 | 1.000 | 10 | 0 | 7 | 3 | 0/9 | 2.07 | 0.2
C only (Laya) + MCQ | 15 | 0.489 | 0.322 | 0.423 | 0.379 | 15 | 18 | 1 | 0 | 2/9 | 7.40 | 0.5
C only (Laya) (no MCQ) | 15 | 0.333 | 0.311 | 0.231 | 0.750 | 20 | 2 | 4 | 1 | 0/9 | 2.07 | 0.5
A+B+C (hybrid) + MCQ | 15 | 0.836 | 0.503 | 0.923 | 0.571 | 2 | 18 | 1 | 1 | 3/9 | 7.27 | 0.4
A+B+C (hybrid) (no MCQ) | 15 | 0.747 | 0.844 | 0.769 | 0.909 | 6 | 2 | 8 | 2 | 0/9 | 2.60 | 0.4

Laya source: **real** pinned `english` checkpoint (convaiinnovations/laya), shared LayaClient. scoring gold: **adjudicated human annotation** (tests/annotation/human_gold.yaml) cases: **held_out** set.
MCQ-off 'MCQ count' is the full residual question burden (untruncated): what the clarification loop would put to the user.