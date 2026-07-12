"""Mutation testing evidence executor."""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
import subprocess
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal

from evidence_first_harness.domain.evidence import EvidenceRecord, EvidenceRequirement

if TYPE_CHECKING:
    from evidence_first_harness.evidence.executors.base import EvidenceExecutionContext

_MUTATION_SUMMARY_PATTERN = re.compile(
    r"(?P<killed>\d+)\s+killed,\s+"
    r"(?P<survived>\d+)\s+survived,\s+"
    r"(?P<timeout>\d+)\s+timeout"
)


class MutationExecutor:
    """Run mutmut mutation testing and summarize the result."""

    name = "mutation_test"

    async def execute(
        self,
        context: EvidenceExecutionContext,
        requirement: EvidenceRequirement,
    ) -> EvidenceRecord:
        """Run mutmut against the worktree and return structured evidence."""
        started_at = datetime.now(UTC)
        command = [
            context.python_path,
            "-m",
            "mutmut",
            "run",
            "--paths-to-mutate",
            str(context.worktree_path / "src"),
        ]
        environment_digest = _environment_digest(context)

        try:
            result = await asyncio.to_thread(
                subprocess.run,
                command,
                cwd=context.worktree_path,
                capture_output=True,
                text=True,
                timeout=context.timeout_seconds,
                env=_build_environment(context),
                check=False,
            )
        except subprocess.TimeoutExpired:
            completed_at = datetime.now(UTC)
            return _build_record(
                requirement=requirement,
                executor=self.name,
                command=command,
                started_at=started_at,
                completed_at=completed_at,
                status="error",
                exit_code=None,
                summary=f"mutmut timed out after {context.timeout_seconds} seconds.",
                environment_digest=environment_digest,
                limitations=["Mutation testing exceeded the executor timeout."],
            )
        except FileNotFoundError as error:
            completed_at = datetime.now(UTC)
            return _build_record(
                requirement=requirement,
                executor=self.name,
                command=command,
                started_at=started_at,
                completed_at=completed_at,
                status="error",
                exit_code=None,
                summary=f"Failed to start mutation testing: {_clean_text(str(error))}.",
                environment_digest=environment_digest,
            )
        except OSError as error:
            completed_at = datetime.now(UTC)
            return _build_record(
                requirement=requirement,
                executor=self.name,
                command=command,
                started_at=started_at,
                completed_at=completed_at,
                status="error",
                exit_code=None,
                summary=f"Mutation testing failed to execute: {_clean_text(str(error))}.",
                environment_digest=environment_digest,
            )

        completed_at = datetime.now(UTC)
        output = _combine_output(result.stdout, result.stderr)
        lowered_output = output.lower()
        if (
            "no module named mutmut" in lowered_output
            or "no module named 'mutmut'" in lowered_output
        ):
            return _build_record(
                requirement=requirement,
                executor=self.name,
                command=command,
                started_at=started_at,
                completed_at=completed_at,
                status="unavailable",
                exit_code=result.returncode,
                summary="Mutation testing is unavailable because mutmut is not installed.",
                environment_digest=environment_digest,
                limitations=["Install mutmut in the executor environment to collect evidence."],
            )

        match = _MUTATION_SUMMARY_PATTERN.search(output)
        if match is None:
            return _build_record(
                requirement=requirement,
                executor=self.name,
                command=command,
                started_at=started_at,
                completed_at=completed_at,
                status="error",
                exit_code=result.returncode,
                summary=("mutmut completed but its killed/survived summary could not be parsed."),
                environment_digest=environment_digest,
                limitations=[
                    "Expected a mutmut summary with killed, survived, and timeout counts."
                ],
            )

        killed = int(match.group("killed"))
        survived = int(match.group("survived"))
        timed_out = int(match.group("timeout"))
        total = killed + survived
        mutation_score = killed / total if total else 0.0

        status, summary, limitations = _evaluate_result(
            result=result,
            requirement=requirement,
            survived=survived,
            timed_out=timed_out,
            total=total,
            mutation_score=mutation_score,
        )

        return _build_record(
            requirement=requirement,
            executor=self.name,
            command=command,
            started_at=started_at,
            completed_at=completed_at,
            status=status,
            exit_code=result.returncode,
            summary=summary,
            environment_digest=environment_digest,
            metrics={
                "mutants_killed": killed,
                "mutants_survived": survived,
                "mutants_total": total,
                "mutation_score": mutation_score,
                "mutants_timeout": timed_out,
            },
            limitations=limitations,
        )


def _evaluate_result(
    *,
    result: subprocess.CompletedProcess[str],
    requirement: EvidenceRequirement,
    survived: int,
    timed_out: int,
    total: int,
    mutation_score: float,
) -> tuple[Literal["pass", "fail", "partial", "error"], str, list[str]]:
    limitations: list[str] = []
    if timed_out:
        limitations.append(f"{timed_out} mutants timed out during execution.")

    if total == 0:
        limitations.append("mutmut reported no killed or survived mutants.")
        return "partial", "mutmut ran but reported no scored mutants.", limitations

    if result.returncode != 0 and survived == 0:
        return (
            "error",
            "mutmut exited non-zero without reporting surviving mutants.",
            limitations,
        )

    if requirement.minimum_threshold is not None:
        if mutation_score >= requirement.minimum_threshold:
            return (
                "pass",
                f"Mutation score {mutation_score:.3f} meets the required threshold "
                f"of {requirement.minimum_threshold:.3f}.",
                limitations,
            )
        return (
            "fail",
            f"Mutation score {mutation_score:.3f} is below the required threshold "
            f"of {requirement.minimum_threshold:.3f}.",
            limitations,
        )

    if survived > 0:
        return (
            "fail",
            f"mutmut reported {survived} surviving mutants out of {total} scored mutants.",
            limitations,
        )

    return "pass", f"mutmut killed all {total} scored mutants.", limitations


def _build_environment(context: EvidenceExecutionContext) -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(context.environment)
    return environment


def _environment_digest(context: EvidenceExecutionContext) -> str:
    entries = [
        f"python_path={context.python_path}",
        f"ruff_path={context.ruff_path}",
        f"pyright_path={context.pyright_path}",
        f"pytest_path={context.pytest_path}",
        f"timeout_seconds={context.timeout_seconds}",
        f"worktree_path={context.worktree_path}",
    ]
    entries.extend(f"{key}={value}" for key, value in sorted(context.environment.items()))
    digest = hashlib.sha256("\n".join(entries).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _combine_output(stdout: str, stderr: str) -> str:
    return "\n".join(part for part in (stdout.strip(), stderr.strip()) if part)


def _clean_text(value: str) -> str:
    return " ".join(value.split())


def _build_record(
    *,
    requirement: EvidenceRequirement,
    executor: str,
    command: list[str],
    started_at: datetime,
    completed_at: datetime,
    status: Literal["pass", "fail", "partial", "error", "unavailable"],
    exit_code: int | None,
    summary: str,
    environment_digest: str,
    metrics: dict[str, float | int | str] | None = None,
    limitations: list[str] | None = None,
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
        metrics=metrics or {},
        environment_digest=environment_digest,
        limitations=limitations or [],
    )
