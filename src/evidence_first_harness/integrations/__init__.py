"""Integrations — GitHub Checks API, PR management."""

from evidence_first_harness.integrations.github import (
    CheckAnnotation,
    CheckRunResult,
    GitHubIntegration,
)

__all__ = ["GitHubIntegration", "CheckRunResult", "CheckAnnotation"]
