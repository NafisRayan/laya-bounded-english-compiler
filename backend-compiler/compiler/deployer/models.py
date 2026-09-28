"""Deployment result model (Developer Spec.md §8.8, §9.2)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

__all__ = ["DeployResult"]


class DeployResult(BaseModel):
    """Outcome of a deployment attempt.

    `success=False` carries the triggering `error`, its §9.1 `category`
    (the last one seen when attempts run out), and the `ref` so a reused
    project can be inspected or torn down.
    """

    success: bool
    ref: str | None = None
    error: Any = None
    category: str | None = None
