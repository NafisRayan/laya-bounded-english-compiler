"""Fragment composition engine (Developer Spec.md §7).

    recompute_spec(spec, ontology) -> compose(spec, ontology) -> list[Migration]

Fragments are SQL units with declared dependencies; `compose` selects,
orders, conflict-checks and renders them into migration files.
"""

from compiler.generator.composer import compose, detect_conflicts, render
from compiler.generator.fragments import list_all_fragments, load, load_all
from compiler.generator.models import CompositionError, Fragment, Migration
from compiler.generator.ordering import topo_sort

__all__ = [
    "CompositionError",
    "Fragment",
    "Migration",
    "compose",
    "detect_conflicts",
    "list_all_fragments",
    "load",
    "load_all",
    "render",
    "topo_sort",
]
