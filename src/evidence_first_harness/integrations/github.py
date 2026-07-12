"""GitHub integration — Checks API, PR comments, evidence artifacts.

Section 23 of the spec. Publishes evidence bundles as GitHub Check Runs
with structured annotations for each evidence executor result.

Uses the GitHub REST API via `gh` CLI or direct HTTP calls.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger()


@dataclass
class CheckAnnotation:
    """A single annotation for a GitHub Check Run."""

    path: str
    start_line: int
    end_line: int
    annotation_level: str  # "notice", "warning", "failure"
    message: str
    title: str = ""
    raw_details: str = ""


@dataclass
class CheckRunResult:
    """Complete result of a GitHub Check Run publication."""

    check_run_id: int | None = None
    check_run_url: str = ""
    conclusion: str = "neutral"  # "success", "failure", "neutral", "cancelled", "timed_out", "action_required"
    annotations_count: int = 0
    html_url: str = ""
    error: str | None = None


class GitHubIntegration:
    """Publishes evidence bundles as GitHub Check Runs.

    Uses the GitHub REST API to create check runs with structured
    annotations, evidence summaries, and artifact attachments.

    Authentication:
        Uses the `GITHUB_TOKEN` environment variable or `gh auth token`.
        For private repos, a token with `repo` scope is required.
    """

    def __init__(
        self,
        owner: str,
        repo: str,
        token: str | None = None,
        api_url: str = "https://api.github.com",
    ) -> None:
        """Initialize the GitHub integration.

        Args:
            owner: Repository owner (org or user).
            repo: Repository name.
            token: GitHub personal access token. If None, uses GITHUB_TOKEN env var or `gh auth token`.
            api_url: GitHub API base URL (for GitHub Enterprise).
        """
        self._owner = owner
        self._repo = repo
        self._api_url = api_url.rstrip("/")
        self._token = token or self._resolve_token()

    @property
    def repo_slug(self) -> str:
        return f"{self._owner}/{self._repo}"

    def create_check_run(
        self,
        name: str,
        head_sha: str,
        evidence_summary: dict[str, Any],
        annotations: list[CheckAnnotation] | None = None,
        conclusion: str = "neutral",
        details_url: str = "",
        external_id: str = "",
    ) -> CheckRunResult:
        """Create a GitHub Check Run with evidence results.

        Args:
            name: Check run name (e.g., "Evidence-First Harness").
            head_sha: The commit SHA to attach the check to.
            evidence_summary: Dict with decision, evidence counts, risk tier, etc.
            annotations: Optional list of CheckAnnotation for individual evidence results.
            conclusion: "success", "failure", "neutral", "cancelled", "timed_out", "action_required".
            details_url: URL to the full evidence bundle.
            external_id: Optional external ID for idempotency.

        Returns:
            CheckRunResult with the GitHub API response data.
        """
        if not self._token:
            return CheckRunResult(error="No GitHub token available")

        # Build the summary text
        summary_text = self._format_summary(evidence_summary)

        # Build annotations from evidence results
        check_annotations = annotations or []
        if not check_annotations and "evidence" in evidence_summary:
            check_annotations = self._evidence_to_annotations(
                evidence_summary["evidence"]
            )

        payload: dict[str, Any] = {
            "name": name,
            "head_sha": head_sha,
            "status": "completed",
            "conclusion": conclusion,
            "completed_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "output": {
                "title": self._make_title(evidence_summary),
                "summary": summary_text,
                "annotations": [
                    {
                        "path": a.path,
                        "start_line": a.start_line,
                        "end_line": a.end_line,
                        "annotation_level": a.annotation_level,
                        "message": a.message,
                        "title": a.title or a.annotation_level,
                    }
                    for a in check_annotations[:50]  # GitHub limit: 50 per check run
                ],
            },
        }

        if external_id:
            payload["external_id"] = external_id

        if details_url:
            payload["details_url"] = details_url

        # Create the check run
        result = self._api_request(
            "POST",
            f"/repos/{self._owner}/{self._repo}/check-runs",
            payload,
        )

        if result.get("error"):
            return CheckRunResult(error=result["error"])

        return CheckRunResult(
            check_run_id=result.get("id"),
            check_run_url=result.get("url", ""),
            conclusion=conclusion,
            annotations_count=len(check_annotations),
            html_url=result.get("html_url", ""),
        )

    def create_pr_comment(
        self,
        pr_number: int,
        evidence_summary: dict[str, Any],
    ) -> dict[str, Any]:
        """Post an evidence summary as a PR comment.

        Args:
            pr_number: Pull request number.
            evidence_summary: Dict with decision, evidence counts, etc.

        Returns:
            API response dict.
        """
        if not self._token:
            return {"error": "No GitHub token available"}

        body = self._format_pr_comment(evidence_summary)

        return self._api_request(
            "POST",
            f"/repos/{self._owner}/{self._repo}/issues/{pr_number}/comments",
            {"body": body},
        )

    def create_draft_pr(
        self,
        head_branch: str,
        base_branch: str,
        title: str,
        body: str = "",
    ) -> dict[str, Any]:
        """Create a draft pull request.

        Args:
            head_branch: Source branch name.
            base_branch: Target branch name (e.g., "main").
            title: PR title.
            body: PR description (markdown).

        Returns:
            API response dict with PR number and URL.
        """
        if not self._token:
            return {"error": "No GitHub token available"}

        return self._api_request(
            "POST",
            f"/repos/{self._owner}/{self._repo}/pulls",
            {
                "title": title,
                "head": head_branch,
                "base": base_branch,
                "body": body,
                "draft": True,
            },
        )

    def upload_artifact(
        self,
        run_id: str,
        artifact_path: Path,
    ) -> dict[str, Any]:
        """Upload an evidence bundle as a GitHub Actions artifact.

        Note: Requires GitHub Actions runner context.
        For non-Actions environments, returns the path for manual upload.

        Args:
            run_id: The harness run ID.
            artifact_path: Path to the evidence bundle file.

        Returns:
            Dict with artifact info or error.
        """
        if not artifact_path.exists():
            return {"error": f"Artifact not found: {artifact_path}"}

        # In a GitHub Actions runner, upload via actions/upload-artifact
        if os.environ.get("GITHUB_ACTIONS") == "true":
            try:
                subprocess.run(
                    [
                        "gh", "run", "upload",
                        "--name", f"evidence-bundle-{run_id}",
                        str(artifact_path),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=True,
                )
                return {
                    "artifact_name": f"evidence-bundle-{run_id}",
                    "path": str(artifact_path),
                    "uploaded": True,
                }
            except subprocess.CalledProcessError as e:
                return {"error": f"Upload failed: {e.stderr}"}

        # For local runs, return the path for reference
        return {
            "artifact_name": f"evidence-bundle-{run_id}",
            "path": str(artifact_path),
            "uploaded": False,
            "note": "Not running in GitHub Actions — artifact available locally",
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_token() -> str | None:
        """Resolve a GitHub token from environment or gh CLI."""
        # Check environment
        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if token:
            return token

        # Try gh CLI
        try:
            result = subprocess.run(
                ["gh", "auth", "token"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            pass

        return None

    def _api_request(
        self,
        method: str,
        path: str,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make an authenticated GitHub API request.

        Args:
            method: HTTP method (GET, POST, PATCH).
            path: API path (e.g., "/repos/owner/repo/check-runs").
            data: Optional JSON body.

        Returns:
            Parsed JSON response dict.
        """
        import urllib.request
        import urllib.error

        url = f"{self._api_url}{path}"
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self._token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "evidence-first-harness",
        }

        body_bytes: bytes | None = None
        if data is not None:
            body_bytes = json.dumps(data).encode("utf-8")
            headers["Content-Type"] = "application/json"

        try:
            req = urllib.request.Request(url, data=body_bytes, headers=headers, method=method)
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            logger.error(
                "github_api_error",
                method=method,
                path=path,
                status=e.code,
                error=error_body[:500],
            )
            return {"error": f"HTTP {e.code}: {error_body[:200]}"}
        except Exception as e:
            logger.error(
                "github_api_request_failed",
                method=method,
                path=path,
                error=str(e),
            )
            return {"error": str(e)}

    @staticmethod
    def _format_summary(evidence_summary: dict[str, Any]) -> str:
        """Format evidence summary as a GitHub Check Run summary (markdown)."""
        decision = evidence_summary.get("decision", {})
        decision_text = decision.get("decision", "unknown") if isinstance(decision, dict) else str(decision)

        risk = evidence_summary.get("risk", {})
        risk_tier = risk.get("overall_tier", "?") if isinstance(risk, dict) else "?"

        evidence = evidence_summary.get("evidence", [])
        passed = sum(1 for e in evidence if isinstance(e, dict) and e.get("status") == "pass")
        failed = sum(1 for e in evidence if isinstance(e, dict) and e.get("status") in ("fail", "error"))
        total = len(evidence)

        lines = [
            "## Evidence-First Harness — Check Run",
            "",
            f"**Decision:** `{decision_text}`",
            f"**Risk Tier:** {risk_tier}",
            f"**Evidence:** {passed} passed, {failed} failed, {total - passed - failed} other (of {total} total)",
            "",
            "### Evidence Detail",
            "",
        ]

        for e_record in evidence:
            if not isinstance(e_record, dict):
                continue
            status = e_record.get("status", "unknown")
            icon = {"pass": "✅", "fail": "❌", "error": "⚠️", "unavailable": "⬜", "partial": "🔶"}.get(status, "❓")
            executor = e_record.get("executor", "unknown")
            summary = e_record.get("summary", "")
            lines.append(f"- {icon} **{executor}**: {summary}")

        return "\n".join(lines)

    @staticmethod
    def _format_pr_comment(evidence_summary: dict[str, Any]) -> str:
        """Format evidence summary as a PR comment (markdown)."""
        decision = evidence_summary.get("decision", {})
        decision_text = decision.get("decision", "unknown") if isinstance(decision, dict) else str(decision)

        risk = evidence_summary.get("risk", {})
        risk_tier = risk.get("overall_tier", "?") if isinstance(risk, dict) else "?"

        run_id = evidence_summary.get("run_id", "unknown")
        repo = evidence_summary.get("repository", "unknown")
        base_commit = evidence_summary.get("base_commit", "unknown")

        impact = evidence_summary.get("impact", {})
        impact_conf = impact.get("confidence", "N/A") if isinstance(impact, dict) else "N/A"

        contradictions = evidence_summary.get("contradictions", [])
        limitations = evidence_summary.get("limitations", [])

        lines = [
            "## 🤖 Evidence-First Harness Report",
            "",
            f"**Run:** `{run_id}` | **Repo:** {repo} | **Base:** `{base_commit[:8]}`",
            "",
            "### Decision",
            f"**Decision:** `{decision_text}` | **Risk Tier:** {risk_tier}",
            f"**Impact confidence:** {impact_conf}",
            "",
        ]

        if contradictions:
            lines.append("### ⚠️ Contradictions")
            for c in contradictions[:5]:
                lines.append(f"- {c}")
            lines.append("")

        if limitations:
            lines.append("### 📋 Limitations")
            for lim in limitations[:5]:
                lines.append(f"- {lim}")
            lines.append("")

        lines.extend([
            "---",
            f"*Generated by Evidence-First Harness — run `{run_id}`*",
        ])

        return "\n".join(lines)

    @staticmethod
    def _make_title(evidence_summary: dict[str, Any]) -> str:
        """Create a concise title for the check run."""
        decision = evidence_summary.get("decision", {})
        decision_text = decision.get("decision", "unknown") if isinstance(decision, dict) else str(decision)
        return f"Evidence-First: {decision_text}"

    @staticmethod
    def _evidence_to_annotations(
        evidence: list[dict[str, Any]],
    ) -> list[CheckAnnotation]:
        """Convert evidence records to GitHub Check annotations."""
        annotations: list[CheckAnnotation] = []

        for e_record in evidence:
            if not isinstance(e_record, dict):
                continue

            status = e_record.get("status", "unknown")
            executor = e_record.get("executor", "unknown")
            summary = e_record.get("summary", "")
            req_id = e_record.get("requirement_id", executor)

            level = {
                "pass": "notice",
                "fail": "failure",
                "error": "failure",
                "unavailable": "warning",
                "partial": "warning",
            }.get(status, "warning")

            annotations.append(
                CheckAnnotation(
                    path=f"evidence:{req_id}",
                    start_line=1,
                    end_line=1,
                    annotation_level=level,
                    message=f"[{executor}] {summary}",
                    title=f"{executor} ({status})",
                )
            )

        return annotations
