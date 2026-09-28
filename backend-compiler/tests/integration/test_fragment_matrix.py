# tests/integration/test_fragment_matrix.py
import itertools

import pytest
import psycopg

from compiler.generator.fragments import list_all_fragments
from compiler.generator.composer import compose


pytestmark = pytest.mark.slow

ALL_FRAGMENTS = list_all_fragments()


@pytest.mark.parametrize("pair", list(itertools.combinations(ALL_FRAGMENTS, 2)))
def test_pair_applies(pair, ontology, fresh_db):
    frag_a, frag_b = pair
    spec = _spec_for_fragments([frag_a, frag_b])
    for m in compose(spec, ontology):
        with psycopg.connect(fresh_db, autocommit=True) as conn:
            conn.execute(m.sql)


def _spec_for_fragments(fragment_ids):
    from compiler.generator.fragment_spec_map import spec_for
    return spec_for(fragment_ids)