"""Supabase deployer (Developer Spec.md §8, §9)."""

from compiler.deployer.deployer import (
    apply_migrations,
    deploy_spec,
    deploy_with_remediation,
    link_project,
    present_mcq,
)
from compiler.deployer.errors import (
    MigrationError,
    apply_remediation,
    classify_error,
    remediation_options,
)
from compiler.deployer.models import DeployResult

__all__ = [
    "DeployResult",
    "MigrationError",
    "apply_migrations",
    "apply_remediation",
    "classify_error",
    "deploy_spec",
    "deploy_with_remediation",
    "link_project",
    "present_mcq",
    "remediation_options",
]
