"""Pytest evidence executor."""

from __future__ import annotations

import hashlib
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from evidence_first_harness.domain.evidence import EvidenceRecord, EvidenceRequirement
from evidence_first_harness.evidence.executors.base import EvidenceExecutionContext

_SUMMARY_PATTERN = re.compile(r"(?P<count>\d+)\s+(?P<label>passed|failed|skipped|error)")


class PytestExecutor:
    """Run pytest and parse the resulting test counts."""

    name = "pytest"

    async def execute(
        self,
        context: EvidenceExecutionContext,
        requirement: EvidenceRequirement,
    ) -> EvidenceRecord:
        """Execute pytest in the target worktree."""
        started_at = context.started_at
        command = [context.pytest_path, "-q", "--tb=short"]
        limitations: list[str] = []
        tests_dir = context.worktree_path / "tests"
        if not tests_dir.exists():
            limitations.append("tests directory does not exist")
        elif not any(tests_dir.iterdir()):
            limitations.append("tests directory is empty")

        try:
            result = subprocess.run(
                command,
                cwd=context.worktree_path,
                capture_output=True,
                text=True,
                timeout=context.timeout_seconds,
                check=False,
                env=_build_environment(context),
            )
        except subprocess.TimeoutExpired:
            completed_at = datetime.now(UTC)
            return EvidenceRecord(
                id=_record_id(requirement.id, self.name),
                requirement_id=requirement.id,
                status="error",
                executor=self.name,
                command=command,
                started_at=started_at,
                completed_at=completed_at,
                exit_code=None,
                summary="pytest timed out",
                environment_digest=_environment_digest(context),
                limitations=limitations,
            )
        except OSError as exc:
            completed_at = datetime.now(UTC)
            return EvidenceRecord(
                id=_record_id(requirement.id, self.name),
                requirement_id=requirement.id,
                status="error",
                executor=self.name,
                command=command,
                started_at=started_at,
                completed_at=completed_at,
                exit_code=None,
                summary=f"pytest could not start: {exc}",
                environment_digest=_environment_digest(context),
                limitations=limitations,
            )

        output = "\n".join(part for part in [result.stdout, result.stderr] if part.strip())
        counts = _parse_summary_counts(output)
        passed = counts.get("passed", 0)
        failed = counts.get("failed", 0) + counts.get("error", 0)
        total = passed + failed
        completed_at = datetime.now(UTC)

        status = _status_for_result(result.returncode, total, failed)
        summary = _build_summary(status, passed, failed, total, result.returncode)

        if result.returncode == 5:
            limitations.append("pytest reported that no tests were collected")

        return EvidenceRecord(
            id=_record_id(requirement.id, self.name),
            requirement_id=requirement.id,
            status=status,
            executor=self.name,
            command=command,
            started_at=started_at,
            completed_at=completed_at,
            exit_code=result.returncode,
            summary=summary,
            metrics={
                "tests_passed": passed,
                "tests_failed": failed,
                "tests_total": total,
            },
            environment_digest=_environment_digest(context),
            limitations=limitations,
        )


def _build_environment(context: EvidenceExecutionContext) -> dict[str, str]:
    environment = dict(context.environment)
    return environment


def _environment_digest(context: EvidenceExecutionContext) -> str:
    parts = [
        f"python_path={context.python_path}",
        f"pytest_path={context.pytest_path}",
        f"timeout_seconds={context.timeout_seconds}",
        f"sandbox_id={context.sandbox_id or ''}",
    ]
    parts.extend(
        f"{key}={value}"
        for key, value in sorted(context.environment.items(), key=lambda item: item[0])
    )
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def _parse_summary_counts(output: str) -> dict[str, int]:
    counts = {"passed": 0, "failed": 0, "skipped": 0, "error": 0}
    for match in _SUMMARY_PATTERN.finditer(output):
        label = match.group("label")
        counts[label] = counts.get(label, 0) + int(match.group("count"))
    return counts


def _status_for_result(returncode: int, total: int, failed: int) -> str:
    if returncode == 0:
        return "pass"
    if returncode == 5 or total == 0:
        return "partial"
    if failed > 0:
        return "fail"
    return "error"


def _build_summary(status: str, passed: int, failed: int, total: int, returncode: int) -> str:
    if status == "pass":
        return f"pytest passed {passed} of {total} tests"
    if status == "partial":
        return "pytest did not collect any tests"
    if status == "fail":
        return f"pytest reported {failed} failing tests out of {total}"
    return f"pytest exited with code {returncode}"


def _record_id(requirement_id: str, executor_name: str) -> str:
    return f"{requirement_id}_{executor_name}"
