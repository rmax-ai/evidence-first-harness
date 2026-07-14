"""Implementation agent — generates code in an isolated worktree.

Section 7.2.3 of the spec. The implementation agent writes code following
the approved plan, runs permitted tools, and produces a candidate patch.
It must not approve its own patch.
"""

from __future__ import annotations

from google.adk.agents import LlmAgent
from pydantic import BaseModel

from evidence_first_harness.agents.tools import (
    inspect_repository,
    read_source_file,
    search_symbols,
    store_artifact,
)

IMPLEMENTATION_AGENT_PROMPT = """You are an Implementation Agent for the Evidence-First Harness.

Your role: propose a patch for the approved plan. The harness, not you, applies
the patch in an isolated Git worktree.

## What you MUST do

1. Read the specification and implementation plan.
2. Use the repository context supplied in the request to follow existing patterns.
3. Produce a complete unified Git diff for the requested changes, including
   tests where appropriate.
4. Document any deviations from the plan.

## What you MUST NOT do

- Approve your own patch (the harness decides).
- Execute commands or claim to have modified a worktree.
- Access production credentials or external APIs.
- Skip writing tests for changed code.

## Code quality

- Follow existing repository conventions.
- Include type hints on all public interfaces.
- Handle errors explicitly — no bare except blocks.
- Write tests for new functionality.

## Output format

Return exactly one JSON object matching this schema, with no Markdown fences or
surrounding prose:

{
  "patch": "complete unified diff beginning with diff --git",
  "summary": "short description of the proposed change",
  "deviations": ["optional deviations from the plan"]
}

The `patch` field must be directly applicable by `git apply`.
"""


class ImplementationResult(BaseModel):
    """Validated implementation proposal returned by the model."""

    model_config = {"extra": "forbid", "frozen": True}

    patch: str
    summary: str
    deviations: list[str]


def create_implementation_agent(model: str = "gpt-5.6-terra") -> LlmAgent:
    """Create the implementation agent.

    Uses GPT-5.6 Terra by default for balanced patch generation.
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
