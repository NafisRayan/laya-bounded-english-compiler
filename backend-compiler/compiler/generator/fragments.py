"""Fragment registry (Developer Spec.md §7.2).

Two sources, one registry:

- static fragments authored as YAML in `fragments/*.yaml`
  (`function_*`, `bucket_*`, `realtime_*`, `trigger_*`);
- fragments generated from the ontology -- `table_<entity>` from
  `table_fragments`, `rls_<entity>_<group>` from `rls`.

`list_all_fragments()` is the union of both, so the spec's §18.18 fragment
matrix can pair up every fragment the composer is able to emit.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from compiler.generator import table_fragments
from compiler.generator.models import CompositionError, Fragment
from compiler.generator.rls import build_rls_group, parse_rls_id, rls_group_fragments

__all__ = ["list_all_fragments", "load", "load_all"]

FRAGMENTS_DIR = Path(__file__).parent / "fragments"

TABLE_PREFIX = "table_"


@lru_cache(maxsize=1)
def _static_fragments() -> dict[str, Fragment]:
    registry: dict[str, Fragment] = {}
    for path in sorted(FRAGMENTS_DIR.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            raise CompositionError(f"malformed fragment YAML (not a mapping): {path.name}")
        fragment = Fragment(**data)
        if fragment.id in registry:
            raise CompositionError(f"duplicate static fragment id: {fragment.id}")
        registry[fragment.id] = fragment
    return registry


@lru_cache(maxsize=1)
def _generated_fragments() -> dict[str, Fragment]:
    generated: dict[str, Fragment] = {
        f"{TABLE_PREFIX}{entity}": table_fragments.build_table(entity)
        for entity in table_fragments.table_entity_ids()
    }
    for fragment in rls_group_fragments():
        generated[fragment.id] = fragment
    return generated


def load(fragment_id: str) -> Fragment:
    """Load one fragment by id (static YAML or generated from the ontology)."""
    static = _static_fragments()
    if fragment_id in static:
        return static[fragment_id]
    if fragment_id.startswith(TABLE_PREFIX):
        entity = fragment_id[len(TABLE_PREFIX):]
        if entity in set(table_fragments.table_entity_ids()):
            return table_fragments.build_table(entity)
    else:
        parsed = parse_rls_id(fragment_id)
        if parsed is not None:
            return build_rls_group(*parsed)
    raise CompositionError(f"unknown fragment: {fragment_id}")


@lru_cache(maxsize=1)
def _all_fragments() -> tuple[Fragment, ...]:
    fragments = list(_static_fragments().values()) + list(_generated_fragments().values())
    return tuple(sorted(fragments, key=lambda fragment: fragment.id))


def load_all() -> list[Fragment]:
    """Every fragment, static and generated, sorted by id."""
    return list(_all_fragments())


@lru_cache(maxsize=1)
def _all_fragment_ids() -> tuple[str, ...]:
    return tuple(fragment.id for fragment in _all_fragments())


def list_all_fragments() -> list[str]:
    """Every fragment id, static and generated (sorted).

    Developer Spec.md §18.18:2974 drives the pairwise matrix off this list.
    """
    return list(_all_fragment_ids())
