"""ADK workflow state model.

Section 9 of the spec. Compact structured workflow state per ADK session.
Large outputs go to artifacts, not session state.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


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

    # Node timing
    node_timings: dict[str, float] = Field(default_factory=dict)

    # Errors
    errors: list[str] = Field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dict for ADK session state."""
        return self.model_dump()
