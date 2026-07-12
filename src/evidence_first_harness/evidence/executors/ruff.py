"""Ruff evidence executor."""

from __future__ import annotations

import asyncio
import hashlib
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from evidence_first_harness.domain.evidence import EvidenceRecord, EvidenceRequirement

if TYPE_CHECKING:
    from evidence_first_harness.evidence.executors.base import EvidenceExecutionContext


def _build_environment(context: EvidenceExecutionContext) -> dict[str, str]:
    environment = dict(os.environ)
    environment.update(context.environment)
    return environment


def _environment_digest(context: EvidenceExecutionContext) -> str:
    payload = [
        f"worktree_path={context.worktree_path}",
        f"ruff_path={context.ruff_path}",
        f"timeout_seconds={context.timeout_seconds}",
    ]
    payload.extend(f"{key}={value}" for key, value in sorted(context.environment.items()))
    digest = hashlib.sha256("\n".join(payload).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _line_count(output: str) -> int:
    return sum(1 for line in output.splitlines() if line.strip())


def _clean_output(output: str) -> str:
    return " ".join(output.split())


class RuffExecutor:
    """Run Ruff lint and format checks."""

    name = "ruff"

    async def execute(
        self,
        context: EvidenceExecutionContext,
        requirement: EvidenceRequirement,
    ) -> EvidenceRecord:
        """Execute Ruff lint and formatting checks for the target worktree."""
        started_at = datetime.now(UTC)
        worktree_path = Path(context.worktree_path)
        check_command = [context.ruff_path, "check"]
        format_command = [context.ruff_path, "format", "--check"]
        environment = _build_environment(context)
        environment_digest = _environment_digest(context)

        try:
            check_result = await asyncio.to_thread(
                subprocess.run,
                check_command,
                capture_output=True,
                text=True,
                cwd=worktree_path,
                env=environment,
                timeout=context.timeout_seconds,
                check=False,
            )
            format_result = await asyncio.to_thread(
                subprocess.run,
                format_command,
                capture_output=True,
                text=True,
                cwd=worktree_path,
                env=environment,
                timeout=context.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired:
            completed_at = datetime.now(UTC)
            return EvidenceRecord(
                id=f"{requirement.id}_{self.name}",
                requirement_id=requirement.id,
                status="error",
                executor=self.name,
                command=check_command,
                started_at=started_at,
                completed_at=completed_at,
                exit_code=None,
                summary=f"Ruff timed out after {context.timeout_seconds} seconds.",
                metrics={},
                environment_digest=environment_digest,
                limitations=[
                    "Ruff linting and formatting checks exceeded the configured timeout.",
                ],
            )
        except FileNotFoundError as error:
            completed_at = datetime.now(UTC)
            return EvidenceRecord(
                id=f"{requirement.id}_{self.name}",
                requirement_id=requirement.id,
                status="error",
                executor=self.name,
                command=check_command,
                started_at=started_at,
                completed_at=completed_at,
                exit_code=None,
                summary=f"Ruff failed to launch: {error}.",
                metrics={},
                environment_digest=environment_digest,
                limitations=[
                    "The configured Ruff executable is unavailable in the executor environment.",
                ],
            )

        completed_at = datetime.now(UTC)
        combined_output = "\n".join(
            part
            for part in (
                check_result.stdout,
                check_result.stderr,
                format_result.stdout,
                format_result.stderr,
            )
            if part.strip()
        )
        exit_code = 0 if check_result.returncode == 0 and format_result.returncode == 0 else 1
        status = "pass" if exit_code == 0 else "fail"

        if status == "pass":
            summary = "Ruff lint and format checks passed."
        else:
            summary = "Ruff reported lint or formatting violations."
            failure_detail = _clean_output(combined_output)
            if failure_detail:
                summary = f"{summary} {failure_detail}"

        return EvidenceRecord(
            id=f"{requirement.id}_{self.name}",
            requirement_id=requirement.id,
            status=status,
            executor=self.name,
            command=check_command,
            started_at=started_at,
            completed_at=completed_at,
            exit_code=exit_code,
            summary=summary,
            metrics={
                "exit_code": exit_code,
                "check_exit_code": check_result.returncode,
                "format_exit_code": format_result.returncode,
                "check_output_lines": _line_count(check_result.stdout + check_result.stderr),
                "format_output_lines": _line_count(format_result.stdout + format_result.stderr),
                "combined_output_lines": _line_count(combined_output),
            },
            environment_digest=environment_digest,
            limitations=[
                "Ruff only reports lint and formatting issues it is configured to detect.",
                "Results depend on the installed Ruff version and repository configuration.",
                "This executor runs both `ruff check` and `ruff format --check`.",
            ],
        )
