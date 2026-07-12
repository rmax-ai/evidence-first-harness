"""Common test fixtures for Evidence-First Harness."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def temp_repo() -> Path:
    """Create a temporary directory simulating a git repository."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo = Path(tmpdir)
        (repo / ".git").mkdir()
        (repo / "src").mkdir()
        (repo / "tests").mkdir()
        yield repo


@pytest.fixture
def sample_policy_yaml() -> str:
    """Return a minimal valid policy YAML."""
    return """
version: "1.0"
tiers:
  3:
    description: "Low risk"
    required:
      - formatting
      - lint
    minimum:
      test_pass_rate: 1.0
      impact_confidence: 0.70
    approval: []
  2:
    description: "Medium risk"
    required:
      - formatting
      - lint
      - type_check
      - targeted_tests
    minimum:
      test_pass_rate: 1.0
      mutation_score: 0.70
      impact_confidence: 0.80
    approval:
      - code_owner
  1:
    description: "High risk"
    required:
      - formatting
      - lint
      - type_check
      - targeted_tests
      - integration_tests
    minimum:
      test_pass_rate: 1.0
      mutation_score: 0.80
      impact_confidence: 0.90
    approval:
      - code_owner
      - security_owner
"""
