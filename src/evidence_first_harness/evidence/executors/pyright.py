"""Pyright evidence executor."""

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

_PYRIGHT_SUMMARY_PATTERN = re.compile(
    r"(?P<errors>\d+)\s+error[s]?,\s+(?P<warnings>\d+)\s+warning[s]?,\s+"
    r"(?P<infos>\d+)\s+information",
)


def _environment_digest(environment: dict[str, str]) -> str:
    payload = "\n".join(f"{key}={value}" for key, value in sorted(environment.items()))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _line_count(output: str) -> int:
    return sum(1 for line in output.splitlines() if line.strip())


class PyrightExecutor:
    """Run Pyright static type checks."""

    name = "pyright"

    async def execute(
        self,
        context: EvidenceExecutionContext,
        requirement: EvidenceRequirement,
    ) -> EvidenceRecord:
        """Execute Pyright type checking for the target worktree."""
        started_at = datetime.now(UTC)
        command = [context.pyright_path]

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
        output_lines = _line_count(combined_output)
        errors = 0
        warnings = 0
        infos = 0
        summary_match = _PYRIGHT_SUMMARY_PATTERN.search(combined_output)
        if summary_match is not None:
            errors = int(summary_match.group("errors"))
            warnings = int(summary_match.group("warnings"))
            infos = int(summary_match.group("infos"))

        status = "pass" if result.returncode == 0 else "fail"
        summary = (
            "Pyright type checks passed"
            if status == "pass"
            else "Pyright reported type checking issues"
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
                "errors": errors,
                "warnings": warnings,
                "information": infos,
                "output_lines": output_lines,
            },
            environment_digest=_environment_digest(context.environment),
            limitations=[
                "Pyright only evaluates statically inferrable typing issues.",
                "Results depend on the installed Pyright version and project configuration.",
            ],
        )
