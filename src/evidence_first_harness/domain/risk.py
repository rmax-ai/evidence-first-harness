"""Risk assessment domain model.

Section 10.2 of the Evidence-First Harness specification.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class RiskDimension(BaseModel):
    """Assessment of a single risk dimension."""

    model_config = {"extra": "forbid", "frozen": True}

    level: Literal["low", "medium", "high", "critical"]
    rationale: str = Field(..., min_length=1)
    evidence: list[str] = Field(default_factory=list)


class RiskAssessment(BaseModel):
    """Complete risk assessment for a proposed change.

    Tier interpretation:
    - Tier 1: high-risk, explicit specialist approval
    - Tier 2: human review before merge
    - Tier 3: eligible for automated acceptance after evidence sufficiency
    """

    model_config = {"extra": "forbid", "frozen": True}

    regulatory_impact: RiskDimension
    customer_proximity: RiskDimension
    reversibility: RiskDimension
    data_sensitivity: RiskDimension
    operational_blast_radius: RiskDimension
    security_impact: RiskDimension
    repository_uncertainty: RiskDimension
    overall_tier: Literal[1, 2, 3]
    required_approval_roles: list[str] = Field(default_factory=list)
