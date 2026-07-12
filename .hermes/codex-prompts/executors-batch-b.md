IMPLEMENT the following evidence executors for the Evidence-First Harness.

## Project Context

Evidence-First Harness is a deterministic assurance system for AI-generated code. Evidence executors are deterministic Python classes that run checks against a repository and return structured EvidenceRecords.

## Requirements

Create these 4 files, each implementing the EvidenceExecutor protocol:

### 1. `src/evidence_first_harness/evidence/executors/pytest.py`
PytestExecutor — runs targeted tests via pytest. Parses test counts.

### 2. `src/evidence_first_harness/evidence/executors/coverage.py`
CoverageExecutor — runs pytest with coverage. Parses coverage percentages.

### 3. `src/evidence_first_harness/evidence/executors/secrets.py`
SecretScanExecutor — runs gitleaks or basic regex secret scanning.

### 4. `src/evidence_first_harness/evidence/executors/dependency.py`
DependencyExecutor — runs pip-audit for known vulnerabilities.

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

## Implementation Pattern

For each executor:
1. Accept tool paths from context
2. Run the command using `subprocess.run()` in the worktree directory
3. Parse output to extract metrics (test pass/fail counts, coverage %, vuln count)
4. Return EvidenceRecord with structured metrics

**PytestExecutor specifics:**
- Run: `[context.pytest_path, "-q", "--tb=short"]`
- Parse the summary line: "N passed, M failed"
- Show warning if tests directory doesn't exist or is empty
- Metrics: {"tests_passed": N, "tests_failed": M, "tests_total": N+M}

**CoverageExecutor specifics:**
- Run: `[context.pytest_path, "--cov=.", "--cov-report=term", "-q"]`
- Parse coverage % from "TOTAL" line
- If pytest-cov not installed, mark "unavailable" with explanation
- Metrics: {"coverage_pct": X, "tests_passed": N, "tests_total": N}

**SecretScanExecutor specifics:**
- Check for gitleaks first, fall back to grep-based scan for common patterns
- Patterns: API keys, tokens, passwords in source files
- Exclude .git/ and test fixtures
- Metrics: {"secrets_found": N}

**DependencyExecutor specifics:**
- Run: `[context.python_path, "-m", "pip_audit", "-r", "requirements.txt"]` or check pyproject.toml
- Parse for known vulnerabilities
- If pip-audit not installed, mark "unavailable"
- Metrics: {"vulnerabilities_found": N, "vulnerabilities_critical": N}

Use `import subprocess`, `from pathlib import Path`, `from __future__ import annotations`.

## Verification

After writing all 4 files, verify imports:
```bash
cd ~/src/rmax-ai/evidence-first-harness && uv run python3 -c "
from evidence_first_harness.evidence.executors.pytest import PytestExecutor
from evidence_first_harness.evidence.executors.coverage import CoverageExecutor
from evidence_first_harness.evidence.executors.secrets import SecretScanExecutor
from evidence_first_harness.evidence.executors.dependency import DependencyExecutor
print('All executors import successfully')
for ex in [PytestExecutor(), CoverageExecutor(), SecretScanExecutor(), DependencyExecutor()]:
    print(f'{ex.name}: OK')
"
```

Run ruff format + check after writing files.
