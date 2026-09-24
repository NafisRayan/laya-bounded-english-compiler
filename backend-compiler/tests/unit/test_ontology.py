"""Ontology loader + senior-bundle parity guards (stability of v1 data)."""

from pathlib import Path

from compiler.ontology.loader import Ontology, load_ontology

PROJECT_ROOT = Path(__file__).parents[2]
V1_DIR = PROJECT_ROOT / "compiler" / "ontology" / "versions" / "v1"


def test_load_versioned_directory():
    ontology = load_ontology(V1_DIR)
    assert isinstance(ontology, Ontology)
    assert ontology.version == 1
    assert "authentication" in ontology.features
    assert "listings" in ontology.entities
    assert "owner" in ontology.roles


def test_fixture_bundle_matches_versioned_directory(ontology):
    from_versioned = load_ontology(V1_DIR)
    assert ontology.version == from_versioned.version
    assert set(ontology.features) == set(from_versioned.features)
    for fid in ontology.features:
        assert ontology.features[fid].requires == from_versioned.features[fid].requires
        assert ontology.features[fid].activates_entities == from_versioned.features[fid].activates_entities
        assert ontology.features[fid].activates_edge_functions == from_versioned.features[fid].activates_edge_functions
    assert list(ontology.roles) == list(from_versioned.roles)
    assert list(ontology.rls_patterns) == list(from_versioned.rls_patterns)
    assert len(ontology.constraints) == len(from_versioned.constraints)


def test_ontology_items_union_of_features_and_entities(ontology):
    assert "listings" in ontology.items
    assert "messaging" in ontology.items
    assert ontology.items == sorted(set(ontology.features) | set(ontology.entities))


def test_realtime_feature_activates_notifications(ontology):
    assert "notifications" in ontology.features["realtime"].activates_entities
    assert ontology.features["realtime"].parameters["channels"].options == [
        "messages", "notifications", "bookings"]