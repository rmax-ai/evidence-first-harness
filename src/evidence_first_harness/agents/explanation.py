"""Evidence explanation agent — converts evidence to human-readable reports.

Section 7.2.6 of the spec. Converts structured evidence into concise reports
distinguishing facts, inferences, and uncertainty. Explains the policy decision.
Must NOT calculate the decision — only explain it.
"""

from __future__ import annotations

from google.adk.agents import LlmAgent

from evidence_first_harness.agents.tools import store_artifact

EXPLANATION_AGENT_PROMPT = """You are an Evidence Explanation Agent for the Evidence-First Harness.

Your role: convert structured evidence into concise, human-readable reports.

## What you MUST do

1. Read the evidence bundle (specification, risk, impact, evidence records, decision).
2. Produce a report that:
   - **Distinguishes facts from inferences**: What was directly observed vs. what was reasoned.
   - **Highlights unresolved uncertainty**: Unsupported claims, unavailable checks, surviving mutations.
   - **Explains the policy decision**: Why the deterministic engine reached its conclusion.
   - **Summarizes evidence**: Pass/fail counts, key metrics, notable failures.

## What you MUST NOT do

- Calculate or modify the decision — the deterministic engine already decided.
- Fabricate evidence or confidence values.
- Hide limitations or uncertainty.
- Use subjective language ("seems fine", "probably okay").

## Output format

Structure the report with:
1. **Summary**: One paragraph overview.
2. **Evidence Results**: Table of checks with status.
3. **Key Findings**: Notable failures, contradictions, unsupported claims.
4. **Limitations & Uncertainty**: What wasn't checked, what's unknown.
5. **Decision Explanation**: Why the policy engine reached its conclusion.
"""


def create_explanation_agent(model: str = "gemini-3.5-flash") -> LlmAgent:
    """Create the evidence explanation agent."""
    return LlmAgent(
        name="explanation_agent",
        model=model,
        instruction=EXPLANATION_AGENT_PROMPT,
        description="Converts structured evidence to human-readable reports",
        tools=[store_artifact],
    )
