"""Secret scanning evidence executor."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from evidence_first_harness.domain.evidence import EvidenceRecord, EvidenceRequirement

if TYPE_CHECKING:
    from evidence_first_harness.evidence.executors.base import EvidenceExecutionContext

_EXCLUDED_DIRECTORIES = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    ".mypy_cache",
    ".pytest_cache",
}
_EXCLUDED_PATH_PARTS = {("tests", "fixtures")}
_MAX_FILE_SIZE_BYTES = 1_000_000
_SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "api_key",
        re.compile(r"(?i)\b(api[_-]?key|secret[_-]?key)\b\s*[:=]\s*['\"][^'\"]{8,}['\"]"),
    ),
    (
        "token",
        re.compile(
            r"(?i)\b(access[_-]?token|auth[_-]?token|bearer[_-]?token|token)\b\s*[:=]\s*['\"][^'\"]{8,}['\"]"
        ),
    ),
    (
        "password",
        re.compile(r"(?i)\b(password|passwd|pwd)\b\s*[:=]\s*['\"][^'\"]{8,}['\"]"),
    ),
    (
        "aws_access_key",
        re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    ),
    (
        "github_token",
        re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    ),
)


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


def _should_exclude(path: Path, worktree_path: Path) -> bool:
    try:
        relative_parts = path.relative_to(worktree_path).parts
    except ValueError:
        return True

    if any(part in _EXCLUDED_DIRECTORIES for part in relative_parts):
        return True
    return relative_parts[:2] in _EXCLUDED_PATH_PARTS


def _looks_textual(path: Path) -> bool:
    try:
        with path.open("rb") as file_handle:
            sample = file_handle.read(2048)
    except OSError:
        return False
    return b"\x00" not in sample


def _regex_secret_count(worktree_path: Path) -> int:
    findings = 0
    for file_path in worktree_path.rglob("*"):
        if not file_path.is_file() or _should_exclude(file_path, worktree_path):
            continue
        try:
            if file_path.stat().st_size > _MAX_FILE_SIZE_BYTES:
                continue
        except OSError:
            continue
        if not _looks_textual(file_path):
            continue
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for _, pattern in _SECRET_PATTERNS:
            findings += len(pattern.findall(content))
    return findings


class SecretScanExecutor:
    """Run gitleaks when available and fall back to basic regex scanning."""

    name = "secrets"

    async def execute(
        self,
        context: EvidenceExecutionContext,
        requirement: EvidenceRequirement,
    ) -> EvidenceRecord:
        """Execute secret scanning for the target worktree."""
        started_at = datetime.now(UTC)
        gitleaks_path = getattr(context, "gitleaks_path", "gitleaks")
        limitations: list[str] = []

        if shutil.which(gitleaks_path) is not None:
            command = [
                gitleaks_path,
                "detect",
                "--source",
                ".",
                "--no-git",
                "--report-format",
                "json",
                "--report-path",
                "-",
            ]
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
                    summary="gitleaks execution timed out",
                    exit_code=None,
                    metrics={"secrets_found": 0},
                    limitations=[
                        f"Execution exceeded timeout of {context.timeout_seconds} seconds."
                    ],
                )

            completed_at = datetime.now(UTC)
            findings = 0
            report_output = result.stdout.strip() or result.stderr.strip()
            if report_output:
                try:
                    parsed_output = json.loads(report_output)
                    if isinstance(parsed_output, list):
                        findings = len(parsed_output)
                except json.JSONDecodeError:
                    limitations.append(
                        "gitleaks output was not valid JSON; findings count may be incomplete."
                    )

            status = "pass" if findings == 0 and result.returncode == 0 else "fail"
            summary = (
                "Secret scan passed with no findings"
                if status == "pass"
                else "Secret scan reported potential secrets"
            )
            limitations.append("gitleaks results depend on the installed rule set and version.")
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
                metrics={"secrets_found": findings},
                limitations=limitations,
            )

        command = ["regex-secret-scan"]
        findings = _regex_secret_count(context.worktree_path)
        completed_at = datetime.now(UTC)
        status = "pass" if findings == 0 else "fail"
        summary = (
            "Regex secret scan passed with no findings"
            if status == "pass"
            else "Regex secret scan reported potential hardcoded secrets"
        )
        limitations.extend(
            [
                "gitleaks was not available; used heuristic regex scanning instead.",
                "Regex scanning can miss encoded or split secrets and may produce false positives.",
            ]
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
            exit_code=0 if status == "pass" else 1,
            metrics={"secrets_found": findings},
            limitations=limitations,
        )
