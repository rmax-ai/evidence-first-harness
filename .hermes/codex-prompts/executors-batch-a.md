IMPLEMENT the following evidence executors for the Evidence-First Harness.

## Project Context

Evidence-First Harness is a deterministic assurance system for AI-generated code. Evidence executors are deterministic Python classes that run checks against a repository and return structured EvidenceRecords.

## Requirements

Create these 3 files, each implementing the EvidenceExecutor protocol:

### 1. `src/evidence_first_harness/evidence/executors/ruff.py`
RuffExecutor — runs `ruff check` and `ruff format --check`.

### 2. `src/evidence_first_harness/evidence/executors/pyright.py`
PyrightExecutor — runs `pyright`.

### 3. `src/evidence_first_harness/evidence/executors/semgrep.py`
SemgrepExecutor — runs `semgrep --config auto --quiet`.

## EvidenceExecutor Protocol

Each executor must follow this protocol (defined in `src/evidence_first_harness/evidence/executors/base.py`):

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

    @property
    def started_at(self) -> datetime:
        return datetime.now(UTC)
```

## EvidenceRecord (from domain)

```python
class EvidenceRecord(BaseModel):
    model_config = {"extra": "forbid", "frozen": True}
    id: str  # pattern r"^[a-z0-9_-]+$"
    requirement_id: str  # pattern r"^[a-z0-9_-]+$"
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

## Implementation Pattern

Each executor should:
1. Accept tool paths from context (context.ruff_path, context.pyright_path, etc.)
2. Run the command using `subprocess.run()` in the worktree directory
3. Parse output to determine pass/fail
4. Return an EvidenceRecord with:
   - status: "pass" if exit_code=0, "fail" otherwise
   - metrics: at minimum {"exit_code": exit_code}, plus tool-specific metrics
   - summary: concise result description
   - limitations: known limitations of this check
   - started_at/completed_at timestamps

Use `import subprocess` and `from pathlib import Path`. Use `from __future__ import annotations`.

## Verification

After writing the files, verify:
```bash
cd ~/src/rmax-ai/evidence-first-harness && uv run python3 -c "
from evidence_first_harness.evidence.executors.ruff import RuffExecutor
from evidence_first_harness.evidence.executors.pyright import PyrightExecutor
from evidence_first_harness.evidence.executors.semgrep import SemgrepExecutor
print('All executors import successfully')
print(f'Ruff: {RuffExecutor().name}')
print(f'Pyright: {PyrightExecutor().name}')
print(f'Semgrep: {SemgrepExecutor().name}')
"
```

Run ruff format + check after writing files.
