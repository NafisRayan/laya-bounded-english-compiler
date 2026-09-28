"""Composition engine models (Developer Spec.md §7.2, §7.3).

Three objects only:

- `Fragment`: the unit of composition. Its YAML interface is §7.2's
  (`id`, `type`, `requires`, `provides`, `sql`).
- `Migration`: one emitted `.sql` file, named `{ordinal}_{fragment_id}.sql`.
- `CompositionError`: every composition failure (unknown fragment, ordering
  cycle, conflict) is reported as a list of issues so callers get every
  problem in one pass instead of only the first.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["CompositionError", "Fragment", "FragmentType", "Migration"]


# Developer Spec.md §7.1 -- the fragment taxonomy.
FragmentType = Literal[
    "table",
    "rls",
    "trigger",
    "function",
    "bucket",
    "realtime",
    "edge_function",
]


class Migration(BaseModel):
    """One emitted migration file: name plus SQL body."""

    filename: str
    sql: str


class Fragment(BaseModel):
    """A composable SQL fragment (Developer Spec.md §7.2)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    type: FragmentType
    requires: list[str] = Field(default_factory=list)
    provides: list[str] = Field(default_factory=list)
    sql: str


class CompositionError(Exception):
    """One or more composition issues.

    Accepts a single message or a list of issues; `str()` renders them
    joined so the exception stays readable in tracebacks and in
    `pytest.raises(match=...)` assertions.
    """

    def __init__(self, issues: list[str] | str) -> None:
        self.issues: list[str] = [issues] if isinstance(issues, str) else list(issues)
        super().__init__("; ".join(self.issues))

    def __str__(self) -> str:
        return "; ".join(self.issues)
