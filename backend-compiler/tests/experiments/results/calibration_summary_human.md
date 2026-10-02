# Real-Laya calibration report (golden corpus, pinned english checkpoint)

Pairs: 500 (one per case x feature item; entity items skipped) across 50 cases.
Decision accuracy at the engine's rule (noul >= 0.5): 0.900

| Quantity | Value |
|---|---|
| Raw ECE (10 bins, shipped answer_confidence) | 0.0381 |
| Gate (ECE < 0.1) | PASS |
| Fitted temperature | 0.88 |
| ECE after fit | 0.0208 |

## Auto-accept sweep (threshold on answer_confidence)

| Threshold | Coverage | Accuracy among auto-accepted |
|---|---|---|
| 0.50 | 1.000 (500) | 0.900 |
| 0.55 | 0.982 (491) | 0.906 |
| 0.60 | 0.960 (480) | 0.912 |
| 0.65 | 0.934 (467) | 0.912 |
| 0.70 | 0.910 (455) | 0.921 |
| 0.75 | 0.878 (439) | 0.927 |
| 0.80 | 0.824 (412) | 0.942 |
| 0.85 | 0.706 (353) | 0.960 |
| 0.90 | 0.456 (228) | 0.961 |
| 0.95 | 0.186 (93) | 0.957 |

Honesty note: labels derive from the engine-pinned golden expectations
(regression truth), not from independent human annotation; the pairs are
in-sample for the same corpus R2 scores. 0.75 is the shipped
CONFIDENCE_AUTO_ACCEPT.
