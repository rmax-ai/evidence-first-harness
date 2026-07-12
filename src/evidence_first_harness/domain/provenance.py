"""Provenance domain model.

Section 19 of the Evidence-First Harness specification.

Append-only event stream with hash chaining for tamper detection.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ProvenanceEvent(BaseModel):
    """A single provenance event in the append-only chain."""

    model_config = {"extra": "forbid", "frozen": True}

    event_id: str = Field(..., pattern=r"^evt_[a-z0-9]+$")
    run_id: str = Field(..., pattern=r"^run_[a-z0-9]+$")
    timestamp: datetime
    actor_type: str = Field(..., min_length=1)  # "agent", "tool", "human", "system"
    actor_id: str = Field(..., min_length=1)
    model: str | None = None
    action: str = Field(..., min_length=1)
    input_digest: str = Field(..., min_length=1)
    output_digest: str = Field(..., min_length=1)
    tool: str | None = None
    authorization: str | None = None
    previous_event_digest: str = Field(..., min_length=1)
