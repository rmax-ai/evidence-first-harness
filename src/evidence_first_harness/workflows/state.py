"""ADK workflow state model.

Section 9 of the spec. Compact structured workflow state per ADK session.
Large outputs go to artifacts, not session state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field


# ── Per-model pricing (USD per 1M tokens) ────────────────────────────────
# Updated 2026-07. Input + output prices from official provider pages.
@dataclass(frozen=True)
class ModelPricing:
    input_per_mtok: float
    output_per_mtok: float


PRICING: dict[str, ModelPricing] = {
    # Anthropic
    "claude-opus-4-6":  ModelPricing(input_per_mtok=15.00, output_per_mtok=75.00),
    "claude-sonnet-5":  ModelPricing(input_per_mtok=3.00,  output_per_mtok=15.00),
    "claude-haiku-4-5": ModelPricing(input_per_mtok=0.80,  output_per_mtok=4.00),
    # Google
    "gemini-3.5-flash": ModelPricing(input_per_mtok=0.075, output_per_mtok=0.30),
    # DeepSeek
    "deepseek-chat":    ModelPricing(input_per_mtok=0.27,  output_per_mtok=1.10),
}


def compute_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Compute USD cost from token counts."""
    pricing = PRICING.get(model)
    if pricing is None:
        return 0.0
    return (input_tokens / 1_000_000) * pricing.input_per_mtok + (
        output_tokens / 1_000_000
    ) * pricing.output_per_mtok


def compute_cost_key(model: str, input_tokens: int, output_tokens: int) -> str:
    """Compute cost as a single decimal kwarg for structlog.

    structlog renders float32 naturally but explicit rounding to 6
    decimal places avoids float noise like 0.0059873512.
    """
    cost = compute_cost(model, input_tokens, output_tokens)
    return f"{cost:.6f}"


@dataclass(frozen=True)
class AgentCallRecord:
    """Per-agent call telemetry — accumulated in WorkflowState."""
    agent: str
    model: str
    input_tokens: int
    output_tokens: int
    duration_ms: float
    cost_usd: float  # pre-computed


class WorkflowState(BaseModel):
    """Compact workflow state for an ADK session.

    Contains only references (artifact paths), not large data.
    Full repository contents, tool logs, patches, transcripts are
    stored as artifacts and referenced by immutable IDs.
    """

    model_config = {"extra": "forbid"}

    run_id: str = Field(..., pattern=r"^run_[a-z0-9]+$")
    repository_id: str = ""
    base_commit: str = ""
    task_id: str = ""
    workflow_status: str = "started"
    current_node: str = "start"

    # Artifact references (paths/IDs, not content)
    specification_artifact: str = ""
    risk_assessment_artifact: str = ""
    implementation_plan_artifact: str = ""
    patch_artifact: str = ""
    impact_report_artifact: str = ""
    evidence_plan_artifact: str = ""
    evidence_bundle_artifact: str = ""

    # Control state
    repair_attempt: int = 0
    human_approval_status: str | None = None

    # Final decision (set by assess_evidence_sufficiency)
    final_decision: str = "unknown"

    # Node timing
    node_timings: dict[str, float] = Field(default_factory=dict)

    # Agent call telemetry
    agent_calls: list[dict[str, Any]] = Field(default_factory=list)
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0

    # Errors
    errors: list[str] = Field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dict for ADK session state."""
        return self.model_dump()

    def record_agent_call(self, record: AgentCallRecord) -> None:
        """Accumulate token + cost telemetry."""
        self.agent_calls.append({
            "agent": record.agent,
            "model": record.model,
            "input_tokens": record.input_tokens,
            "output_tokens": record.output_tokens,
            "duration_ms": record.duration_ms,
            "cost_usd": round(record.cost_usd, 6),
        })
        self.total_input_tokens += record.input_tokens
        self.total_output_tokens += record.output_tokens
        self.total_cost_usd = round(self.total_cost_usd + record.cost_usd, 6)
