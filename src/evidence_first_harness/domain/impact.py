"""Impact report domain model.

Section 10.3 of the Evidence-First Harness specification.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from evidence_first_harness.domain.composability import ChangeShape  # noqa: TC001


class ImpactReport(BaseModel):
    """Structural impact analysis of a proposed patch."""

    model_config = {"extra": "forbid", "frozen": True}

    changed_files: list[str] = Field(default_factory=list)
    changed_symbols: list[str] = Field(default_factory=list)
    direct_dependencies: list[str] = Field(default_factory=list)
    transitive_dependencies: list[str] = Field(default_factory=list)
    affected_tests: list[str] = Field(default_factory=list)
    affected_services: list[str] = Field(default_factory=list)
    affected_data_models: list[str] = Field(default_factory=list)
    affected_interfaces: list[str] = Field(default_factory=list)
    affected_capabilities: tuple[str, ...] = ()
    change_shapes: tuple[ChangeShape, ...] = ()
    confidence: float = Field(ge=0.0, le=1.0)
    unknown_impact_areas: list[str] = Field(default_factory=list)
