"""ECE measurement gates (Developer Spec.md §18.17, §3.5; design:
docs/superpowers/specs/2026-09-25-ece-calibration-design.md).

`calibration_set.json` holds 500 MEASURED (answer_confidence, label) pairs:
real `laya` 0.3.20, pinned `english` checkpoint, one pair per golden-case
feature item (regenerate with
`python -m tests.experiments.run_calibration`). `miscalibrated_set.json`
stays synthetic on purpose: it demos the fit mechanics on a set that is
deliberately wrong, which a well-calibrated real set cannot provide.
"""

import json
from pathlib import Path

from compiler.interpreter.calibration import (
    apply_temperature,
    expected_calibration_error,
    fit_temperature,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "golden_calibration"


def _load(name):
    data = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    probs = [d["answer_confidence"] for d in data]
    labels = [d["label"] for d in data]
    return probs, labels


def test_ece_on_shipped_answer_confidence_is_acceptable():
    probs, labels = _load("calibration_set.json")
    ece = expected_calibration_error(probs, labels, n_bins=10)
    assert ece < 0.1, (
        f"ECE on shipped answer_confidence is {ece:.3f}, which exceeds the "
        f"0.1 threshold. See §3.5 for the fitting procedure."
    )


def test_fit_temperature_improves_miscalibrated_set():
    probs, labels = _load("miscalibrated_set.json")
    before = expected_calibration_error(probs, labels, n_bins=10)
    assert before >= 0.1, "miscalibrated_set.json is supposed to be miscalibrated"

    t = fit_temperature(probs, labels)
    after = expected_calibration_error(
        [apply_temperature(p, t) for p in probs], labels, n_bins=10)
    assert after < before, (
        f"temperature fit did not improve ECE: {before:.3f} -> {after:.3f}"
    )
