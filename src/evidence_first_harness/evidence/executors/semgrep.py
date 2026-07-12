"""Semgrep evidence executor."""

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
        semgrep_path = getattr(context, "semgrep_path", "semgrep")
        command = [semgrep_path, "--config", "auto", "--quiet"]

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
        completed_at = datetime.now(UTC)

        combined_output = "\n".join(part for part in (result.stdout, result.stderr) if part.strip())
        findings = _line_count(combined_output)
        status = "pass" if result.returncode == 0 else "fail"
        summary = (
            "Semgrep checks passed"
            if status == "pass"
            else "Semgrep reported findings or execution issues"
        )

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
                "output_lines": findings,
            },
            environment_digest=_environment_digest(context.environment),
            limitations=[
                "Semgrep coverage is limited to rules selected by the auto configuration.",
                "Results depend on the installed Semgrep version, network availability, "
                "and rule corpus.",
            ],
        )
