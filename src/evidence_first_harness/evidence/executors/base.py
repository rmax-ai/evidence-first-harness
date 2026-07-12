"""Evidence executor protocol and execution context.

All evidence executors implement this protocol. The harness discovers executors
via registration and runs them in cost order with parallel execution where safe.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from evidence_first_harness.domain.evidence import EvidenceRecord, EvidenceRequirement


class EvidenceExecutor(Protocol):
    """Protocol for all evidence executors.

    Each executor runs a single check type against a repository in a sandbox
    and returns a structured EvidenceRecord.
    """

    name: str

    async def execute(
        self,
        context: EvidenceExecutionContext,
        requirement: EvidenceRequirement,
    ) -> EvidenceRecord:
        """Execute this evidence check and return a record."""
        ...


@dataclass
class EvidenceExecutionContext:
    """Context passed to every evidence executor at runtime.

    Contains repository info, sandbox handles, and tool paths — everything
    an executor needs to run without importing harness internals.
    """

    worktree_path: Path
    sandbox_id: str | None = None
    python_path: str = "python3"
    ruff_path: str = "ruff"
    pyright_path: str = "pyright"
    pytest_path: str = "pytest"
    environment: dict[str, str] = field(default_factory=dict)
    timeout_seconds: int = 120

    @property
    def started_at(self) -> datetime:
        return datetime.now(UTC)


# Avoid circular import — EvidenceRequirement and EvidenceRecord are imported
# at function-call time in the executors, not at module level.
# This keeps the protocol importable by executors without pulling in all domain models.
