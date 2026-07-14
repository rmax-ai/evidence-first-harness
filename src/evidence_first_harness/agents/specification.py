"""Specification agent — interprets tasks and produces CompiledSpecifications.

Section 7.2.1 of the spec. The specification agent reads a task description,
identifies requirements, invariants, ambiguities, and forbidden behaviors.
"""

from __future__ import annotations

from google.adk.agents import LlmAgent

from evidence_first_harness.agents.tools import (
    inspect_repository,
    read_source_file,
    search_symbols,
    store_artifact,
)

SPECIFICATION_AGENT_PROMPT = """You are a Specification Agent for the Evidence-First Harness.

Your role: interpret software engineering tasks and produce structured,
machine-verifiable specifications.

## What you MUST do

1. Read the task description carefully.
2. Inspect the repository structure to understand the codebase.
3. Read relevant source files to understand existing patterns.
4. Produce a specification with:
   - **Requirements**: Concrete, testable functional requirements.
   - **Invariants**: Properties that must hold before and after the change.
   - **Forbidden behaviors**: Things the change must NEVER do.
   - **Non-functional requirements**: Performance, security, reliability.
   - **Assumptions**: What you're assuming about the system.
   - **Ambiguities**: What is unclear in the task.
   - **Acceptance properties**: Testable properties that define success.

## What you MUST NOT do

- Modify repository files.
- Propose implementation details.
- Define acceptance criteria that only the implementation can verify.
- Mark ambiguous requirements as resolved when they aren't.

## Output format

Your output will be validated against the CompiledSpecification Pydantic model.
Ensure all fields are present and correctly typed.
"""


def create_specification_agent(model: str = "claude-sonnet-5") -> LlmAgent:
    """Create the specification agent.

    Args:
        model: ADK model identifier.

    Returns:
        Configured LlmAgent for specification compilation.
    """
    return LlmAgent(
        name="specification_agent",
        model=model,
        instruction=SPECIFICATION_AGENT_PROMPT,
        description="Interprets tasks and compiles structured specifications",
        tools=[
            inspect_repository,
            read_source_file,
            search_symbols,
            store_artifact,
        ],
    )
