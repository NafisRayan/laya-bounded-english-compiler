"""Confidence calibration (Developer Spec.md §3.5).

Laya ships calibrated: `answer_confidence` is consumed directly. An extra
temperature is only applied if measured ECE was >= 0.1 on the golden set
(persisted per checkpoint in ``calibration.json``).
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Sequence

__all__ = [
    "CALIBRATION_FILE",
    "apply_temperature",
    "expected_calibration_error",
    "fit_temperature",
    "load_calibration",
]

CALIBRATION_FILE = (
    Path(__file__).parent.parent / "ontology" / "versions" / "v1" / "calibration.json"
)


def load_calibration(path: str | Path | None = None) -> dict:
    p = Path(path) if path is not None else CALIBRATION_FILE
    with p.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def apply_temperature(raw: float, temperature: float) -> float:
    clipped = min(max(raw, 1e-6), 1 - 1e-6)
    logit = math.log(clipped / (1 - clipped))
    z = logit / temperature
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    ez = math.exp(z)
    return ez / (1.0 + ez)


def expected_calibration_error(
    probs: Sequence[float], labels: Sequence[int], n_bins: int = 10
) -> float:
    """ECE over equal-width bins (§18.17): Σ bin_share × |mean conf − mean acc|.

    Bins are [lo, hi) from linspace(0, 1, n_bins + 1); the last bin is
    [lo, 1.0] so a probability of exactly 1.0 is counted.
    """
    if not probs:
        raise ValueError("probs must not be empty")
    if len(probs) != len(labels):
        raise ValueError("probs and labels must have equal length")
    edges = [i / n_bins for i in range(n_bins + 1)]
    total = 0.0
    for i in range(n_bins):
        lo, hi = edges[i], edges[i + 1]
        if i == n_bins - 1:
            idx = [j for j, p in enumerate(probs) if lo <= p <= hi]
        else:
            idx = [j for j, p in enumerate(probs) if lo <= p < hi]
        if not idx:
            continue
        mean_p = sum(probs[j] for j in idx) / len(idx)
        mean_l = sum(labels[j] for j in idx) / len(idx)
        total += (len(idx) / len(probs)) * abs(mean_p - mean_l)
    return total


def fit_temperature(
    probs: Sequence[float], labels: Sequence[int]
) -> float:
    """Grid-search T ∈ 0.01…10.00 (step 0.01) minimizing the ECE of the
    temperature-scaled probs (§3.5 step 5). Ties resolve to the smaller T,
    and a T of 1.0 (pass-through) is never replaced by an equal-ECE T.

    The criterion is ECE because that is the §3.5 gate the fit must move.
    """
    best_t = 1.0
    best_ece = expected_calibration_error(
        [apply_temperature(p, best_t) for p in probs], labels)
    for i in range(1, 1001):
        t = i / 100
        e = expected_calibration_error(
            [apply_temperature(p, t) for p in probs], labels)
        if e < best_ece:
            best_t, best_ece = t, e
    return best_t
