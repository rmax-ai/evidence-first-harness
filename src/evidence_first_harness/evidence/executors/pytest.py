"""Pytest evidence executor."""

from __future__ import annotations

import asyncio
import hashlib
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from evidence_first_harness.domain.evidence import EvidenceRecord, EvidenceRequirement

if TYPE_CHECKING:
    from evidence_first_harness.evidence.executors.base import EvidenceExecutionContext

_TEST_SUMMARY_PATTERN = re.compile(r"(?P<count>\d+)\s+(?P<label>passed|failed)")


def _environment_digest(environment: dict[str, str]) -> str:
    payload = "\n".join(f"{key}={value}" for key, value in sorted(environment.items()))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _tests_directory_warning(worktree_path: Path) -> str | None:
    tests_dir = worktree_path / "tests"
    if not tests_dir.exists():
        return "tests directory does not exist"
    if not any(path.is_file() for path in tests_dir.rglob("*")):
        return "tests directory exists but contains no files"
    return None


def _parse_test_counts(output: str) -> tuple[int, int]:
    passed = 0
    failed = 0
    for match in _TEST_SUMMARY_PATTERN.finditer(output):
        count = int(match.group("count"))
        label = match.group("label")
        if label == "passed":
            passed = count
        elif label == "failed":
            failed = count
    return passed, failed


def _build_record(
    *,
    requirement: EvidenceRequirement,
    executor: str,
    command: list[str],
    started_at: datetime,
    completed_at: datetime,
    environment: dict[str, str],
    status: str,
    summary: str,
    exit_code: int | None,
    metrics: dict[str, float | int | str],
    limitations: list[str],
) -> EvidenceRecord:
    return EvidenceRecord(
        id=f"{requirement.id}_{executor}",
        requirement_id=requirement.id,
        status=status,
        executor=executor,
        command=command,
        started_at=started_at,
        completed_at=completed_at,
        exit_code=exit_code,
        summary=summary,
        metrics=metrics,
        environment_digest=_environment_digest(environment),
        limitations=limitations,
    )


class PytestExecutor:
    """Run pytest and report test execution metrics."""

    name = "pytest"

    async def execute(
        self,
        context: EvidenceExecutionContext,
        requirement: EvidenceRequirement,
    ) -> EvidenceRecord:
        """Execute pytest for the target worktree."""
        started_at = datetime.now(UTC)
        command = [context.pytest_path, "-q", "--tb=short"]
        limitations: list[str] = []

        tests_warning = _tests_directory_warning(context.worktree_path)
        if tests_warning is not None:
            limitations.append(tests_warning)

        try:
            result = await asyncio.to_thread(
                subprocess.run,
                command,
                capture_output=True,
                text=True,
                cwd=context.worktree_path,
                env=context.environment or None,
                timeout=context.timeout_seconds,
                check=False,
            )
        except FileNotFoundError:
            completed_at = datetime.now(UTC)
            return _build_record(
                requirement=requirement,
                executor=self.name,
                command=command,
                started_at=started_at,
                completed_at=completed_at,
                environment=context.environment,
                status="unavailable",
                summary="Pytest executable was not found",
                exit_code=None,
                metrics={"tests_passed": 0, "tests_failed": 0, "tests_total": 0},
                limitations=[
                    *limitations,
                    "Install pytest or provide a valid pytest_path in the execution context.",
                ],
            )
        except subprocess.TimeoutExpired:
            completed_at = datetime.now(UTC)
            return _build_record(
                requirement=requirement,
                executor=self.name,
                command=command,
                started_at=started_at,
                completed_at=completed_at,
                environment=context.environment,
                status="error",
                summary="Pytest execution timed out",
                exit_code=None,
                metrics={"tests_passed": 0, "tests_failed": 0, "tests_total": 0},
                limitations=[
                    *limitations,
                    f"Execution exceeded timeout of {context.timeout_seconds} seconds.",
                ],
            )

        completed_at = datetime.now(UTC)
        combined_output = "\n".join(part for part in (result.stdout, result.stderr) if part.strip())
        tests_passed, tests_failed = _parse_test_counts(combined_output)
        tests_total = tests_passed + tests_failed

        status = "pass" if result.returncode == 0 else "fail"
        summary = (
            "Pytest checks passed"
            if result.returncode == 0
            else "Pytest reported failing tests or execution issues"
        )
        if tests_warning is not None:
            summary = f"{summary}; warning: {tests_warning}"

        return _build_record(
            requirement=requirement,
            executor=self.name,
            command=command,
            started_at=started_at,
            completed_at=completed_at,
            environment=context.environment,
            status=status,
            summary=summary,
            exit_code=result.returncode,
            metrics={
                "tests_passed": tests_passed,
                "tests_failed": tests_failed,
                "tests_total": tests_total,
            },
            limitations=limitations,
        )
