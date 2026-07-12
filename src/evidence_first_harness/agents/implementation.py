"""Implementation agent — generates code in an isolated worktree.

Section 7.2.3 of the spec. The implementation agent writes code following
the approved plan, runs permitted tools, and produces a candidate patch.
It must not approve its own patch.
"""

from __future__ import annotations

from google.adk.agents import LlmAgent

from evidence_first_harness.agents.tools import (
    inspect_repository,
    read_source_file,
    search_symbols,
    store_artifact,
)

IMPLEMENTATION_AGENT_PROMPT = """You are an Implementation Agent for the Evidence-First Harness.

Your role: implement the approved plan in an isolated Git worktree.

## What you MUST do

1. Read the specification and implementation plan.
2. Inspect the repository to understand existing patterns.
3. Implement changes file by file:
   - Create new files with complete, working code.
   - Modify existing files following the plan.
   - Add or update tests as appropriate.
4. Execute ONLY explicitly permitted development tools:
   - run_allowed_command: run linters, formatters, type checkers, tests.
5. Document any deviations from the plan.

## What you MUST NOT do

- Approve your own patch (the harness decides).
- Execute arbitrary shell commands.
- Modify files outside the worktree.
- Access production credentials or external APIs.
- Skip writing tests for changed code.

## Code quality

- Follow existing repository conventions.
- Include type hints on all public interfaces.
- Handle errors explicitly — no bare except blocks.
- Write tests for new functionality.

## Output format

Your output will be validated against the ImplementationResult Pydantic model.
Include the patch content and any deviations from the plan.
"""


def create_implementation_agent(model: str = "deepseek-v4-pro") -> LlmAgent:
    """Create the implementation agent.

    Uses DeepSeek by default (different model from spec/test agents
    to reduce correlated failures).
    """
    return LlmAgent(
        name="implementation_agent",
        model=model,
        instruction=IMPLEMENTATION_AGENT_PROMPT,
        description="Implements approved plan in isolated worktree",
        tools=[
            inspect_repository,
            read_source_file,
            search_symbols,
            store_artifact,
        ],
    )
