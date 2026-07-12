IMPLEMENT the following evidence executors for the Evidence-First Harness.

## Project Context

Evidence-First Harness is a deterministic assurance system for AI-generated code. Evidence executors are deterministic Python classes that run checks against a repository and return structured EvidenceRecords.

## Requirements

Create these 2 files:

### 1. `src/evidence_first_harness/evidence/executors/mutation.py`
MutationExecutor — runs mutmut mutation testing. Parses killed/survived counts.

### 2. `src/evidence_first_harness/evidence/executors/gitdiff.py`
GitDiffExecutor — validates the git patch is well-formed, checks for large changes, binary files.

## EvidenceExecutor Protocol (from base.py)

```python
class EvidenceExecutor(Protocol):
    name: str

    async def execute(
        self,
        context: EvidenceExecutionContext,
        requirement: EvidenceRequirement,
    ) -> EvidenceRecord:
        ...
```

## EvidenceExecutionContext

```python
@dataclass
class EvidenceExecutionContext:
    worktree_path: Path
    sandbox_id: str | None = None
    python_path: str = "python3"
    ruff_path: str = "ruff"
    pyright_path: str = "pyright"
    pytest_path: str = "pytest"
    environment: dict[str, str] = field(default_factory=dict)
    timeout_seconds: int = 120
```

## EvidenceRecord

```python
class EvidenceRecord(BaseModel):
    model_config = {"extra": "forbid", "frozen": True}
    id: str
    requirement_id: str
    status: Literal["pass", "fail", "partial", "error", "unavailable"]
    executor: str
    command: list[str] | None = None
    started_at: datetime
    completed_at: datetime
    exit_code: int | None = None
    summary: str = ""
    metrics: dict[str, float | int | str] = Field(default_factory=dict)
    artifact_ids: list[str] = Field(default_factory=list)
    artifact_digests: list[str] = Field(default_factory=list)
    environment_digest: str = ""
    limitations: list[str] = Field(default_factory=list)
```

## MutationExecutor

- Run: `[context.python_path, "-m", "mutmut", "run", "--paths-to-mutate", str(context.worktree_path / "src")]`
- Parse: "N killed, M survived, X timeout"
- If mutmut not installed, mark "unavailable"
- Timeout after context.timeout_seconds (mutation testing can be slow)
- Metrics: {"mutants_killed": N, "mutants_survived": M, "mutants_total": N+M, "mutation_score": N/(N+M)}

## GitDiffExecutor

- Run: `git diff HEAD~1 --stat` in the worktree
- Parse: files changed, insertions, deletions
- Check: no binary files changed, no files over a reasonable size threshold
- Check: the patch applies cleanly (git apply --check)
- Metrics: {"files_changed": N, "insertions": N, "deletions": N, "binary_files": N}

## Implementation

Use `import subprocess`, `from pathlib import Path`, `from __future__ import annotations`. Each executor runs in the worktree directory. Handle subprocess errors gracefully — return "error" status with the error message in summary.

## Verification

```bash
cd ~/src/rmax-ai/evidence-first-harness && uv run python3 -c "
from evidence_first_harness.evidence.executors.mutation import MutationExecutor
from evidence_first_harness.evidence.executors.gitdiff import GitDiffExecutor
print('All executors import successfully')
print(f'Mutation: {MutationExecutor().name}')
print(f'GitDiff: {GitDiffExecutor().name}')
"
```

Run ruff format + ruff check after writing files.
