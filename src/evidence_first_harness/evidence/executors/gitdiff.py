"""Git diff validation evidence executor."""

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

_DIFF_STAT_PATTERN = re.compile(
    r"(?P<files>\d+)\s+files? changed"
    r"(?:,\s+(?P<insertions>\d+)\s+insertions?\(\+\))?"
    r"(?:,\s+(?P<deletions>\d+)\s+deletions?\(-\))?"
)
_MAX_FILE_CHANGE_LINES = 1_000


class GitDiffExecutor:
    """Validate git patch structure and coarse size guardrails."""

    name = "gitdiff"

    async def execute(
        self,
        context: EvidenceExecutionContext,
        requirement: EvidenceRequirement,
    ) -> EvidenceRecord:
        """Validate the repository diff and summarize coarse patch health checks."""
        started_at = datetime.now(UTC)
        command = ["git", "diff", "HEAD~1", "--stat"]
        environment_digest = _environment_digest(context)

        try:
            stat_result = await asyncio.to_thread(
                subprocess.run,
                command,
                cwd=context.worktree_path,
                capture_output=True,
                text=True,
                timeout=context.timeout_seconds,
                env=_build_environment(context),
                check=False,
            )
            numstat_result = await asyncio.to_thread(
                subprocess.run,
                ["git", "diff", "HEAD~1", "--numstat"],
                cwd=context.worktree_path,
                capture_output=True,
                text=True,
                timeout=context.timeout_seconds,
                env=_build_environment(context),
                check=False,
            )
            patch_result = await asyncio.to_thread(
                subprocess.run,
                ["git", "diff", "HEAD~1"],
                cwd=context.worktree_path,
                capture_output=True,
                text=True,
                timeout=context.timeout_seconds,
                env=_build_environment(context),
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
                status="error",
                exit_code=None,
                summary=f"Git diff validation timed out after {context.timeout_seconds} seconds.",
                environment_digest=environment_digest,
                limitations=["Git diff validation exceeded the executor timeout."],
            )
        except FileNotFoundError as error:
            completed_at = datetime.now(UTC)
            return _build_record(
                requirement=requirement,
                executor=self.name,
                command=command,
                started_at=started_at,
                completed_at=completed_at,
                status="error",
                exit_code=None,
                summary=f"Git diff validation failed to launch: {_clean_text(str(error))}.",
                environment_digest=environment_digest,
            )
        except OSError as error:
            completed_at = datetime.now(UTC)
            return _build_record(
                requirement=requirement,
                executor=self.name,
                command=command,
                started_at=started_at,
                completed_at=completed_at,
                status="error",
                exit_code=None,
                summary=f"Git diff validation failed to execute: {_clean_text(str(error))}.",
                environment_digest=environment_digest,
            )

        completed_at = datetime.now(UTC)
        for label, result in (
            ("git diff --stat", stat_result),
            ("git diff --numstat", numstat_result),
            ("git diff", patch_result),
        ):
            if result.returncode != 0:
                return _build_record(
                    requirement=requirement,
                    executor=self.name,
                    command=command,
                    started_at=started_at,
                    completed_at=completed_at,
                    status="error",
                    exit_code=result.returncode,
                    summary=_summarize_failure(label, result.stderr),
                    environment_digest=environment_digest,
                )

        parsed_stat = _parse_diff_stat(stat_result.stdout)
        if parsed_stat is None:
            return _build_record(
                requirement=requirement,
                executor=self.name,
                command=command,
                started_at=started_at,
                completed_at=completed_at,
                status="error",
                exit_code=stat_result.returncode,
                summary="git diff --stat completed but its summary line could not be parsed.",
                environment_digest=environment_digest,
                limitations=[
                    "Expected files changed, insertions, and deletions in git diff --stat output."
                ],
            )

        files_changed, insertions, deletions = parsed_stat
        binary_files, oversized_files = _parse_numstat(numstat_result.stdout)

        try:
            apply_result = await asyncio.to_thread(
                subprocess.run,
                ["git", "apply", "--check", "--reverse", "-"],
                cwd=context.worktree_path,
                input=patch_result.stdout,
                capture_output=True,
                text=True,
                timeout=context.timeout_seconds,
                env=_build_environment(context),
                check=False,
            )
        except subprocess.TimeoutExpired:
            return _build_record(
                requirement=requirement,
                executor=self.name,
                command=command,
                started_at=started_at,
                completed_at=datetime.now(UTC),
                status="error",
                exit_code=None,
                summary=f"git apply --check timed out after {context.timeout_seconds} seconds.",
                environment_digest=environment_digest,
            )
        except OSError as error:
            return _build_record(
                requirement=requirement,
                executor=self.name,
                command=command,
                started_at=started_at,
                completed_at=datetime.now(UTC),
                status="error",
                exit_code=None,
                summary=f"git apply --check failed to execute: {_clean_text(str(error))}.",
                environment_digest=environment_digest,
            )

        metrics: dict[str, float | int | str] = {
            "files_changed": files_changed,
            "insertions": insertions,
            "deletions": deletions,
            "binary_files": len(binary_files),
        }
        limitations: list[str] = [
            (
                "Patch apply validation uses reverse application against the current "
                "worktree to verify patch well-formedness."
            )
        ]
        summary_parts = [
            (
                f"Diff covers {files_changed} files with {insertions} insertions "
                f"and {deletions} deletions."
            )
        ]
        status = "pass"

        if binary_files:
            status = "fail"
            summary_parts.append(f"Binary files changed: {', '.join(binary_files[:5])}.")

        if oversized_files:
            status = "fail"
            metrics["oversized_files"] = len(oversized_files)
            summary_parts.append(
                "Files over the size threshold: "
                + ", ".join(
                    f"{path} ({changes} changed lines)" for path, changes in oversized_files[:5]
                )
                + "."
            )
            limitations.append(f"Per-file changed-line threshold is {_MAX_FILE_CHANGE_LINES}.")

        if apply_result.returncode != 0:
            status = "fail"
            summary_parts.append(f"Patch validation failed: {_clean_text(apply_result.stderr)}.")

        if status == "pass":
            summary_parts.append("Patch structure, size guardrails, and apply check passed.")

        return _build_record(
            requirement=requirement,
            executor=self.name,
            command=command,
            started_at=started_at,
            completed_at=completed_at,
            status=status,
            exit_code=0 if status == "pass" else apply_result.returncode,
            summary=" ".join(summary_parts),
            environment_digest=environment_digest,
            metrics=metrics,
            limitations=limitations,
        )


