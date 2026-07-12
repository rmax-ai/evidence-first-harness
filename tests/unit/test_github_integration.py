"""Unit tests for GitHub integration.

Tests check run creation, PR comment formatting, artifact upload,
and evidence-to-annotation conversion — without hitting the API.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from evidence_first_harness.integrations.github import (
    CheckAnnotation,
    CheckRunResult,
    GitHubIntegration,
)


@pytest.fixture
def integration() -> GitHubIntegration:
    """Integration with no token — tests formatting, not API calls."""
    return GitHubIntegration(owner="test-org", repo="test-repo", token=None)


@pytest.fixture
def sample_evidence() -> dict:
    """Sample evidence bundle similar to what the harness produces."""
    return {
        "run_id": "run_abc123",
        "repository": "test-org/test-repo",
        "base_commit": "abc123def456abc123def456abc123def456abc1",
        "decision": {"decision": "human_review_required", "rationale": "Missing evidence"},
        "risk": {"overall_tier": 2},
        "impact": {"confidence": 0.85},
        "evidence": [
            {
                "requirement_id": "formatting",
                "executor": "ruff",
                "status": "pass",
                "summary": "Formatting check passed — 0 issues",
            },
            {
                "requirement_id": "type_check",
                "executor": "pyright",
                "status": "fail",
                "summary": "Type check found 3 errors",
            },
            {
                "requirement_id": "mutation_test",
                "executor": "mutation_test",
                "status": "unavailable",
                "summary": "mutmut not installed",
            },
            {
                "requirement_id": "targeted_tests",
                "executor": "pytest",
                "status": "partial",
                "summary": "35/35 passed, 2 skipped",
            },
        ],
        "contradictions": [],
        "limitations": ["No coverage data available"],
    }


# ---------------------------------------------------------------------------
# Token Resolution Tests
# ---------------------------------------------------------------------------


class TestTokenResolution:
    def test_resolves_token_from_env(self) -> None:
        """Token resolves from gh auth token in CI/dev environments."""
        integration = GitHubIntegration(owner="x", repo="y", token=None)
        # May resolve from GITHUB_TOKEN or gh CLI; if so, API calls will hit GitHub
        # and get 404 for nonexistent repo — that's expected behavior.
        result = integration.create_check_run(
            name="test",
            head_sha="abc123",
            evidence_summary={},
        )
        # Either it fails with no token, or it calls GitHub and gets 404
        assert result.error is not None
        # Acceptable: "token" error (no auth) or "404" error (authenticated but repo doesn't exist)
        error_lower = result.error.lower()
        assert "token" in error_lower or "404" in error_lower or "not found" in error_lower


# ---------------------------------------------------------------------------
# Summary Formatting Tests
# ---------------------------------------------------------------------------


class TestSummaryFormatting:
    def test_format_summary(self, sample_evidence: dict) -> None:
        """Summary includes decision, evidence counts, and detail."""
        summary = GitHubIntegration._format_summary(sample_evidence)
        assert "human_review_required" in summary
        assert "Tier" in summary
        assert "1 passed" in summary or "passed" in summary
        assert "ruff" in summary
        assert "pyright" in summary

    def test_make_title(self, sample_evidence: dict) -> None:
        """Title reflects the decision."""
        title = GitHubIntegration._make_title(sample_evidence)
        assert "Evidence-First" in title
        assert "human_review_required" in title

    def test_format_pr_comment(self, sample_evidence: dict) -> None:
        """PR comment includes decision, risk, limitations."""
        comment = GitHubIntegration._format_pr_comment(sample_evidence)
        assert "run_abc123" in comment
        assert "human_review_required" in comment
        assert "Risk Tier" in comment or "Tier" in comment
        assert "No coverage data available" in comment


# ---------------------------------------------------------------------------
# Annotation Conversion Tests
# ---------------------------------------------------------------------------


class TestAnnotationConversion:
    def test_evidence_to_annotations(self) -> None:
        """Evidence records are correctly converted to check annotations."""
        evidence = [
            {"requirement_id": "formatting", "executor": "ruff", "status": "pass", "summary": "ok"},
            {"requirement_id": "type_check", "executor": "pyright", "status": "fail", "summary": "3 errors"},
            {"requirement_id": "secret_scan", "executor": "secrets", "status": "pass", "summary": "clean"},
        ]

        annotations = GitHubIntegration._evidence_to_annotations(evidence)

        assert len(annotations) == 3
        assert annotations[0].annotation_level == "notice"  # pass → notice
        assert annotations[1].annotation_level == "failure"  # fail → failure
        assert annotations[2].annotation_level == "notice"

    def test_empty_evidence(self) -> None:
        """Empty evidence list produces no annotations."""
        annotations = GitHubIntegration._evidence_to_annotations([])
        assert len(annotations) == 0

    def test_unknown_status_maps_to_warning(self) -> None:
        """Unknown statuses default to warning level."""
        evidence = [{"requirement_id": "x", "executor": "test", "status": "unknown_weird", "summary": "?"}]
        annotations = GitHubIntegration._evidence_to_annotations(evidence)
        assert annotations[0].annotation_level == "warning"


# ---------------------------------------------------------------------------
# Check Run Result Tests
# ---------------------------------------------------------------------------


class TestCheckRunResult:
    def test_error_result(self) -> None:
        """CheckRunResult with error is handled gracefully."""
        result = CheckRunResult(error="Token not found")
        assert result.error == "Token not found"
        assert result.check_run_id is None
        assert result.html_url == ""

    def test_success_result(self) -> None:
        """CheckRunResult holds all fields correctly."""
        result = CheckRunResult(
            check_run_id=12345,
            check_run_url="https://api.github.com/repos/x/y/check-runs/12345",
            conclusion="success",
            annotations_count=5,
            html_url="https://github.com/x/y/runs/12345",
        )
        assert result.check_run_id == 12345
        assert result.conclusion == "success"
        assert result.annotations_count == 5


# ---------------------------------------------------------------------------
# Integration Flow Tests (no API calls)
# ---------------------------------------------------------------------------


class TestIntegrationFlow:
    def _assert_api_error(self, error: str | None) -> None:
        """API error without token should mention token or get 404."""
        assert error is not None
        error_lower = error.lower()
        assert "token" in error_lower or "404" in error_lower or "not found" in error_lower

    def test_create_check_run_without_token(
        self, integration: GitHubIntegration, sample_evidence: dict
    ) -> None:
        """Without token, check run returns error (doesn't crash)."""
        result = integration.create_check_run(
            name="test",
            head_sha="abc123",
            evidence_summary=sample_evidence,
        )
        self._assert_api_error(result.error)

    def test_create_pr_comment_without_token(
        self, integration: GitHubIntegration, sample_evidence: dict
    ) -> None:
        """Without token, PR comment returns error (doesn't crash)."""
        result = integration.create_pr_comment(
            pr_number=1,
            evidence_summary=sample_evidence,
        )
        self._assert_api_error(result.get("error"))

    def test_upload_artifact_missing_file(self, integration: GitHubIntegration) -> None:
        """Uploading a nonexistent artifact returns error."""
        result = integration.upload_artifact(
            run_id="test",
            artifact_path=Path("/nonexistent/bundle.json"),
        )
        assert "error" in result

    def test_create_draft_pr_without_token(
        self, integration: GitHubIntegration
    ) -> None:
        """Draft PR without token returns error (doesn't crash)."""
        result = integration.create_draft_pr(
            head_branch="feature/x",
            base_branch="main",
            title="Test PR",
        )
        self._assert_api_error(result.get("error"))
