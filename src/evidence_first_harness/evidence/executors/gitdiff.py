"""Git diff validation evidence executor."""

from __future__ import annotations

import asyncio
import hashlib
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from evidence_first_harness.domain.evidence import EvidenceRecord, EvidenceRequirement
from evidence_first_harness.evidence.executors.base import EvidenceExecutionContext

_DIFF_STAT_PATTERN = re.compile(
    r"(?P<files>\d+)\s+files? changed"
    r"(?:,\s+(?P<insertions>\d+)\s+insertions?\(\+\))?"
    r"(?:,\s+(?P<deletions>\d+)\s+deletions?\(-\))?"
)
_MAX_PER_FILE_LINE_CHANGES = 1000


class GitDiffExecutor:
    """Validate that a git patch is well-formed and within basic guardrails."""

    name = "git_validation"

    async def execute(
        self,
        context: EvidenceExecutionContext,
        requirement: EvidenceRequirement,
    ) -> EvidenceRecord:
        started_at = datetime.now(UTC)
        command = ["git", "diff", "HEAD~1", "--stat"]
        environment_digest = self._environment_digest(context)

        try:
            stat_result = await asyncio.to_thread(
                subprocess.run,
                command,
                cwd=context.worktree_path,
                capture_output=True,
                text=True,
                timeout=context.timeout_seconds,
                env=self._build_environment(context),
                check=False,
            )
            numstat_result = await asyncio.to_thread(
                subprocess.run,
                ["git", "diff", "HEAD~1", "--numstat"],
                cwd=context.worktree_path,
                capture_output=True,
                text=True,
                timeout=context.timeout_seconds,
                env=self._build_environment(context),
                check=False,
            )
            patch_result = await asyncio.to_thread(
                subprocess.run,
                ["git", "diff", "HEAD~1"],
                cwd=context.worktree_path,
                capture_output=True,
                text=True,
                timeout=context.timeout_seconds,
                env=self._build_environment(context),
                check=False,
            )
        except subprocess.TimeoutExpired:
            completed_at = datetime.now(UTC)
            return self._build_record(
                requirement=requirement,
                command=command,
                started_at=started_at,
                completed_at=completed_at,
                status="error",
                exit_code=None,
                summary=(f"Git diff validation timed out after {context.timeout_seconds} seconds."),
                limitations=["Git diff validation exceeded the executor timeout."],
                environment_digest=environment_digest,
            )
        except FileNotFoundError as error:
            completed_at = datetime.now(UTC)
            return self._build_record(
                requirement=requirement,
                command=command,
                started_at=started_at,
                completed_at=completed_at,
                status="error",
                exit_code=None,
                summary=f"Git diff validation failed to launch: {error}.",
                limitations=["The git executable is unavailable in the executor environment."],
                environment_digest=environment_digest,
            )
        except OSError as error:
            completed_at = datetime.now(UTC)
            return self._build_record(
                requirement=requirement,
                command=command,
                started_at=started_at,
                completed_at=completed_at,
                status="error",
                exit_code=None,
                summary=f"Git diff validation failed to execute: {error}.",
                environment_digest=environment_digest,
            )

        completed_at = datetime.now(UTC)
        if stat_result.returncode != 0:
            return self._build_record(
                requirement=requirement,
                command=command,
                started_at=started_at,
                completed_at=completed_at,
                status="error",
                exit_code=stat_result.returncode,
                summary=self._summarize_git_failure("git diff --stat failed", stat_result.stderr),
                environment_digest=environment_digest,
            )

        if numstat_result.returncode != 0:
            return self._build_record(
                requirement=requirement,
                command=command,
                started_at=started_at,
                completed_at=completed_at,
                status="error",
                exit_code=numstat_result.returncode,
                summary=self._summarize_git_failure(
                    "git diff --numstat failed", numstat_result.stderr
                ),
                environment_digest=environment_digest,
            )

        if patch_result.returncode != 0:
            return self._build_record(
                requirement=requirement,
                command=command,
                started_at=started_at,
                completed_at=completed_at,
                status="error",
                exit_code=patch_result.returncode,
                summary=self._summarize_git_failure(
                    "git diff failed while generating the patch", patch_result.stderr
                ),
                environment_digest=environment_digest,
            )

        parsed_stat = self._parse_diff_stat(stat_result.stdout)
        if parsed_stat is None:
            return self._build_record(
                requirement=requirement,
                command=command,
                started_at=started_at,
                completed_at=completed_at,
                status="error",
                exit_code=stat_result.returncode,
                summary="Git diff --stat completed but its summary line could not be parsed.",
                limitations=["Expected git diff --stat to report files changed and line counts."],
                environment_digest=environment_digest,
            )

        files_changed, insertions, deletions = parsed_stat
        binary_files, oversized_files = self._parse_numstat(numstat_result.stdout)
        apply_check = await self._run_apply_check(
            context=context,
            patch=patch_result.stdout,
        )

        metrics: dict[str, float | int | str] = {
            "files_changed": files_changed,
            "insertions": insertions,
            "deletions": deletions,
            "binary_files": len(binary_files),
        }
        if oversized_files:
            metrics["oversized_files"] = len(oversized_files)

        status = "pass"
        summary_parts = [
            f"Git diff covers {files_changed} files with {insertions} insertions and {deletions} deletions."
        ]
        limitations: list[str] = []

        if binary_files:
            status = "fail"
            summary_parts.append(f"Binary files changed: {', '.join(binary_files[:5])}.")

        if oversized_files:
            status = "fail"
            summary_parts.append(
                "Files over the line-change threshold: "
                + ", ".join(f"{path} ({changes} lines)" for path, changes in oversized_files[:5])
                + "."
            )
            limitations.append(f"Per-file line-change threshold is {_MAX_PER_FILE_LINE_CHANGES}.")

        if apply_check.returncode != 0:
            status = "fail"
            summary_parts.append(
                f"Patch reverse-apply check failed: {self._clean_text(apply_check.stderr)}."
            )

        if status == "pass":
            summary_parts.append(
                "Patch statistics, size guardrails, and reverse-apply check passed."
            )

        return self._build_record(
            requirement=requirement,
            command=command,
            started_at=started_at,
            completed_at=completed_at,
            status=status,
            exit_code=apply_check.returncode if status == "fail" else stat_result.returncode,
            summary=" ".join(summary_parts),
            metrics=metrics,
            limitations=limitations,
            environment_digest=environment_digest,
        )

    async def _run_apply_check(
        self,
        context: EvidenceExecutionContext,
        patch: str,
    ) -> subprocess.CompletedProcess[str]:
        return await asyncio.to_thread(
            subprocess.run,
            ["git", "apply", "--check", "--reverse", "-"],
            cwd=context.worktree_path,
            input=patch,
            capture_output=True,
            text=True,
            timeout=context.timeout_seconds,
            env=self._build_environment(context),
            check=False,
        )

    @staticmethod
    def _parse_diff_stat(output: str) -> tuple[int, int, int] | None:
        for line in reversed(output.splitlines()):
            match = _DIFF_STAT_PATTERN.search(line.strip())
            if match is None:
                continue
            return (
                int(match.group("files")),
                int(match.group("insertions") or 0),
                int(match.group("deletions") or 0),
            )
        return None

    @staticmethod
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
            if total_changes > _MAX_PER_FILE_LINE_CHANGES:
                oversized_files.append((file_path, total_changes))

        return binary_files, oversized_files

    @staticmethod
    def _build_environment(context: EvidenceExecutionContext) -> dict[str, str]:
        return dict(context.environment)

    @staticmethod
    def _environment_digest(context: EvidenceExecutionContext) -> str:
        entries = [
            f"python_path={context.python_path}",
            f"ruff_path={context.ruff_path}",
            f"pyright_path={context.pyright_path}",
            f"pytest_path={context.pytest_path}",
            f"timeout_seconds={context.timeout_seconds}",
        ]
        entries.extend(f"{key}={value}" for key, value in sorted(context.environment.items()))
        digest = hashlib.sha256("\n".join(entries).encode("utf-8")).hexdigest()
        return f"sha256:{digest}"

    @staticmethod
    def _summarize_git_failure(prefix: str, stderr: str) -> str:
        detail = GitDiffExecutor._clean_text(stderr)
        if detail:
            return f"{prefix}: {detail}."
        return f"{prefix}."

    @staticmethod
    def _clean_text(value: str) -> str:
        return " ".join(value.split())

    def _build_record(
        self,
        requirement: EvidenceRequirement,
        command: list[str],
        started_at: datetime,
        completed_at: datetime,
        status: str,
        exit_code: int | None,
        summary: str,
        metrics: dict[str, float | int | str] | None = None,
        limitations: list[str] | None = None,
        environment_digest: str = "",
    ) -> EvidenceRecord:
        return EvidenceRecord(
            id=f"{requirement.id}_{self.name}",
            requirement_id=requirement.id,
            status=status,
            executor=self.name,
            command=command,
            started_at=started_at,
            completed_at=completed_at,
            exit_code=exit_code,
            summary=summary,
            metrics=metrics or {},
            environment_digest=environment_digest,
            limitations=limitations or [],
        )
