"""Determinism and coverage guarantees for the annotation splits (§4.4)."""

from tests.experiments.runner import iter_cases
from tests.experiments.splits import (
    SEED,
    build_splits,
    load_splits,
    write_splits,
)


def test_splits_cover_every_case_exactly_once():
    splits = write_splits()
    names = {name for name, _ in iter_cases()}
    assert set(splits["golden"]) | set(splits["held_out"]) == names
    assert set(splits["golden"]).isdisjoint(splits["held_out"])


def test_splits_are_stable_for_the_seed():
    names = [name for name, _ in iter_cases()]
    again = build_splits(names, seed=SEED)
    assert again == load_splits()


def test_held_out_fraction_holds():
    splits = load_splits()
    total = len(splits["golden"]) + len(splits["held_out"])
    assert len(splits["held_out"]) == round(total * 0.3)
