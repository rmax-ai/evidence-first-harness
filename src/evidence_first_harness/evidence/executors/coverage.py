"""Coverage evidence executor."""

from __future__ import annotations

import asyncio
import hashlib
import re
import subprocess
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from evidence_first_harness.domain.evidence import EvidenceRecord, EvidenceRequirement

if TYPE_CHECKING:
    from evidence_first_harness.evidence.executors.base import EvidenceExecutionContext

_TEST_SUMMARY_PATTERN = re.compile(r"(?P<count>\d+)\s+(?P<label>passed|failed)")
_COVERAGE_TOTAL_PATTERN = re.compile(
    r"^TOTAL\s+\d+\s+\d+\s+(?P<coverage>\d+(?:\.\d+)?)%$", re.MULTILINE
)


def _environment_digest(environment: dict[str, str]) -> str:
    payload = "\n".join(f"{key}={value}" for key, value in sorted(environment.items()))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


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


def _parse_coverage_pct(output: str) -> float | None:
    match = _COVERAGE_TOTAL_PATTERN.search(output)
    if match is None:
        return None
    return float(match.group("coverage"))


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


class CoverageExecutor:
    """Run pytest with coverage reporting and parse the total coverage."""

    name = "coverage"

    async def execute(
        self,
        context: EvidenceExecutionContext,
        requirement: EvidenceRequirement,
    ) -> EvidenceRecord:
        """Execute pytest-cov for the target worktree."""
        started_at = datetime.now(UTC)
        command = [context.pytest_path, "--cov=.", "--cov-report=term", "-q"]

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
                metrics={"coverage_pct": 0.0, "tests_passed": 0, "tests_total": 0},
                limitations=[
                    "Install pytest and pytest-cov, or provide a valid "
                    "pytest_path in the execution context.",
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
                summary="Coverage execution timed out",
                exit_code=None,
                metrics={"coverage_pct": 0.0, "tests_passed": 0, "tests_total": 0},
                limitations=[f"Execution exceeded timeout of {context.timeout_seconds} seconds."],
            )

        completed_at = datetime.now(UTC)
        combined_output = "\n".join(part for part in (result.stdout, result.stderr) if part.strip())
        lowered_output = combined_output.lower()

        if (
            "unrecognized arguments: --cov" in lowered_output
            or "no module named pytest_cov" in lowered_output
        ):
            return _build_record(
                requirement=requirement,
                executor=self.name,
                command=command,
                started_at=started_at,
                completed_at=completed_at,
                environment=context.environment,
                status="unavailable",
                summary="pytest-cov is not installed or not enabled for this pytest environment",
                exit_code=result.returncode,
                metrics={"coverage_pct": 0.0, "tests_passed": 0, "tests_total": 0},
                limitations=[
                    "Install pytest-cov in the execution environment to collect coverage."
                ],
            )

        tests_passed, tests_failed = _parse_test_counts(combined_output)
        coverage_pct = _parse_coverage_pct(combined_output)
        tests_total = tests_passed + tests_failed

        status = "pass" if result.returncode == 0 else "fail"
        summary = (
            "Coverage checks passed"
            if result.returncode == 0
            else "Coverage run reported failing tests or execution issues"
        )
        limitations: list[str] = []
        if coverage_pct is None:
            limitations.append("Coverage percentage could not be parsed from pytest output.")

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
                "coverage_pct": coverage_pct if coverage_pct is not None else 0.0,
                "tests_passed": tests_passed,
                "tests_total": tests_total,
            },
            limitations=limitations,
        )
