"""Pyright evidence executor."""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from evidence_first_harness.domain.evidence import EvidenceRecord, EvidenceRequirement

if TYPE_CHECKING:
    from evidence_first_harness.evidence.executors.base import EvidenceExecutionContext

_PYRIGHT_SUMMARY_PATTERN = re.compile(
    r"(?P<errors>\d+)\s+error[s]?,\s+(?P<warnings>\d+)\s+warning[s]?,\s+"
    r"(?P<infos>\d+)\s+information",
)


def _build_environment(context: EvidenceExecutionContext) -> dict[str, str]:
    environment = dict(os.environ)
    environment.update(context.environment)
    return environment


def _environment_digest(context: EvidenceExecutionContext) -> str:
    payload = [
        f"worktree_path={context.worktree_path}",
        f"pyright_path={context.pyright_path}",
        f"timeout_seconds={context.timeout_seconds}",
    ]
    payload.extend(f"{key}={value}" for key, value in sorted(context.environment.items()))
    digest = hashlib.sha256("\n".join(payload).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _line_count(output: str) -> int:
    return sum(1 for line in output.splitlines() if line.strip())


def _clean_output(output: str) -> str:
    return " ".join(output.split())


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
        worktree_path = Path(context.worktree_path)
        command = [context.pyright_path]
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
                summary=f"Pyright timed out after {context.timeout_seconds} seconds.",
                metrics={},
                environment_digest=environment_digest,
                limitations=["Pyright exceeded the configured timeout."],
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
                summary=f"Pyright failed to launch: {error}.",
                metrics={},
                environment_digest=environment_digest,
                limitations=[
                    "The configured Pyright executable is unavailable in the executor environment.",
                ],
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
        if status == "pass":
            summary = "Pyright type checks passed."
        else:
            summary = "Pyright reported type checking issues."
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
                "errors": errors,
                "warnings": warnings,
                "information": infos,
                "output_lines": output_lines,
            },
            environment_digest=environment_digest,
            limitations=[
                "Pyright only evaluates statically inferrable typing issues.",
                "Results depend on the installed Pyright version and project configuration.",
            ],
        )
