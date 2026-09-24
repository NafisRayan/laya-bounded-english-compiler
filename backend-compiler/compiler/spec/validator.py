"""Validator implementing Developer Spec.md §6.1 (checks) and §6.2 (logic).

§6.2 assumes dict-shaped constraint/parameter objects; the ontology loader
parses them into pydantic models, so attribute access replaces subscript
access. Semantics are otherwise unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from compiler.ontology.loader import ConstraintCond, ConstraintDef, Ontology
from compiler.spec.derive import derive_buckets, derive_edge_functions, derive_entities
from compiler.spec.models import BackendSpec

__all__ = [
    "BucketDerivationError",
    "CircularDependency",
    "EdgeFunctionDerivationError",
    "EntityDerivationError",
    "InvalidParameterLength",
    "InvalidParameterValue",
    "MissingDependency",
    "RlsEntityMismatch",
    "UndefinedRole",
    "UnknownFeature",
    "UnknownParameter",
    "ValidationError",
    "ValidationIssue",
    "ValidationResult",
    "ValidationWarning",
    "validate",
]


class ValidationIssue(Exception):
    """Base class for every validator error/warning."""


class EntityDerivationError(ValidationIssue):
    def __init__(self, expected: list[str], actual: list[str]) -> None:
        self.expected = expected
        self.actual = actual
        super().__init__(f"entities do not match derivation: derived={expected} actual={actual}")


class BucketDerivationError(ValidationIssue):
    def __init__(self, expected, actual) -> None:
        self.expected = expected
        self.actual = actual
        super().__init__(
            "buckets do not match derivation: derived="
            f"{[b.name for b in expected]} actual={[b.name for b in actual]}"
        )


class EdgeFunctionDerivationError(ValidationIssue):
    def __init__(self, expected: list[str], actual: list[str]) -> None:
        self.expected = expected
        self.actual = actual
        super().__init__(f"edge_functions do not match derivation: derived={expected} actual={actual}")


class ValidationError(ValidationIssue):
    def __init__(self, constraint: ConstraintDef) -> None:
        self.constraint = constraint
        super().__init__(constraint.message or constraint.reason or constraint.type)


class ValidationWarning(ValidationIssue):
    def __init__(self, constraint: ConstraintDef) -> None:
        self.constraint = constraint
        super().__init__(constraint.message or constraint.reason or constraint.type)


class MissingDependency(ValidationIssue):
    def __init__(self, feature_id: str, missing: str) -> None:
        self.feature_id = feature_id
        self.missing = missing
        super().__init__(f"feature {feature_id!r} requires {missing!r} which is not enabled")


class UnknownFeature(ValidationIssue):
    def __init__(self, feature_id: str) -> None:
        self.feature_id = feature_id
        super().__init__(f"feature {feature_id!r} is not defined in the ontology")


class UnknownParameter(ValidationIssue):
    def __init__(self, key: str) -> None:
        self.key = key
        super().__init__(f"parameter {key!r} is not defined in the ontology")


class InvalidParameterValue(ValidationIssue):
    def __init__(self, key: str, value: object) -> None:
        self.key = key
        self.value = value
        super().__init__(f"parameter {key!r} has invalid value {value!r}")


class InvalidParameterLength(ValidationIssue):
    def __init__(self, key: str, length: int, min_len: int | None, max_len: int | None) -> None:
        self.key = key
        self.length = length
        self.min = min_len
        self.max = max_len
        super().__init__(f"parameter {key!r} has length {length}, expected min={min_len} max={max_len}")


class UndefinedRole(ValidationIssue):
    def __init__(self, role: str) -> None:
        self.role = role
        super().__init__(f"role {role!r} is referenced but not defined in the ontology")


class RlsEntityMismatch(ValidationIssue):
    def __init__(self, entity: str) -> None:
        self.entity = entity
        super().__init__(f"RLS override references entity {entity!r} which is not in spec.entities")


class CircularDependency(ValidationIssue):
    def __init__(self, cycle: list[str]) -> None:
        self.cycle = cycle
        super().__init__(f"circular feature dependency: {' -> '.join(cycle)}")


@dataclass
class ValidationResult:
    ok: bool
    errors: list[ValidationIssue] = field(default_factory=list)
    warnings: list[ValidationIssue] = field(default_factory=list)


def constraint_holds(cond: ConstraintCond, features: dict[str, bool],
                     parameters: dict[str, Any]) -> bool:
    """True when a constraint condition holds against feature/parameter state."""
    feature_id = cond.feature
    if cond.parameter is None:
        return features.get(feature_id) == cond.value
    if not features.get(feature_id):
        return False
    key = f"{feature_id}.{cond.parameter}"
    if key not in parameters:
        return False
    actual = parameters[key]
    if cond.contains is not None:
        return isinstance(actual, list) and cond.contains in actual
    return actual == cond.value


def _constraint_matches(constraint: ConstraintDef, spec: BackendSpec) -> bool:
    return constraint_holds(constraint.if_, spec.features, spec.parameters)


def _detect_cycle(enabled: dict[str, bool], ontology: Ontology) -> list[str] | None:
    """DFS over `requires` edges of enabled features; returns a cycle path."""
    graph = {
        fid: list(ontology.features[fid].requires)
        for fid, on in enabled.items()
        if on and fid in ontology.features
    }
    state: dict[str, int] = {}  # 0=unvisited 1=on-stack 2=done
    stack: list[str] = []

    def visit(node: str) -> list[str] | None:
        state[node] = 1
        stack.append(node)
        for nxt in graph.get(node, []):
            if nxt not in graph:
                continue
            if state.get(nxt) == 1:
                return stack[stack.index(nxt):] + [nxt]
            if state.get(nxt, 0) == 0:
                found = visit(nxt)
                if found:
                    return found
        stack.pop()
        state[node] = 2
        return None

    for node in graph:
        if state.get(node, 0) == 0:
            cycle = visit(node)
            if cycle:
                return cycle
    return None


def validate(spec: BackendSpec, ontology: Ontology) -> ValidationResult:
    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []

    # --- derivation invariants (§6.1) ---
    expected_entities = derive_entities(spec, ontology)
    if sorted(spec.entities) != expected_entities:
        errors.append(EntityDerivationError(expected_entities, spec.entities))

    expected_buckets = derive_buckets(spec)
    if sorted(b.name for b in spec.buckets) != sorted(b.name for b in expected_buckets):
        errors.append(BucketDerivationError(expected_buckets, spec.buckets))

    expected_fns = derive_edge_functions(spec, ontology)
    if sorted(spec.edge_functions) != expected_fns:
        errors.append(EdgeFunctionDerivationError(expected_fns, spec.edge_functions))

    # --- ontology constraints (§2.5 / §6.1) ---
    for constraint in ontology.constraints:
        if not _constraint_matches(constraint, spec):
            continue
        if constraint.type == "contradicts" and constraint.severity == "hard":
            errors.append(ValidationError(constraint))
        elif constraint.type == "weakens":
            warnings.append(ValidationWarning(constraint))
        elif constraint.type == "requires":
            then = constraint.then
            if then is None:
                continue
            if then.parameter is not None:
                key = f"{then.feature}.{then.parameter}"
                if spec.parameters.get(key) != then.value:
                    errors.append(ValidationError(constraint))
            else:
                if spec.features.get(then.feature) != then.value:
                    errors.append(ValidationError(constraint))

    # --- feature requires ---
    for feature_id, enabled in spec.features.items():
        if not enabled:
            continue
        if feature_id not in ontology.features:
            errors.append(UnknownFeature(feature_id))
            continue
        for req in ontology.features[feature_id].requires:
            if not spec.features.get(req, False):
                errors.append(MissingDependency(feature_id, req))

    # --- circular feature dependencies ---
    cycle = _detect_cycle(spec.features, ontology)
    if cycle is not None:
        errors.append(CircularDependency(cycle))

    # --- roles referenced but not defined (§6.1) ---
    for role in spec.roles:
        if role not in ontology.roles:
            errors.append(UndefinedRole(role))

    # --- RLS override entity not in spec.entities (§6.1) ---
    for entity in spec.rls_overrides:
        if entity not in spec.entities:
            errors.append(RlsEntityMismatch(entity))

    # --- parameter values / lengths (§6.1) ---
    for key, value in spec.parameters.items():
        if "." not in key:
            errors.append(UnknownParameter(key))
            continue
        feature_id, param_id = key.split(".", 1)
        feature = ontology.features.get(feature_id)
        if not feature or param_id not in feature.parameters:
            errors.append(UnknownParameter(key))
            continue
        param = feature.parameters[param_id]
        ptype = param.type

        if ptype == "choice":
            if value not in param.options:
                errors.append(InvalidParameterValue(key, value))

        elif ptype == "list[choice]":
            if not isinstance(value, list):
                errors.append(InvalidParameterValue(key, value))
            else:
                for item in value:
                    if item not in param.options:
                        errors.append(InvalidParameterValue(key, item))

        elif ptype == "list[string]":
            if not isinstance(value, list):
                errors.append(InvalidParameterValue(key, value))
            else:
                if param.min is not None and len(value) < param.min:
                    errors.append(InvalidParameterLength(key, len(value), param.min, param.max))
                if param.max is not None and len(value) > param.max:
                    errors.append(InvalidParameterLength(key, len(value), param.min, param.max))
                for item in value:
                    if not isinstance(item, str) or not item.strip():
                        errors.append(InvalidParameterValue(key, item))

    return ValidationResult(ok=len(errors) == 0, errors=errors, warnings=warnings)