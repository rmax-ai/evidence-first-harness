"""Decision engine domain model.

Section 20 of the Evidence-First Harness specification.

The decision engine is deterministic. The LLM may explain the result but
cannot modify it.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class Decision(StrEnum):
    """Possible outcomes from the evidence sufficiency assessment."""

    REJECTED = "rejected"
    REPAIR_REQUIRED = "repair_required"
    HUMAN_REVIEW_REQUIRED = "human_review_required"
    SPECIALIST_APPROVAL_REQUIRED = "specialist_approval_required"
    ELIGIBLE_FOR_AUTOMATION = "eligible_for_automation"


class DecisionResult(BaseModel):
    """The deterministic decision output."""

    model_config = {"extra": "forbid", "frozen": True}

    decision: Decision
    rationale: str = Field(..., min_length=1)
    risk_tier: int = Field(ge=1, le=3)
    mandatory_evidence_passed: bool
    mandatory_evidence_count: int
    mandatory_evidence_failed: list[str] = Field(default_factory=list)
    mandatory_evidence_unavailable: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    impact_confidence: float = Field(ge=0.0, le=1.0)
    repair_attempts_remaining: int = 0
    required_approvals: list[str] = Field(default_factory=list)
