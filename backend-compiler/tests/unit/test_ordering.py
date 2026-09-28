"""Topological ordering of fragments (Developer Spec.md §7.4, rule 5)."""

import pytest

from compiler.generator.fragments import load
from compiler.generator.models import CompositionError, Fragment
from compiler.generator.ordering import topo_sort


def _fragment(fragment_id, requires=(), fragment_type="table"):
    return Fragment(
        id=fragment_id, type=fragment_type, requires=list(requires), sql=f"-- {fragment_id}"
    )


def test_topo_sort_respects_requires():
    listings = load("table_listings")
    bookings = load("table_bookings")
    assert bookings.requires == ["table_listings"]

    ordered = topo_sort([bookings, listings], key="requires")

    assert ordered.index(listings) < ordered.index(bookings)


def test_topo_sort_cycle_raises():
    a = _fragment("a", requires=["b"])
    b = _fragment("b", requires=["a"])

    with pytest.raises(CompositionError) as excinfo:
        topo_sort([a, b], key="requires")

    assert "ordering cycle" in str(excinfo.value)
    assert {"a", "b"} <= set(excinfo.value.issues[0].split())


def test_topo_sort_external_requires_ignored():
    # `users` is Supabase-managed: no fragment is ever emitted for it, so
    # the requirement must not stall the sort.
    orphan = _fragment("orphan", requires=["users"])

    assert topo_sort([orphan], key="requires") == [orphan]


def test_topo_sort_stable():
    first = _fragment("first", fragment_type="bucket")
    second = _fragment("second", fragment_type="realtime")
    third = _fragment("third", fragment_type="function")

    assert topo_sort([first, second, third], key="requires") == [first, second, third]
    assert topo_sort([third, second, first], key="requires") == [third, second, first]


def test_topo_sort_empty():
    assert topo_sort([], key="requires") == []


def test_topo_sort_honours_key_argument():
    a = _fragment("a", fragment_type="bucket")
    b = _fragment("b", fragment_type="bucket")
    # `provides` is just another list-valued field the sort can read: `b`
    # requires "a", so `a` has to be emitted first.
    a_with_provides = a.model_copy(update={"provides": ["z"]})
    b_with_provides = b.model_copy(update={"provides": ["a"]})

    ordered = topo_sort([b_with_provides, a_with_provides], key="provides")

    assert ordered == [a_with_provides, b_with_provides]


def test_topo_sort_is_deterministic():
    fragments = [load(f"table_{entity}") for entity in ("messages", "bookings", "listings", "profiles")]
    first = [fragment.id for fragment in topo_sort(fragments, key="requires")]
    second = [fragment.id for fragment in topo_sort(list(reversed(fragments)), key="requires")]

    # The dependency edges are identical in both directions, so the result
    # must be too -- only genuinely independent fragments may swap.
    assert set(first) == set(second)
    assert first.index("table_listings") < first.index("table_bookings") < first.index("table_messages")
