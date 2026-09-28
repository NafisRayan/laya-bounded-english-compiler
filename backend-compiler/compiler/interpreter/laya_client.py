"""Laya client integration (Developer Spec.md §3.7).

CHECKPOINT pins the `english` checkpoint. The Router is constructed without
a models override so the library's default checkpoint resolution applies;
``predict_batch`` receives a list of ``{state, questions, model}`` dicts.
"""

from __future__ import annotations

import os

from compiler.interpreter.calibration import apply_temperature, load_calibration

__all__ = ["CHECKPOINT", "LayaClient"]

CHECKPOINT = "english"    # pinned; do not auto-route


class LayaClient:
    """
    Thin wrapper around the laya Router, pinned to the `english` checkpoint.

    The Router import is deferred to construction time so this module stays
    importable (and testable via MockLayaClient) on machines without the
    `laya` package or its downloaded weights.
    """

    def __init__(self, device: str | None = None):  # pragma: no cover - needs the laya package and its downloaded weights; tests exercise MockLayaClient instead
        self.device = device or os.environ.get("LAYA_DEVICE", "cpu")
        from laya import Router

        # No models override — the library default is english ->
        # ("convaiinnovations/laya", None). LRU caps at 2 loaded models,
        # irrelevant since we only use english.
        self.router = Router(device=self.device, preload=True)
        self.calibration = load_calibration()

    def predict(self, state: str, questions: dict) -> dict:
        """
        Call the Router with typed questions.

        Returns the library envelope unchanged:
            {
              "model":   "laya-rl-agent",
              "answers": { qid: { "type", "noul"|"choice", "confidence",
                                  "answer_confidence", "action": {...} }, ... },
              "usage":   {"input_tokens": ..., "output_tokens": ...},
              "routing": {"model": ..., "repo": ..., "reason": ...},
            }
        """
        return self.router.predict(state, questions, model=CHECKPOINT)

    def predict_batch(self, states: list[str], questions: dict) -> list[dict]:
        """
        Batched inference.

        Router.predict_batch takes a Sequence[Dict], where each item
        carries state/questions (and optionally model). There is no
        `model=` kwarg on predict_batch.
        """
        requests = [
            {"state": s, "questions": questions, "model": CHECKPOINT}
            for s in states
        ]
        return self.router.predict_batch(requests)

    def calibrated_confidence(self, answer: dict) -> float:
        """
        Return the calibrated confidence for an answer.

        Laya already calibrates via answer_confidence. We only apply
        an extra temperature if ECE measured >= 0.1 on the golden set.
        """
        raw = answer["answer_confidence"]
        T = self.calibration[CHECKPOINT]["temperature"]
        if T == 1.0:
            return raw
        return apply_temperature(raw, T)