"""Repository management — Git operations, worktree creation, patch handling.

Section 13 of the spec. Manages repository intake, worktree isolation,
and patch normalization without exposing raw shell access to agents.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import structlog

from evidence_first_harness.domain.exceptions import RepositoryError

logger = structlog.get_logger()


class RepositoryManager:
    """Manages a source repository for evidence-first evaluation.

    Creates isolated Git worktrees where agents and executors operate.
    Never modifies the original repository directly.
    """

    def __init__(self, repo_path: Path | str) -> None:
        self._repo_path = Path(repo_path).resolve()
        self._validate()

    def _validate(self) -> None:
        """Verify the path is a valid Git repository."""
        if not self._repo_path.exists():
            raise RepositoryError(f"Repository path does not exist: {self._repo_path}")

        git_dir = self._repo_path / ".git"
        if not git_dir.exists():
            raise RepositoryError(f"Not a Git repository (no .git directory): {self._repo_path}")

    @property
    def repo_path(self) -> Path:
        return self._repo_path

    @property
    def base_commit(self) -> str:
        """Get the current HEAD commit hash."""
        return self._run_git(["rev-parse", "HEAD"]).strip()

    def create_worktree(self, branch_name: str | None = None) -> Worktree:
        """Create an isolated Git worktree for agent operations.

        Args:
            branch_name: Optional branch name for the worktree.
                         Defaults to a unique name based on timestamp.

        Returns:
            A Worktree object pointing to the isolated directory.
        """
        if branch_name is None:
            import time

            branch_name = f"efh-{int(time.time())}"

        worktree_dir = Path(tempfile.mkdtemp(prefix="efh-worktree-"))

        try:
            self._run_git(
                ["worktree", "add", str(worktree_dir), "-b", branch_name],
                cwd=self._repo_path,
            )
        except subprocess.CalledProcessError as e:
            worktree_dir.rmdir()
            raise RepositoryError(f"Failed to create worktree: {e}") from e

        logger.info(
            "worktree_created",
            branch=branch_name,
            path=str(worktree_dir),
            base_commit=self.base_commit,
        )

        return Worktree(worktree_dir, branch_name, self.base_commit)

    def remove_worktree(self, worktree: Worktree) -> None:
        """Remove a worktree and clean up its directory."""
        try:
            self._run_git(
                ["worktree", "remove", str(worktree.path), "--force"],
                cwd=self._repo_path,
            )
        except subprocess.CalledProcessError:
            # Worktree may already be removed; clean up the directory
            import shutil

            if worktree.path.exists():
                shutil.rmtree(worktree.path, ignore_errors=True)

        logger.info("worktree_removed", branch=worktree.branch, path=str(worktree.path))

    def get_diff(self, worktree: Worktree) -> str:
        """Get the diff between the worktree and the base commit."""
        return self._run_git(
            ["diff", worktree.base_commit, "--", "."],
            cwd=worktree.path,
        )

    def get_patch(self, worktree: Worktree) -> str:
        """Get a formatted patch from the worktree."""
        return self._run_git(
            ["format-patch", "-1", "HEAD", "--stdout"],
            cwd=worktree.path,
        )

    def normalize_patch(self, patch_content: str) -> str:
        """Normalize a patch for comparison and storage.

        Strips variable metadata like timestamps and commit hashes.
        """
        lines = patch_content.split("\n")
        normalized: list[str] = []
        for line in lines:
            if line.startswith("Date:") or line.startswith("From "):
                continue
            if line.startswith("index "):
                normalized.append("index 0000000..0000000")
                continue
            normalized.append(line)
        return "\n".join(normalized)

    def _run_git(self, args: list[str], cwd: Path | None = None, timeout: int = 30) -> str:
        """Run a git command and return stdout."""
        cmd = ["git"] + args
        try:
            result = subprocess.run(
                cmd,
                cwd=cwd or self._repo_path,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=True,
            )
            return result.stdout
        except subprocess.TimeoutExpired as e:
            raise RepositoryError(f"Git command timed out: {' '.join(args)}") from e
        except subprocess.CalledProcessError as e:
            raise RepositoryError(f"Git command failed: {' '.join(args)}\n{e.stderr}") from e


class Worktree:
    """An isolated Git worktree for agent operations."""

    def __init__(self, path: Path, branch: str, base_commit: str) -> None:
        self.path = path
        self.branch = branch
        self.base_commit = base_commit

    def commit(self, message: str) -> str:
        """Stage all changes and commit in the worktree.

        Returns the new commit hash.
        """
        try:
            subprocess.run(
                ["git", "add", "-A"],
                cwd=self.path,
                capture_output=True,
                text=True,
                timeout=30,
                check=True,
            )
            result = subprocess.run(
                ["git", "commit", "-m", message],
                cwd=self.path,
                capture_output=True,
                text=True,
                timeout=30,
                check=True,
            )
            # Get the new commit hash
            hash_result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.path,
                capture_output=True,
                text=True,
                timeout=10,
                check=True,
            )
            return hash_result.stdout.strip()
        except subprocess.CalledProcessError as e:
            raise RepositoryError(f"Commit failed: {e.stderr}") from e

    def __repr__(self) -> str:
        return f"Worktree({self.branch}, {self.base_commit[:8]})"
