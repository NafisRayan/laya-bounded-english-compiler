"""Deployer error taxonomy (Developer Spec.md §9.1, §9.3)."""

import pytest

from compiler.deployer.errors import (
    RETRYABLE_CATEGORIES,
    MigrationError,
    apply_remediation,
    classify_error,
    remediation_options,
)


@pytest.mark.parametrize("message,expected", [
    ('relation "listings" already exists', "duplicate_object"),
    ('policy "x" already exists', "rls_conflict"),
    ('foreign key constraint "bookings_listing_id_fkey"', "fk_ordering"),
    ('extension "pgcrypto" does not exist', "extension_missing"),
    ("HTTP 503", "transient"),
    ("connection timeout after 30s", "transient"),
    ("permission denied to create extension", "permission_denied"),
    ("exceeded max number of tables for plan", "quota_exceeded"),
    ('syntax error at or near "XYZ"', "sql_syntax"),
    ("something entirely novel happened", "unknown"),
])
def test_classify_error_matches_spec_rows(message, expected):
    assert classify_error(message) == expected


def test_rls_conflict_takes_precedence_over_duplicate():
    assert classify_error('policy "p" already exists') == "rls_conflict"


def test_retryable_categories_match_spec():
    assert RETRYABLE_CATEGORIES == {
        "transient",
        "duplicate_object",
        "rls_conflict",
        "fk_ordering",
        "extension_missing",
    }


@pytest.mark.parametrize("category,expected_count", [
    ("fk_ordering", 3),
    ("quota_exceeded", 3),
    ("extension_missing", 2),
    ("duplicate_object", 1),
    ("rls_conflict", 1),
    ("permission_denied", 0),
    ("sql_syntax", 0),
    ("unknown", 0),
])
def test_remediation_options_shape(category, expected_count, marketplace_spec):
    options = remediation_options(category, marketplace_spec, RuntimeError("x"))
    assert len(options) == expected_count
    for option in options:
        assert set(option) == {"label", "value"}


def test_apply_remediation_remove_features_drops_optional_features(marketplace_spec):
    spec = marketplace_spec.model_copy(update={
        "features": {**marketplace_spec.features, "favorites": True, "reviews": True},
    })
    result = apply_remediation(spec, "quota_exceeded", "remove_features")
    assert "favorites" not in result.features
    assert "reviews" not in result.features
    assert result.decisions[-1].capability_id == "deploy.remediation.quota_exceeded"
    assert result.decisions[-1].value == "remove_features"


def test_apply_remediation_records_other_answers_without_feature_changes(marketplace_spec):
    before = dict(marketplace_spec.features)
    result = apply_remediation(marketplace_spec, "fk_ordering", "reorder")
    assert result.features == before
    assert result.decisions[-1].value == "reorder"


def test_migration_error_is_an_exception():
    assert issubclass(MigrationError, Exception)
