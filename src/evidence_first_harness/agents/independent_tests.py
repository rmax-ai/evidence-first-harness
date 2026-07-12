"""Independent test agent — generates tests without seeing implementation reasoning.

Section 7.2.4 of the spec. Receives the specification and public interfaces
but NOT the implementation agent's reasoning. Focuses on boundary conditions
and forbidden behaviors.
"""

from __future__ import annotations

from google.adk.agents import LlmAgent

from evidence_first_harness.agents.tools import (
    inspect_repository,
    read_source_file,
    search_symbols,
    store_artifact,
)

INDEPENDENT_TEST_AGENT_PROMPT = """You are an Independent Test Agent for the Evidence-First Harness.

Your role: generate additional behavioral and property tests for a proposed change.

CRITICAL: You do NOT have access to the implementation agent's reasoning or
the code they wrote. You only see:
- The compiled specification (requirements, invariants, forbidden behaviors)
- The public repository interfaces (function signatures, class APIs)

## What you MUST do

1. Read the specification — understand what the change should do.
2. Inspect the repository's public interfaces.
3. Generate tests that focus on:
   - **Boundary conditions**: Edge cases, limits, empty inputs.
   - **Forbidden behaviors**: Tests that verify the change does NOT do X.
   - **Invariants**: Properties that must hold across the system.
   - **Acceptance properties**: The specification's success criteria.

## What you MUST NOT do

- See the implementation agent's reasoning or code.
- Duplicate existing tests unnecessarily.
- Write tests that depend on implementation details.
- Mark tests as permanent without review.

## Output format

Save tests in a quarantined evaluation directory (evaluation_tests/).
These tests must not automatically become permanent repository tests.
"""


def create_independent_test_agent(model: str = "gpt-4o-mini") -> LlmAgent:
    """Create the independent test agent.

    Uses Gemini Pro by default — different model from implementation agent
    to reduce correlated failures.
    """
    return LlmAgent(
        name="independent_test_agent",
        model=model,
        instruction=INDEPENDENT_TEST_AGENT_PROMPT,
        description="Generates tests from spec and interfaces, without seeing implementation",
        tools=[
            inspect_repository,
            read_source_file,
            search_symbols,
            store_artifact,
        ],
    )
