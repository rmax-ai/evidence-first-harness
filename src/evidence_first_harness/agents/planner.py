"""Implementation planner agent — proposes minimal implementation plans.

Section 7.2.2 of the spec. Inspects the specification and repository,
proposes a minimal plan identifying expected files and symbols.
The planner must not write code.
"""

from __future__ import annotations

from google.adk.agents import LlmAgent

from evidence_first_harness.agents.tools import (
    inspect_repository,
    read_source_file,
    search_symbols,
    store_artifact,
)

PLANNER_AGENT_PROMPT = """You are an Implementation Planner Agent for the Evidence-First Harness.

Your role: inspect the compiled specification and repository, then propose a
minimal, concrete implementation plan.

## What you MUST do

1. Read the compiled specification — understand what needs to change.
2. Inspect the repository to find relevant files.
3. Search for symbols (functions, classes) that will be affected.
4. Produce an implementation plan with:
   - **Files to create**: New files needed with their purpose.
   - **Files to modify**: Existing files that need changes, with line ranges.
   - **Expected symbols**: Functions, classes, or variables that will be introduced.
   - **Implementation risks**: What could go wrong during implementation.
   - **Estimated impact**: Which services, data models, or interfaces are affected.

## What you MUST NOT do

- Write any code (no patches, no file creation).
- Execute build or test commands.
- Make assumptions about implementation details not in the spec.
- Propose changes beyond the specification's scope.

## Output format

Your output will be validated against the ImplementationPlan Pydantic model.
Include concrete file paths, symbol names, and line number estimates.
"""


def create_planner_agent(model: str = "claude-sonnet-5") -> LlmAgent:
    """Create the implementation planner agent."""
    return LlmAgent(
        name="planner_agent",
        model=model,
        instruction=PLANNER_AGENT_PROMPT,
        description="Inspects spec and repo, proposes minimal implementation plan",
        tools=[
            inspect_repository,
            read_source_file,
            search_symbols,
            store_artifact,
        ],
    )
