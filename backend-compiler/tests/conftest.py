"""Shared fixtures for all tests (Developer Spec.md §18.2).

`ontology` loads the merged bundle fixture exactly as the spec specifies;
it is kept in parity with ``compiler/ontology/versions/v1`` by
``tests/unit/test_ontology.py``.
"""

from pathlib import Path

import pytest

from compiler.ontology.loader import Ontology, load_ontology
from compiler.spec.derive import recompute_spec
from compiler.spec.models import BackendSpec, Decision

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def ontology() -> Ontology:
    return load_ontology(FIXTURES / "ontology.yaml")


@pytest.fixture
def minimal_spec(ontology) -> BackendSpec:
    spec = BackendSpec(
        version="1.0", ontology_version=1, created_at="2025-01-01T00:00:00Z",
        features={"authentication": True},
        parameters={"authentication.method": "email_password"},
        roles=["user"], rls_overrides={},
        entities=[], buckets=[], edge_functions=[],
        decisions=[
            Decision(capability_id="authentication.enabled",
                     value=True, confidence=0.95, source="user", evidence=None),
        ],
        defaulted=[], unsupported=[],
    )
    return recompute_spec(spec, ontology)


@pytest.fixture
def marketplace_spec(ontology) -> BackendSpec:
    spec = BackendSpec(
        version="1.0", ontology_version=1, created_at="2025-01-01T00:00:00Z",
        features={
            "authentication": True, "bookings": True, "messaging": True,
            "payments": True, "file_storage": True,
        },
        parameters={
            "authentication.method": "email_password",
            "bookings.mode": "owner_approval",
            "messaging.trigger_event": "after_request",
            "payments.provider": "stripe",
            "file_storage.bucket_purpose": "listings",
        },
        roles=["user", "owner", "renter"], rls_overrides={},
        entities=[], buckets=[], edge_functions=[],
        decisions=[], defaulted=[], unsupported=[],
    )
    return recompute_spec(spec, ontology)