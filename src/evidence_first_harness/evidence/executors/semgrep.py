"""Semgrep evidence executor."""

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
        f"semgrep_path={getattr(context, 'semgrep_path', 'semgrep')}",
        f"timeout_seconds={context.timeout_seconds}",
    ]
    payload.extend(f"{key}={value}" for key, value in sorted(context.environment.items()))
    digest = hashlib.sha256("\n".join(payload).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _line_count(output: str) -> int:
    return sum(1 for line in output.splitlines() if line.strip())


def _clean_output(output: str) -> str:
    return " ".join(output.split())


class SemgrepExecutor:
    """Run Semgrep security and correctness checks."""

    name = "semgrep"

    async def execute(
        self,
        context: EvidenceExecutionContext,
        requirement: EvidenceRequirement,
    ) -> EvidenceRecord:
        """Execute Semgrep scanning for the target worktree."""
        started_at = datetime.now(UTC)
        worktree_path = Path(context.worktree_path)
        semgrep_path = getattr(context, "semgrep_path", "semgrep")
        command = [semgrep_path, "--config", "auto", "--quiet"]
        environment = _build_environment(context)
        environment_digest = _environment_digest(context)

        try:
            result = await asyncio.to_thread(
                subprocess.run,
                command,
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
                command=command,
                started_at=started_at,
                completed_at=completed_at,
                exit_code=None,
                summary=f"Semgrep timed out after {context.timeout_seconds} seconds.",
                metrics={},
                environment_digest=environment_digest,
                limitations=["Semgrep exceeded the configured timeout."],
            )
        except FileNotFoundError as error:
            completed_at = datetime.now(UTC)
            return EvidenceRecord(
                id=f"{requirement.id}_{self.name}",
                requirement_id=requirement.id,
                status="error",
                executor=self.name,
                command=command,
                started_at=started_at,
                completed_at=completed_at,
                exit_code=None,
                summary=f"Semgrep failed to launch: {error}.",
                metrics={},
                environment_digest=environment_digest,
                limitations=[
                    "The configured Semgrep executable is unavailable in the executor environment.",
                ],
            )

        completed_at = datetime.now(UTC)
        combined_output = "\n".join(part for part in (result.stdout, result.stderr) if part.strip())
        status = "pass" if result.returncode == 0 else "fail"

        if status == "pass":
            summary = "Semgrep checks passed."
        else:
            summary = "Semgrep reported findings or execution issues."
            failure_detail = _clean_output(combined_output)
            if failure_detail:
                summary = f"{summary} {failure_detail}"

        return EvidenceRecord(
            id=f"{requirement.id}_{self.name}",
            requirement_id=requirement.id,
            status=status,
            executor=self.name,
            command=command,
            started_at=started_at,
            completed_at=completed_at,
            exit_code=result.returncode,
            summary=summary,
            metrics={
                "exit_code": result.returncode,
                "output_lines": _line_count(combined_output),
            },
            environment_digest=environment_digest,
            limitations=[
                "Semgrep coverage is limited to rules selected by the auto configuration.",
                "Results depend on the installed Semgrep version, "
                "network availability, and rule corpus.",
            ],
        )
