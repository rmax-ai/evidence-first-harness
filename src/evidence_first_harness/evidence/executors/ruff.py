"""Ruff evidence executor."""

from __future__ import annotations

import asyncio
import hashlib
import subprocess
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from evidence_first_harness.domain.evidence import EvidenceRecord, EvidenceRequirement

if TYPE_CHECKING:
    from evidence_first_harness.evidence.executors.base import EvidenceExecutionContext


def _environment_digest(environment: dict[str, str]) -> str:
    payload = "\n".join(f"{key}={value}" for key, value in sorted(environment.items()))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _line_count(output: str) -> int:
    return sum(1 for line in output.splitlines() if line.strip())


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
        check_command = [context.ruff_path, "check", "."]
        format_command = [context.ruff_path, "format", "--check", "."]

        check_result = await asyncio.to_thread(
            subprocess.run,
            check_command,
            capture_output=True,
            text=True,
            cwd=context.worktree_path,
            env=context.environment or None,
            timeout=context.timeout_seconds,
            check=False,
        )
        format_result = await asyncio.to_thread(
            subprocess.run,
            format_command,
            capture_output=True,
            text=True,
            cwd=context.worktree_path,
            env=context.environment or None,
            timeout=context.timeout_seconds,
            check=False,
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
        summary = (
            "Ruff lint and format checks passed"
            if status == "pass"
            else "Ruff reported lint or formatting violations"
        )

        return EvidenceRecord(
            id=f"{requirement.id}_{self.name}",
            requirement_id=requirement.id,
            status=status,
            executor=self.name,
            command=[*check_command, "&&", *format_command],
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
            environment_digest=_environment_digest(context.environment),
            limitations=[
                "Ruff only reports lint and formatting issues it is configured to detect.",
                "Results depend on the installed Ruff version and repository configuration.",
            ],
        )
