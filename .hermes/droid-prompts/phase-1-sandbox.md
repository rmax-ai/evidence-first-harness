IMPLEMENT the Docker sandbox module for the Evidence-First Harness.

## Project Context

Evidence-First Harness executes untrusted repository code inside disposable Docker containers. The sandbox module manages container lifecycle, enforces security constraints, and provides a validated command execution interface.

## Requirements

Create these 3 files:

### 1. `src/evidence_first_harness/sandbox/docker.py`

DockerSandbox — manages ephemeral Docker containers for running evidence executors and agent code in isolation.

Must support:
- Creating a container from a configurable image
- Mounting a worktree directory as read-only or read-write
- Setting CPU and memory limits
- Setting network mode (disabled, proxy, full)
- Non-root user inside the container
- Timeout enforcement
- Output size limits
- Capturing stdout/stderr
- Cleaning up containers after use

### 2. `src/evidence_first_harness/sandbox/permissions.py`

SandboxPermissions — defines and enforces what operations are allowed inside the sandbox.

Must support:
- File system: read-only base, writable temp area
- Network: allowlist for package installation proxies
- Environment variables: explicit allowlist only
- No host Docker socket access
- No production credentials

### 3. `src/evidence_first_harness/sandbox/commands.py`

CommandValidator — validates commands before they run inside the sandbox.

Must support:
- Command allowlist (only approved tools)
- Argument validation
- Path traversal prevention
- No shell metacharacters or injection vectors
- Timeout per command

## Key Design Constraints

- Use the `docker` Python SDK (`import docker`)
- All execution MUST pass through validated commands — no arbitrary shell
- Repository content is untrusted data
- Containers must be ephemeral and disposable
- Use `asyncio` for async container operations
- Log all container lifecycle events with structlog
- Handle Docker daemon unavailability gracefully

## DockerSandbox API

```python
class DockerSandbox:
    def __init__(self, image: str = "evidence-first-harness-sandbox:latest"):
        ...

    async def create(
        self,
        worktree_path: Path,
        network_mode: str = "disabled",
        cpu_limit: float = 2.0,
        memory_limit: str = "2g",
        read_only: bool = True,
        timeout_seconds: int = 300,
    ) -> str:
        """Create container, return container_id."""
        ...

    async def exec_command(
        self,
        container_id: str,
        command: list[str],
        timeout_seconds: int = 120,
    ) -> CommandResult:
        """Execute a validated command inside the container."""
        ...

    async def copy_out(self, container_id: str, src: str, dest: Path) -> None:
        """Copy a file or directory out of the container."""
        ...

    async def destroy(self, container_id: str) -> None:
        """Stop and remove the container."""
        ...

@dataclass
class CommandResult:
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: float
    timed_out: bool
```

## Dependencies

The project uses:
- Python 3.12+
- `docker` package (already in pyproject.toml)
- `structlog` for logging
- `asyncio` for async operations
- Pydantic v2 for data models

## Conventions

- `from __future__ import annotations` in all modules
- Structlog: `logger.info("event_name", key=value)` — never f-strings in log calls
- Use `from evidence_first_harness.domain.exceptions import SandboxError` for errors
- All async methods return awaitables
- Type hints on all public interfaces

## Verification

After writing all 3 files:
```bash
cd ~/src/rmax-ai/evidence-first-harness && uv run python3 -c "
from evidence_first_harness.sandbox.docker import DockerSandbox, CommandResult
from evidence_first_harness.sandbox.permissions import SandboxPermissions
from evidence_first_harness.sandbox.commands import CommandValidator
print('All sandbox modules import successfully')
"
```

If Docker is available:
```bash
python3 -c "
import asyncio
from evidence_first_harness.sandbox.docker import DockerSandbox

async def test():
    sandbox = DockerSandbox()
    print(f'Sandbox created with image: {sandbox._image}')
    # Don't actually create container in verification
    print('Docker SDK available')

asyncio.run(test())
"
```

Run ruff format + ruff check after writing files.
