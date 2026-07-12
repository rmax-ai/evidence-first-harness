"""Domain exceptions for the Evidence-First Harness.

All harness errors inherit from HarnessError. Domain logic raises these;
FastAPI exception handlers map them to HTTP responses.
"""

from __future__ import annotations


class HarnessError(Exception):
    """Base exception for all harness errors."""


class SpecificationError(HarnessError):
    """Invalid, incomplete, or contradictory specification."""


class RiskClassificationError(HarnessError):
    """Risk assessment could not be completed."""


class BaselineValidationError(HarnessError):
    """Repository baseline checks failed."""


class ImplementationError(HarnessError):
    """Code generation or patch application failed."""


class EvidenceError(HarnessError):
    """Evidence collection or evaluation failed."""


class EvidenceFailureError(EvidenceError):
    """Mandatory evidence check failed."""


class EvidenceUnavailableError(EvidenceError):
    """Required evidence could not be collected."""


class PolicyError(HarnessError):
    """Policy evaluation or loading failed."""


class SandboxError(HarnessError):
    """Sandbox creation, execution, or teardown failed."""


class DecisionError(HarnessError):
    """Decision engine could not produce a decision."""


class ProvenanceError(HarnessError):
    """Provenance chain validation failed."""


class ArtifactError(HarnessError):
    """Artifact storage or integrity verification failed."""


class WorkflowError(HarnessError):
    """ADK workflow routing or state transition error."""


class RepositoryError(HarnessError):
    """Repository or git operations failed."""


class ApprovalError(HarnessError):
    """Human approval validation failed."""
