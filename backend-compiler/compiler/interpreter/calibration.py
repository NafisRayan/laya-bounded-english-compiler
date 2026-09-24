"""Confidence calibration (Developer Spec.md §3.5).

Laya ships calibrated: `answer_confidence` is consumed directly. An extra
temperature is only applied if measured ECE was >= 0.1 on the golden set
(persisted per checkpoint in ``calibration.json``).
"""

from __future__ import annotations

import json
import math
from pathlib import Path

__all__ = ["CALIBRATION_FILE", "apply_temperature", "load_calibration"]

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
    return 1.0 / (1.0 + math.exp(-z))