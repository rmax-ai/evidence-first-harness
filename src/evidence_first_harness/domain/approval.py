"""Human approval domain model.

Section 18 of the Evidence-First Harness specification.

Approval binds to the exact evidence-bundle digest. A modified patch
invalidates earlier approval.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ApprovalRequest(BaseModel):
    """Request for human approval during a workflow."""

    model_config = {"extra": "forbid", "frozen": True}

    request_id: str = Field(..., pattern=r"^apr_[a-z0-9]+$")
    run_id: str = Field(..., pattern=r"^run_[a-z0-9]+$")
    evidence_bundle_id: str = Field(..., min_length=1)
    requested_role: str = Field(..., min_length=1)
    reason: str = Field(..., min_length=1)
    blocking_findings: list[str] = Field(default_factory=list)
    expires_at: datetime


class ApprovalDecision(BaseModel):
    """A human's decision on an approval request."""

    model_config = {"extra": "forbid", "frozen": True}

    request_id: str = Field(..., pattern=r"^apr_[a-z0-9]+$")
    actor_id: str = Field(..., min_length=1)
    role: str = Field(..., min_length=1)
    decision: Literal["approve", "reject", "request_changes"]
    rationale: str = Field(..., min_length=1)
    evidence_bundle_digest: str = Field(..., min_length=1)
    timestamp: datetime
