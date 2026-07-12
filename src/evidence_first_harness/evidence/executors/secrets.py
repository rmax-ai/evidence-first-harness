"""Secret scanning evidence executor."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from evidence_first_harness.domain.evidence import EvidenceRecord, EvidenceRequirement
from evidence_first_harness.evidence.executors.base import EvidenceExecutionContext

_TEXT_FILE_SUFFIXES = {
    ".env",
    ".ini",
    ".json",
    ".md",
    ".py",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
    ".cfg",
    ".conf",
    ".sh",
    ".js",
    ".ts",
}
_SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "api_key",
        re.compile(
            r"(?i)\b(api[_-]?key|secret[_-]?key)\b\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{16,}['\"]?"
        ),
    ),
    (
        "token",
        re.compile(
            r"(?i)\b(access[_-]?token|auth[_-]?token|token)\b\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{16,}['\"]?"
        ),
    ),
    (
        "password",
        re.compile(r"(?i)\b(password|passwd|pwd)\b\s*[:=]\s*['\"]?[^\s'\"#]{8,}['\"]?"),
    ),
    (
        "private_key",
        re.compile(r"-----BEGIN (RSA|DSA|EC|OPENSSH|PGP) PRIVATE KEY-----"),
    ),
)


class SecretScanExecutor:
    """Run gitleaks when available, with a deterministic regex fallback."""

    name = "secrets"

    async def execute(
        self,
        context: EvidenceExecutionContext,
        requirement: EvidenceRequirement,
    ) -> EvidenceRecord:
        """Scan the worktree for likely secrets."""
        if shutil.which("gitleaks") is not None:
            return await self._execute_gitleaks(context, requirement)
        return await self._execute_regex_scan(context, requirement, use_fallback_only=True)

    async def _execute_gitleaks(
        self,
        context: EvidenceExecutionContext,
        requirement: EvidenceRequirement,
    ) -> EvidenceRecord:
        started_at = context.started_at
        command = [
            "gitleaks",
            "detect",
            "--no-git",
            "--source",
            ".",
            "--report-format",
            "json",
            "--report-path",
            "-",
        ]
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
                summary="gitleaks timed out",
                environment_digest=_environment_digest(context),
            )
        except OSError:
            return await self._execute_regex_scan(context, requirement, use_fallback_only=True)

        findings = _parse_gitleaks_findings(result.stdout)
        if findings is None:
            return await self._execute_regex_scan(context, requirement, use_fallback_only=False)

        completed_at = datetime.now(UTC)
        secret_count = len(findings)
        status = "pass" if secret_count == 0 else "fail"
        summary = (
            "no secrets detected by gitleaks" if secret_count == 0 else "gitleaks detected secrets"
        )
        return EvidenceRecord(
            id=_record_id(requirement.id, self.name),
            requirement_id=requirement.id,
            status=status,
            executor=self.name,
            command=command,
            started_at=started_at,
            completed_at=completed_at,
            exit_code=result.returncode,
            summary=summary,
            metrics={"secrets_found": secret_count},
            environment_digest=_environment_digest(context),
        )

    async def _execute_regex_scan(
        self,
        context: EvidenceExecutionContext,
        requirement: EvidenceRequirement,
        *,
        use_fallback_only: bool,
    ) -> EvidenceRecord:
        started_at = context.started_at
        completed_at = datetime.now(UTC)
        findings = _scan_for_secrets(context.worktree_path)
        secret_count = len(findings)
        limitations = ["used regex fallback scanner instead of gitleaks"]
        if not use_fallback_only:
            limitations.append("gitleaks output could not be parsed and was ignored")

        return EvidenceRecord(
            id=_record_id(requirement.id, self.name),
            requirement_id=requirement.id,
            status="pass" if secret_count == 0 else "fail",
            executor=self.name,
            command=None,
            started_at=started_at,
            completed_at=completed_at,
            exit_code=None,
            summary="regex secret scan completed",
            metrics={"secrets_found": secret_count},
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


def _parse_gitleaks_findings(output: str) -> list[dict[str, object]] | None:
    stripped = output.strip()
    if not stripped:
        return []
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, list):
        return None
    findings: list[dict[str, object]] = []
    for item in payload:
        if isinstance(item, dict):
            findings.append(cast(dict[str, object], item))
    return findings


def _scan_for_secrets(worktree_path: Path) -> list[str]:
    findings: list[str] = []
    for path in worktree_path.rglob("*"):
        if not path.is_file():
            continue
        if _should_exclude(path, worktree_path):
            continue
        if (
            path.suffix
            and path.suffix.lower() not in _TEXT_FILE_SUFFIXES
            and not _looks_like_env_file(path)
        ):
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for _, pattern in _SECRET_PATTERNS:
            if pattern.search(content) is not None:
                findings.append(str(path.relative_to(worktree_path)))
                break
    return findings


def _should_exclude(path: Path, root: Path) -> bool:
    relative_parts = path.relative_to(root).parts
    return ".git" in relative_parts or "fixtures" in relative_parts


def _looks_like_env_file(path: Path) -> bool:
    return path.name.startswith(".env")


def _record_id(requirement_id: str, executor_name: str) -> str:
    return f"{requirement_id}_{executor_name}"
