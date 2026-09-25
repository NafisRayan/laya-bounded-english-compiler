"""Known-answer tests for the ECE/temperature math (Developer Spec.md §3.5, §18.17)."""

import pytest

from compiler.interpreter.calibration import (
    apply_temperature,
    expected_calibration_error,
    fit_temperature,
    load_calibration,
)


def test_ece_perfectly_calibrated_is_zero():
    # One bin, mean confidence == mean accuracy.
    assert expected_calibration_error([0.5, 0.5], [1, 0]) == 0.0


def test_ece_hand_computed_single_bin():
    # All four land in [0.8, 0.9): |mean conf 0.8 − mean acc 0.25| = 0.55.
    assert expected_calibration_error([0.8, 0.8, 0.8, 0.8], [1, 0, 0, 0]) == pytest.approx(0.55)


def test_ece_weights_bins_by_share():
    # Bin [0.5,0.6): |0.5 − 1.0| = 0.5 at share 0.5 → 0.25
    # Bin [0.9,1.0]: |0.9 − 0.0| = 0.9 at share 0.5 → 0.45; total 0.70.
    assert expected_calibration_error([0.5, 0.9], [1, 0]) == pytest.approx(0.70)


def test_ece_last_bin_includes_one():
    assert expected_calibration_error([1.0], [0]) == pytest.approx(1.0)


def test_fit_temperature_reduces_ece_on_overconfident_set():
    probs = [0.9, 0.9, 0.9, 0.9]
    labels = [0, 0, 0, 0]
    before = expected_calibration_error(probs, labels)
    t = fit_temperature(probs, labels)
    after = expected_calibration_error([apply_temperature(p, t) for p in probs], labels)
    assert after < before


def test_apply_temperature_half_is_identity():
    # logit(0.5) == 0, so any temperature leaves it at 0.5.
    assert apply_temperature(0.5, 3.7) == pytest.approx(0.5)


def test_apply_temperature_clips_extremes():
    assert apply_temperature(0.0, 1.0) == pytest.approx(1e-6)
    assert apply_temperature(1.0, 1.0) == pytest.approx(1 - 1e-6)


def test_apply_temperature_low_side_is_overflow_safe():
    # exp underflows to 0.0 instead of raising OverflowError (stable sigmoid).
    assert apply_temperature(1e-6, 0.01) == 0.0


def test_load_calibration_v1_english_is_passthrough():
    cal = load_calibration()
    assert cal["english"]["temperature"] == 1.0
    assert cal["english"]["needs_fit"] is False
