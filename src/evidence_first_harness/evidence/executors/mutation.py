"""Mutation testing evidence executor."""

from __future__ import annotations

import asyncio
import hashlib
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from evidence_first_harness.domain.evidence import EvidenceRecord, EvidenceRequirement
from evidence_first_harness.evidence.executors.base import EvidenceExecutionContext

_MUTATION_COUNTS_PATTERN = re.compile(
    r"(?P<killed>\d+)\s+killed,\s+"
    r"(?P<survived>\d+)\s+survived,\s+"
    r"(?P<timeout>\d+)\s+timeout"
)


class MutationExecutor:
    """Run mutmut and report mutation testing results."""

    name = "mutation_test"

    async def execute(
        self,
        context: EvidenceExecutionContext,
        requirement: EvidenceRequirement,
    ) -> EvidenceRecord:
        started_at = datetime.now(UTC)
        command = [
            context.python_path,
            "-m",
            "mutmut",
            "run",
            "--paths-to-mutate",
            str(context.worktree_path / "src"),
        ]

        try:
            result = await asyncio.to_thread(
                subprocess.run,
                command,
                cwd=context.worktree_path,
                capture_output=True,
                text=True,
                timeout=context.timeout_seconds,
                env=self._build_environment(context),
                check=False,
            )
        except subprocess.TimeoutExpired:
            completed_at = datetime.now(UTC)
            return self._build_record(
                requirement=requirement,
                command=command,
                started_at=started_at,
                completed_at=completed_at,
                status="error",
                exit_code=None,
                summary=(f"Mutation testing timed out after {context.timeout_seconds} seconds."),
                limitations=["Mutation testing exceeded the executor timeout."],
                environment_digest=self._environment_digest(context),
            )
        except FileNotFoundError as error:
            completed_at = datetime.now(UTC)
            return self._build_record(
                requirement=requirement,
                command=command,
                started_at=started_at,
                completed_at=completed_at,
                status="error",
                exit_code=None,
                summary=f"Failed to start mutation testing: {error}.",
                limitations=["The configured Python interpreter could not be executed."],
                environment_digest=self._environment_digest(context),
            )
        except OSError as error:
            completed_at = datetime.now(UTC)
            return self._build_record(
                requirement=requirement,
                command=command,
                started_at=started_at,
                completed_at=completed_at,
                status="error",
                exit_code=None,
                summary=f"Mutation testing failed to launch: {error}.",
                environment_digest=self._environment_digest(context),
            )

        completed_at = datetime.now(UTC)
        output = self._combine_output(result.stdout, result.stderr)

        if self._mutmut_missing(output):
            return self._build_record(
                requirement=requirement,
                command=command,
                started_at=started_at,
                completed_at=completed_at,
                status="unavailable",
                exit_code=result.returncode,
                summary="Mutation testing is unavailable because mutmut is not installed.",
                limitations=["Install mutmut in the executor environment to collect evidence."],
                environment_digest=self._environment_digest(context),
            )

        counts = self._parse_counts(output)
        if counts is None:
            return self._build_record(
                requirement=requirement,
                command=command,
                started_at=started_at,
                completed_at=completed_at,
                status="error",
                exit_code=result.returncode,
                summary="Mutation testing completed but the mutmut result summary could not be parsed.",
                limitations=[
                    "Expected a mutmut summary containing killed, survived, and timeout counts."
                ],
                environment_digest=self._environment_digest(context),
            )

        killed, survived, timed_out = counts
        total = killed + survived
        mutation_score = killed / total if total > 0 else 0.0
        metrics: dict[str, float | int | str] = {
            "mutants_killed": killed,
            "mutants_survived": survived,
            "mutants_total": total,
            "mutation_score": mutation_score,
            "mutants_timeout": timed_out,
        }

        status, summary, limitations = self._evaluate_result(
            result=result,
            requirement=requirement,
            killed=killed,
            survived=survived,
            timed_out=timed_out,
            total=total,
            mutation_score=mutation_score,
        )

        return self._build_record(
            requirement=requirement,
            command=command,
            started_at=started_at,
            completed_at=completed_at,
            status=status,
            exit_code=result.returncode,
            summary=summary,
            metrics=metrics,
            limitations=limitations,
            environment_digest=self._environment_digest(context),
        )

    def _evaluate_result(
        self,
        result: subprocess.CompletedProcess[str],
        requirement: EvidenceRequirement,
        killed: int,
        survived: int,
        timed_out: int,
        total: int,
        mutation_score: float,
    ) -> tuple[str, str, list[str]]:
        limitations: list[str] = []
        if timed_out > 0:
            limitations.append(f"{timed_out} mutants timed out during execution.")

        if total == 0:
            limitations.append("Mutmut reported no killed or survived mutants.")
            return (
                "partial",
                "Mutation testing ran but no scored mutants were reported.",
                limitations,
            )

        if result.returncode != 0 and survived == 0:
            return (
                "error",
                "Mutation testing exited non-zero without reporting surviving mutants.",
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
                f"Mutation testing found {survived} surviving mutants out of {total}.",
                limitations,
            )

        return (
            "pass",
            f"Mutation testing killed all {total} scored mutants.",
            limitations,
        )

    @staticmethod
    def _parse_counts(output: str) -> tuple[int, int, int] | None:
        match = _MUTATION_COUNTS_PATTERN.search(output)
        if match is None:
            return None
        return (
            int(match.group("killed")),
            int(match.group("survived")),
            int(match.group("timeout")),
        )

    @staticmethod
    def _mutmut_missing(output: str) -> bool:
        lowered = output.lower()
        return "no module named mutmut" in lowered or "no module named 'mutmut'" in lowered

    @staticmethod
    def _combine_output(stdout: str, stderr: str) -> str:
        return "\n".join(part for part in (stdout.strip(), stderr.strip()) if part)

    @staticmethod
    def _build_environment(context: EvidenceExecutionContext) -> dict[str, str]:
        environment = dict(context.environment)
        if "PATH" not in environment:
            path_value = str(Path(context.python_path).parent)
            if path_value != ".":
                environment["PATH"] = path_value
        return environment

    @staticmethod
    def _environment_digest(context: EvidenceExecutionContext) -> str:
        entries = [
            f"python_path={context.python_path}",
            f"ruff_path={context.ruff_path}",
            f"pyright_path={context.pyright_path}",
            f"pytest_path={context.pytest_path}",
            f"timeout_seconds={context.timeout_seconds}",
        ]
        entries.extend(f"{key}={value}" for key, value in sorted(context.environment.items()))
        digest = hashlib.sha256("\n".join(entries).encode("utf-8")).hexdigest()
        return f"sha256:{digest}"

    def _build_record(
        self,
        requirement: EvidenceRequirement,
        command: list[str],
        started_at: datetime,
        completed_at: datetime,
        status: str,
        exit_code: int | None,
        summary: str,
        metrics: dict[str, float | int | str] | None = None,
        limitations: list[str] | None = None,
        environment_digest: str = "",
    ) -> EvidenceRecord:
        return EvidenceRecord(
            id=f"{requirement.id}_{self.name}",
            requirement_id=requirement.id,
            status=status,
            executor=self.name,
            command=command,
            started_at=started_at,
            completed_at=completed_at,
            exit_code=exit_code,
            summary=summary,
            metrics=metrics or {},
            environment_digest=environment_digest,
            limitations=limitations or [],
        )
