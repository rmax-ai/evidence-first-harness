"""Evidence domain models.

Sections 10.4, 10.5, 10.6 of the Evidence-First Harness specification.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from evidence_first_harness.domain.impact import ImpactReport
    from evidence_first_harness.domain.risk import RiskAssessment
    from evidence_first_harness.domain.specification import CompiledSpecification


class EvidenceRequirement(BaseModel):
    """A required piece of evidence linked to specific claims."""

    model_config = {"extra": "forbid", "frozen": True}

    id: str = Field(..., pattern=r"^[a-z0-9_-]+$")
    claim_ids: list[str] = Field(default_factory=list)
    evidence_type: str = Field(..., min_length=1)
    executor: str = Field(..., min_length=1)
    mandatory: bool = True
    minimum_threshold: float | None = None
    independence_class: Literal[
        "external_oracle",
        "deterministic",
        "independent_model",
        "same_model",
    ]
    failure_action: Literal["reject", "repair", "review", "warn"]


class EvidenceRecord(BaseModel):
    """A single executed piece of evidence."""

    model_config = {"extra": "forbid", "frozen": True}

    id: str = Field(..., pattern=r"^[a-z0-9_-]+$")
    requirement_id: str = Field(..., pattern=r"^[a-z0-9_-]+$")
    status: Literal["pass", "fail", "partial", "error", "unavailable"]
    executor: str = Field(..., min_length=1)
    command: list[str] | None = None
    started_at: datetime
    completed_at: datetime
    exit_code: int | None = None
    summary: str = ""
    metrics: dict[str, float | int | str] = Field(default_factory=dict)
    artifact_ids: list[str] = Field(default_factory=list)
    artifact_digests: list[str] = Field(default_factory=list)
    environment_digest: str = ""
    limitations: list[str] = Field(default_factory=list)


class EvidenceBundle(BaseModel):
    """The primary output of the harness — a validated claim-evidence-decision package.

    Not just a patch. This is the unit of work.
    """

    model_config = {"extra": "forbid", "frozen": True}

    schema_version: str = Field(default="1.0")
    run_id: str = Field(..., min_length=1)
    repository: str = Field(..., min_length=1)
    base_commit: str = Field(..., min_length=1)
    patch_commit: str | None = None
    specification: CompiledSpecification | None = None
    risk: RiskAssessment | None = None
    impact: ImpactReport | None = None
    evidence_plan: list[EvidenceRequirement] = Field(default_factory=list)
    evidence: list[EvidenceRecord] = Field(default_factory=list)
    unsupported_claims: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    provenance: dict = Field(default_factory=dict)
    sufficiency: dict = Field(default_factory=dict)
    decision: dict = Field(default_factory=dict)
