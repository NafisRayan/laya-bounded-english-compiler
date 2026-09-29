"""Fidelity metrics for experiment runs (Developer Spec.md §4.3).

A golden case pins an ``expected_spec`` (features + optional parameters,
roles, entities, buckets, edge functions). We score a pipeline-produced
``BackendSpec`` against those labels:

- feature precision/recall/F1 over the *positive* class (feature enabled);
- silent omissions = gold-enabled features the run did not enable;
- hallucinations = features the run enabled that the gold set does not;
- per-dimension exact matches for parameters / roles / entities / buckets /
  edge functions (each only when the case pins that dimension);
- ``all_match`` = every pinned dimension matches and features are exact.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from compiler.spec.models import BackendSpec, BucketSpec

__all__ = ["CaseLabels", "RunMetrics", "extract_labels", "score"]


@dataclass
class CaseLabels:
    feature_map: dict[str, bool] = field(default_factory=dict)
    parameters: dict[str, Any] = field(default_factory=dict)
    roles: list[str] | None = None
    entities: list[str] | None = None
    buckets: list[dict[str, Any]] | None = None
    edge_functions: list[str] | None = None


@dataclass
class RunMetrics:
    case: str
    mechanisms: str
    mcq: bool
    persona: str

    gold_features: int = 0
    decided_features: int = 0
    true_positives: int = 0
    precision: float = 0.0
    recall: float = 0.0
    omissions: int = 0
    hallucinations: int = 0

    params_match: bool | None = None
    roles_match: bool | None = None
    entities_match: bool | None = None
    buckets_match: bool | None = None
    edges_match: bool | None = None
    all_match: bool = False

    mcq_count: int = 0
    ms: float = 0.0


def extract_labels(expected_spec: dict[str, Any]) -> CaseLabels:
    features = expected_spec.get("features")
    return CaseLabels(
        feature_map=dict(features) if isinstance(features, dict) else {},
        parameters=dict(expected_spec.get("parameters") or {}),
        roles=list(expected_spec["roles"]) if expected_spec.get("roles") is not None else None,
        entities=list(expected_spec["entities"]) if expected_spec.get("entities") is not None else None,
        buckets=list(expected_spec["buckets"]) if expected_spec.get("buckets") is not None else None,
        edge_functions=list(expected_spec["edge_functions"])
        if expected_spec.get("edge_functions") is not None else None,
    )


def _canon(items) -> list:
    if not items:
        return []
    if isinstance(items[0], BucketSpec):
        items = [b.model_dump() for b in items]
    return sorted(items, key=lambda x: _json_canon(x))


def _json_canon(x: Any) -> str:
    import json
    return json.dumps(x, sort_keys=True, default=str)


def _lists_equal(actual, expected: list[Any]) -> bool:
    if isinstance(actual, list) and actual and isinstance(actual[0], BucketSpec):
        actual = [b.model_dump() for b in actual]
    return _canon(actual) == _canon(expected)


def score(spec: BackendSpec, labels: CaseLabels, case: str = "",
          mechanisms: str = "ABC", mcq: bool = True,
          persona: str = "default") -> RunMetrics:
    gold_true = {f for f, v in labels.feature_map.items() if v}
    pred_true = {f for f, v in spec.features.items() if v}

    tp = len(pred_true & gold_true)
    if gold_true:
        precision = tp / len(pred_true) if pred_true else 0.0
        recall = tp / len(gold_true)
    else:
        # A case with no gold-enabled features (pure-negation case) is
        # correctly scored as 1.0 when the run also enabled nothing;
        # anything enabled is a hallucination.
        precision = 1.0 if not pred_true else 0.0
        recall = 1.0 if not pred_true else 0.0

    params_match: bool | None = None
    if labels.parameters:
        params_match = all(spec.parameters.get(k) == v
                           for k, v in labels.parameters.items())

    roles_match: bool | None = None
    if labels.roles is not None:
        roles_match = sorted(spec.roles) == sorted(labels.roles)

    entities_match: bool | None = None
    if labels.entities is not None:
        entities_match = _lists_equal(sorted(spec.entities), labels.entities)

    buckets_match: bool | None = None
    if labels.buckets is not None:
        buckets_match = _canon(spec.buckets) == _canon(labels.buckets)

    edges_match: bool | None = None
    if labels.edge_functions is not None:
        edges_match = _lists_equal(sorted(spec.edge_functions), labels.edge_functions)

    dimensions = [d for d in (params_match, roles_match, entities_match,
                              buckets_match, edges_match) if d is not None]
    all_match = (tp == len(gold_true) and tp == len(pred_true)
                 and all(dim is True for dim in dimensions))

    return RunMetrics(
        case=case, mechanisms=mechanisms, mcq=mcq, persona=persona,
        gold_features=len(gold_true), decided_features=len(pred_true),
        true_positives=tp, precision=precision, recall=recall,
        omissions=len(gold_true - pred_true),
        hallucinations=len(pred_true - gold_true),
        params_match=params_match, roles_match=roles_match,
        entities_match=entities_match, buckets_match=buckets_match,
        edges_match=edges_match, all_match=all_match,
    )