def _build_environment(context: EvidenceExecutionContext) -> dict[str, str] | None:
    environment = dict(context.environment)
    return environment or None


def _environment_digest(context: EvidenceExecutionContext) -> str:
    entries = [
        f"python_path={context.python_path}",
        f"ruff_path={context.ruff_path}",
        f"pyright_path={context.pyright_path}",
        f"pytest_path={context.pytest_path}",
        f"timeout_seconds={context.timeout_seconds}",
        f"worktree_path={context.worktree_path}",
    ]
    entries.extend(f"{key}={value}" for key, value in sorted(context.environment.items()))
    digest = hashlib.sha256("\n".join(entries).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _parse_diff_stat(output: str) -> tuple[int, int, int] | None:
    for line in reversed(output.splitlines()):
        match = _DIFF_STAT_PATTERN.search(line.strip())
        if match is not None:
            return (
                int(match.group("files")),
                int(match.group("insertions") or 0),
                int(match.group("deletions") or 0),
            )
    return None


def _parse_numstat(output: str) -> tuple[list[str], list[tuple[str, int]]]:
    binary_files: list[str] = []
    oversized_files: list[tuple[str, int]] = []

    for line in output.splitlines():
        parts = line.split("\t", maxsplit=2)
        if len(parts) != 3:
            continue

        insertions, deletions, file_path = parts
        if insertions == "-" or deletions == "-":
            binary_files.append(file_path)
            continue

        total_changes = int(insertions) + int(deletions)
        if total_changes > _MAX_FILE_CHANGE_LINES:
            oversized_files.append((file_path, total_changes))

    return binary_files, oversized_files


def _summarize_failure(command_name: str, stderr: str) -> str:
    detail = _clean_text(stderr)
    if detail:
        return f"{command_name} failed: {detail}."
    return f"{command_name} failed."


def _clean_text(value: str) -> str:
    return " ".join(value.split())


def _build_record(
    *,
    requirement: EvidenceRequirement,
    executor: str,
    command: list[str],
    started_at: datetime,
    completed_at: datetime,
    status: str,
    exit_code: int | None,
    summary: str,
    environment_digest: str,
    metrics: dict[str, float | int | str] | None = None,
    limitations: list[str] | None = None,
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
        metrics=metrics or {},
        environment_digest=environment_digest,
        limitations=limitations or [],
    )
