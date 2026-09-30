"""Deterministic golden/held-out splits for the annotation protocol (§4.4).

The 50 engine-pinned golden cases split into an annotation working set and a
held-out set with a fixed seed, so every run of the protocol (and every
future re-annotation) partitions identically. The split never changes what
the engine's regression suite runs — it only labels which cases count as
in-sample evidence and which are reserved for held-out claims.
"""

from __future__ import annotations

import random
from pathlib import Path

import yaml

from tests.experiments.runner import iter_cases

__all__ = ["SPLITS_PATH", "SEED", "build_splits", "write_splits", "load_splits"]

SPLITS_PATH = Path(__file__).parent.parent / "golden" / "splits.yaml"
SEED = 20260930
#: fraction of cases reserved as held-out (15 of 50)
HELD_OUT_FRACTION = 0.3


def build_splits(names: list[str], seed: int = SEED,
                 held_out_fraction: float = HELD_OUT_FRACTION) -> dict[str, list[str]]:
    ordered = sorted(names)
    rng = random.Random(seed)
    shuffled = ordered[:]
    rng.shuffle(shuffled)
    n_held = round(len(ordered) * held_out_fraction)
    return {
        "seed": seed,
        "held_out": sorted(shuffled[:n_held]),
        "golden": sorted(shuffled[n_held:]),
    }


def write_splits(path: Path | None = None, seed: int = SEED) -> dict[str, list[str]]:
    names = [name for name, _ in iter_cases()]
    splits = build_splits(names, seed=seed)
    target = path or SPLITS_PATH
    target.write_text(yaml.safe_dump(splits, sort_keys=True), encoding="utf-8")
    return splits


def load_splits(path: Path | None = None) -> dict[str, list[str]]:
    with (path or SPLITS_PATH).open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)
