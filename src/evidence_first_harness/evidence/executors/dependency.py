"""Dependency vulnerability evidence executor."""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from evidence_first_harness.domain.evidence import EvidenceRecord, EvidenceRequirement
from evidence_first_harness.evidence.executors.base import EvidenceExecutionContext


class DependencyExecutor:
    """Run pip-audit against the repository dependencies."""

    name = "dependency"

    async def execute(
        self,
        context: EvidenceExecutionContext,
        requirement: EvidenceRequirement,
    ) -> EvidenceRecord:
        """Audit dependencies for known vulnerabilities."""
        started_at = context.started_at
        audit_target = _select_audit_target(context.worktree_path)
        if audit_target is None:
            completed_at = datetime.now(UTC)
            return EvidenceRecord(
                id=_record_id(requirement.id, self.name),
                requirement_id=requirement.id,
                status="unavailable",
                executor=self.name,
                command=None,
                started_at=started_at,
                completed_at=completed_at,
                exit_code=None,
                summary="no requirements.txt or pyproject.toml found for dependency audit",
                environment_digest=_environment_digest(context),
            )

        command = [context.python_path, "-m", "pip_audit", "-f", "json"]
        if audit_target.name == "requirements.txt":
            command.extend(["-r", audit_target.name])

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
                summary="pip-audit timed out",
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
                summary=f"pip-audit could not start: {exc}",
                environment_digest=_environment_digest(context),
            )

        combined_output = "\n".join(part for part in [result.stdout, result.stderr] if part.strip())
        if _pip_audit_missing(combined_output):
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
                summary="pip-audit is not installed or not available",
                environment_digest=_environment_digest(context),
                limitations=["dependency auditing requires the pip-audit package"],
            )

        parsed = _parse_pip_audit_output(result.stdout)
        vulnerabilities_found = parsed["vulnerabilities_found"]
        vulnerabilities_critical = parsed["vulnerabilities_critical"]
        completed_at = datetime.now(UTC)

        limitations: list[str] = []
        if parsed["severity_supported"] == 0:
            limitations.append(
                "pip-audit output did not include severity levels; critical count may be zero"
            )

        return EvidenceRecord(
            id=_record_id(requirement.id, self.name),
            requirement_id=requirement.id,
            status="pass" if vulnerabilities_found == 0 else "fail",
            executor=self.name,
            command=command,
            started_at=started_at,
            completed_at=completed_at,
            exit_code=result.returncode,
            summary=_build_summary(vulnerabilities_found, vulnerabilities_critical),
            metrics={
                "vulnerabilities_found": vulnerabilities_found,
                "vulnerabilities_critical": vulnerabilities_critical,
            },
            environment_digest=_environment_digest(context),
            limitations=limitations,
        )


def _build_environment(context: EvidenceExecutionContext) -> dict[str, str]:
    environment = dict(context.environment)
    return environment


def _environment_digest(context: EvidenceExecutionContext) -> str:
    parts = [
        f"python_path={context.python_path}",
        f"timeout_seconds={context.timeout_seconds}",
        f"sandbox_id={context.sandbox_id or ''}",
    ]
    parts.extend(
        f"{key}={value}"
        for key, value in sorted(context.environment.items(), key=lambda item: item[0])
    )
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def _select_audit_target(worktree_path: Path) -> Path | None:
    requirements_path = worktree_path / "requirements.txt"
    if requirements_path.exists():
        return requirements_path
    pyproject_path = worktree_path / "pyproject.toml"
    if pyproject_path.exists():
        return pyproject_path
    return None


def _pip_audit_missing(output: str) -> bool:
    lowered = output.lower()
    return "no module named pip_audit" in lowered or "no module named pip-audit" in lowered


def _parse_pip_audit_output(output: str) -> dict[str, int]:
    stripped = output.strip()
    if not stripped:
        return {
            "vulnerabilities_found": 0,
            "vulnerabilities_critical": 0,
            "severity_supported": 0,
        }

    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        return {
            "vulnerabilities_found": 0,
            "vulnerabilities_critical": 0,
            "severity_supported": 0,
        }

    if not isinstance(payload, list):
        return {
            "vulnerabilities_found": 0,
            "vulnerabilities_critical": 0,
            "severity_supported": 0,
        }

    vulnerabilities_found = 0
    vulnerabilities_critical = 0
    severity_supported = 0

    for dependency in payload:
        if not isinstance(dependency, dict):
            continue
        vulnerabilities = dependency.get("vulns")
        if not isinstance(vulnerabilities, list):
            continue
        vulnerabilities_found += len(vulnerabilities)
        for vulnerability in vulnerabilities:
            if not isinstance(vulnerability, dict):
                continue
            severity = vulnerability.get("severity")
            if isinstance(severity, str):
                severity_supported = 1
                if severity.lower() == "critical":
                    vulnerabilities_critical += 1

    return {
        "vulnerabilities_found": vulnerabilities_found,
        "vulnerabilities_critical": vulnerabilities_critical,
        "severity_supported": severity_supported,
    }


def _build_summary(vulnerabilities_found: int, vulnerabilities_critical: int) -> str:
    if vulnerabilities_found == 0:
        return "pip-audit found no known vulnerabilities"
    return (
        "pip-audit found "
        f"{vulnerabilities_found} known vulnerabilities, "
        f"{vulnerabilities_critical} marked critical"
    )


def _record_id(requirement_id: str, executor_name: str) -> str:
    return f"{requirement_id}_{executor_name}"
