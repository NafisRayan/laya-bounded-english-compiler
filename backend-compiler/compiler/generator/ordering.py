"""Dependency ordering for fragments (Developer Spec.md §7.4, rule 5).

Stable Kahn's algorithm over `Fragment.requires` (the default key; the
argument exists for symmetry with the spec's `topo_sort(..., key=...)`).
Two rules matter in practice:

- a `requires` id that is not among the fragments being ordered is
  *external* (e.g. a table fragment that references Supabase-managed
  `users`) and is ignored -- it is never going to be emitted;
- independent fragments keep their input order, so re-composing an
  unchanged spec produces byte-identical migrations.
"""

from __future__ import annotations

from collections.abc import Sequence

from compiler.generator.models import CompositionError, Fragment

__all__ = ["topo_sort"]


def topo_sort(fragments: Sequence[Fragment], key: str = "requires") -> list[Fragment]:
    """Order fragments so every `requires` id precedes its dependent.

    Raises `CompositionError` when the requirement graph has a cycle.
    """
    positions = {fragment.id: index for index, fragment in enumerate(fragments)}
    # Nodes are positions, not ids, so a duplicated id (reported as a
    # conflict by `detect_conflicts`) still sorts deterministically here.
    dependencies: list[set[int]] = []
    for index, fragment in enumerate(fragments):
        dependencies.append({
            positions[requirement]
            for requirement in (getattr(fragment, key) or [])
            if requirement in positions and positions[requirement] != index
        })

    ordered: list[Fragment] = []
    emitted: set[int] = set()
    pending = list(range(len(fragments)))
    while pending:
        progressed = False
        for index in list(pending):
            if dependencies[index] <= emitted:
                ordered.append(fragments[index])
                emitted.add(index)
                pending.remove(index)
                progressed = True
        if pending and not progressed:
            chain = _find_cycle(fragments, dependencies, pending)
            raise CompositionError([f"ordering cycle: {' -> '.join(chain)}"])

    return ordered


def _find_cycle(
    fragments: Sequence[Fragment], dependencies: list[set[int]], pending: list[int]
) -> list[str]:
    """Return one dependency cycle among the stalled nodes, as fragment ids."""
    remaining = set(pending)
    visited: set[int] = set()
    on_stack: list[int] = []

    def visit(node: int) -> list[str] | None:
        visited.add(node)
        on_stack.append(node)
        for nxt in sorted(dependencies[node] & remaining):
            if nxt in on_stack:
                start = on_stack.index(nxt)
                return [fragments[i].id for i in on_stack[start:]] + [fragments[nxt].id]
            if nxt not in visited:
                found = visit(nxt)
                if found:
                    return found
        on_stack.pop()
        return None

    for node in sorted(pending):
        if node not in visited:
            found = visit(node)
            if found:
                return found
    # Unreachable for a stalled Kahn pass, but keep the report informative.
    return [fragments[i].id for i in sorted(remaining)]
