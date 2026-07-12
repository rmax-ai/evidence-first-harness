"""Dependency vulnerability evidence executor."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
import tempfile
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from evidence_first_harness.domain.evidence import EvidenceRecord, EvidenceRequirement

if TYPE_CHECKING:
    from evidence_first_harness.evidence.executors.base import EvidenceExecutionContext


def _environment_digest(environment: dict[str, str]) -> str:
    payload = "\n".join(f"{key}={value}" for key, value in sorted(environment.items()))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


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


def _requirements_file(worktree_path: Path) -> Path | None:
    requirements_path = worktree_path / "requirements.txt"
    if requirements_path.is_file():
        return requirements_path
    return None


def _pyproject_dependencies(worktree_path: Path) -> list[str]:
    pyproject_path = worktree_path / "pyproject.toml"
    if not pyproject_path.is_file():
        return []

    with pyproject_path.open("rb") as file_handle:
        data = tomllib.load(file_handle)

    project = data.get("project", {})
    raw_dependencies = project.get("dependencies", [])
    if not isinstance(raw_dependencies, list):
        return []
    return [dependency for dependency in raw_dependencies if isinstance(dependency, str)]


def _parse_vulnerability_metrics(payload: Any) -> tuple[int, int]:
    if not isinstance(payload, dict):
        return 0, 0

    critical = 0
    total = 0
    dependencies = payload.get("dependencies", [])
    if not isinstance(dependencies, list):
        return 0, 0

    for dependency in dependencies:
        if not isinstance(dependency, dict):
            continue
        vulns = dependency.get("vulns", [])
        if not isinstance(vulns, list):
            continue
        total += len(vulns)
        for vuln in vulns:
            if not isinstance(vuln, dict):
                continue
            aliases = vuln.get("aliases", [])
            description = str(vuln.get("description", ""))
            if (
                isinstance(aliases, list)
                and any("critical" in str(alias).lower() for alias in aliases)
            ) or "critical" in description.lower():
                critical += 1

    return total, critical


class DependencyExecutor:
    """Run pip-audit against a dependency manifest and parse vulnerabilities."""

    name = "dependency"

    async def execute(
        self,
        context: EvidenceExecutionContext,
        requirement: EvidenceRequirement,
    ) -> EvidenceRecord:
        """Execute pip-audit for the target worktree."""
        started_at = datetime.now(UTC)
        requirements_path = _requirements_file(context.worktree_path)
        temporary_requirements_path: str | None = None
        limitations: list[str] = []

        try:
            if requirements_path is not None:
                command = [
                    context.python_path,
                    "-m",
                    "pip_audit",
                    "--format",
                    "json",
                    "-r",
                    str(requirements_path),
                ]
            else:
                dependencies = _pyproject_dependencies(context.worktree_path)
                if not dependencies:
                    completed_at = datetime.now(UTC)
                    return _build_record(
                        requirement=requirement,
                        executor=self.name,
                        command=[context.python_path, "-m", "pip_audit"],
                        started_at=started_at,
                        completed_at=completed_at,
                        environment=context.environment,
                        status="unavailable",
                        summary="No requirements.txt or project dependencies were found to audit",
                        exit_code=None,
                        metrics={"vulnerabilities_found": 0, "vulnerabilities_critical": 0},
                        limitations=[
                            "Add requirements.txt or declare dependencies "
                            "in pyproject.toml for dependency auditing.",
                        ],
                    )

                file_descriptor, temporary_requirements_path = tempfile.mkstemp(suffix=".txt")
                os.close(file_descriptor)
                with Path(temporary_requirements_path).open("w", encoding="utf-8") as file_handle:
                    file_handle.write("\n".join(dependencies))
                command = [
                    context.python_path,
                    "-m",
                    "pip_audit",
                    "--format",
                    "json",
                    "-r",
                    temporary_requirements_path,
                ]
                limitations.append(
                    "Audited dependencies synthesized from pyproject.toml project.dependencies."
                )

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
                    summary="Python executable or pip-audit module was not found",
                    exit_code=None,
                    metrics={"vulnerabilities_found": 0, "vulnerabilities_critical": 0},
                    limitations=[
                        "Install pip-audit in the execution environment to audit dependencies."
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
                    summary="Dependency audit timed out",
                    exit_code=None,
                    metrics={"vulnerabilities_found": 0, "vulnerabilities_critical": 0},
                    limitations=[
                        f"Execution exceeded timeout of {context.timeout_seconds} seconds."
                    ],
                )

            completed_at = datetime.now(UTC)
            combined_output = "\n".join(
                part for part in (result.stdout, result.stderr) if part.strip()
            )
            lowered_output = combined_output.lower()
            if "no module named pip_audit" in lowered_output:
                return _build_record(
                    requirement=requirement,
                    executor=self.name,
                    command=command,
                    started_at=started_at,
                    completed_at=completed_at,
                    environment=context.environment,
                    status="unavailable",
                    summary="pip-audit is not installed in the execution environment",
                    exit_code=result.returncode,
                    metrics={"vulnerabilities_found": 0, "vulnerabilities_critical": 0},
                    limitations=["Install pip-audit to enable dependency vulnerability scanning."],
                )

            vulnerabilities_found = 0
            vulnerabilities_critical = 0
            if result.stdout.strip():
                try:
                    parsed_output = json.loads(result.stdout)
                    vulnerabilities_found, vulnerabilities_critical = _parse_vulnerability_metrics(
                        parsed_output
                    )
                except json.JSONDecodeError:
                    limitations.append(
                        "pip-audit output was not valid JSON; "
                        "vulnerability counts may be incomplete."
                    )

            status = "pass" if vulnerabilities_found == 0 and result.returncode == 0 else "fail"
            summary = (
                "Dependency audit passed with no known vulnerabilities"
                if status == "pass"
                else "Dependency audit reported known vulnerabilities or execution issues"
            )
            limitations.append(
                "Critical vulnerability count depends on metadata present in pip-audit output."
            )

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
                    "vulnerabilities_found": vulnerabilities_found,
                    "vulnerabilities_critical": vulnerabilities_critical,
                },
                limitations=limitations,
            )
        finally:
            if temporary_requirements_path is not None:
                Path(temporary_requirements_path).unlink(missing_ok=True)
