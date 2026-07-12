"""Coverage evidence executor."""

from __future__ import annotations

import hashlib
import re
import subprocess
from datetime import UTC, datetime

from evidence_first_harness.domain.evidence import EvidenceRecord, EvidenceRequirement
from evidence_first_harness.evidence.executors.base import EvidenceExecutionContext

_SUMMARY_PATTERN = re.compile(r"(?P<count>\d+)\s+(?P<label>passed|failed|skipped|error)")
_TOTAL_PATTERN = re.compile(r"^TOTAL\s+\d+\s+\d+\s+(?P<coverage>\d+)%$", re.MULTILINE)


class CoverageExecutor:
    """Run pytest with coverage enabled and parse the total coverage percentage."""

    name = "coverage"

    async def execute(
        self,
        context: EvidenceExecutionContext,
        requirement: EvidenceRequirement,
    ) -> EvidenceRecord:
        """Execute pytest-cov in the target worktree."""
        started_at = context.started_at
        command = [context.pytest_path, "--cov=.", "--cov-report=term", "-q"]

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
                summary="coverage run timed out",
                environment_digest=_environment_digest(context),
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
                summary=f"coverage run could not start: {exc}",
                environment_digest=_environment_digest(context),
            )

        output = "\n".join(part for part in [result.stdout, result.stderr] if part.strip())
        if _pytest_cov_missing(output):
            completed_at = datetime.now(UTC)
            return EvidenceRecord(
                id=_record_id(requirement.id, self.name),
                requirement_id=requirement.id,
                status="unavailable",
                executor=self.name,
                command=command,
                started_at=started_at,
                completed_at=completed_at,
                exit_code=result.returncode,
                summary="pytest-cov is not installed or not available",
                environment_digest=_environment_digest(context),
                limitations=["coverage requires the pytest-cov plugin"],
            )

        counts = _parse_summary_counts(output)
        passed = counts.get("passed", 0)
        failed = counts.get("failed", 0) + counts.get("error", 0)
        total = passed + failed
        coverage_pct = _parse_coverage_percentage(output)
        metrics: dict[str, float | int | str] = {
            "tests_passed": passed,
            "tests_total": total,
        }
        if coverage_pct is not None:
            metrics["coverage_pct"] = coverage_pct

        completed_at = datetime.now(UTC)
        status = _status_for_result(
            returncode=result.returncode,
            failed=failed,
            coverage_pct=coverage_pct,
            minimum_threshold=requirement.minimum_threshold,
        )
        summary = _build_summary(
            status=status,
            coverage_pct=coverage_pct,
            passed=passed,
            total=total,
            failed=failed,
            threshold=requirement.minimum_threshold,
            returncode=result.returncode,
        )

        limitations: list[str] = []
        if coverage_pct is None:
            limitations.append("TOTAL coverage line was not present in pytest output")
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
            metrics=metrics,
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


def _parse_coverage_percentage(output: str) -> float | None:
    match = _TOTAL_PATTERN.search(output)
    if match is None:
        return None
    return float(match.group("coverage"))


def _pytest_cov_missing(output: str) -> bool:
    lowered = output.lower()
    return "unrecognized arguments: --cov=." in lowered or "no module named pytest_cov" in lowered


def _status_for_result(
    *,
    returncode: int,
    failed: int,
    coverage_pct: float | None,
    minimum_threshold: float | None,
) -> str:
    if returncode == 0 and coverage_pct is not None:
        if minimum_threshold is not None and coverage_pct < minimum_threshold:
            return "fail"
        return "pass"
    if returncode == 5:
        return "partial"
    if failed > 0:
        return "fail"
    if (
        coverage_pct is not None
        and minimum_threshold is not None
        and coverage_pct < minimum_threshold
    ):
        return "fail"
    return "error"


def _build_summary(
    *,
    status: str,
    coverage_pct: float | None,
    passed: int,
    total: int,
    failed: int,
    threshold: float | None,
    returncode: int,
) -> str:
    if status == "pass" and coverage_pct is not None:
        return f"coverage {coverage_pct:.0f}% across {passed} passing tests"
    if status == "partial":
        return "coverage run did not collect any tests"
    if status == "fail" and failed > 0:
        return f"coverage run reported {failed} failing tests out of {total}"
    if status == "fail" and coverage_pct is not None and threshold is not None:
        return f"coverage {coverage_pct:.0f}% is below required threshold {threshold:.0f}%"
    return f"coverage run exited with code {returncode}"


def _record_id(requirement_id: str, executor_name: str) -> str:
    return f"{requirement_id}_{executor_name}"
