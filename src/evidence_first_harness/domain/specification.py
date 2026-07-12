"""Compiled specification domain model.

Section 10.1 of the Evidence-First Harness specification.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Requirement(BaseModel):
    """A single functional requirement derived from the task."""

    model_config = {"extra": "forbid", "frozen": True}

    id: str = Field(..., pattern=r"^[a-z0-9_-]+$")
    statement: str = Field(..., min_length=1)
    source: str = Field(..., min_length=1)
    priority: Literal["must", "should", "may"]
    verification_hint: str | None = None


class Invariant(BaseModel):
    """A property that must hold across the system."""

    model_config = {"extra": "forbid", "frozen": True}

    id: str = Field(..., pattern=r"^[a-z0-9_-]+$")
    statement: str = Field(..., min_length=1)
    scope: list[str] = Field(default_factory=list)
    severity: Literal["low", "medium", "high", "critical"]


class CompiledSpecification(BaseModel):
    """The interpreted task specification, produced by the Specification Agent.

    A specification with unresolved critical ambiguities must not proceed
    autonomously.
    """

    model_config = {"extra": "forbid", "frozen": True}

    task_id: str = Field(..., min_length=1)
    objective: str = Field(..., min_length=1)
    requirements: list[Requirement] = Field(default_factory=list)
    invariants: list[Invariant] = Field(default_factory=list)
    forbidden_behaviors: list[str] = Field(default_factory=list)
    non_functional_requirements: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    ambiguities: list[str] = Field(default_factory=list)
    acceptance_properties: list[str] = Field(default_factory=list)
    source_digest: str = Field(..., min_length=1, description="SHA-256 of the original task input")
