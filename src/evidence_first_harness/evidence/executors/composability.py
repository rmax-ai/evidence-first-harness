"""Deterministic executor for adapter-produced composability observations."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal, Protocol

from pydantic import ValidationError

from evidence_first_harness.domain.composability import (
    COMPOSABILITY_CASE_ADAPTER,
    ComposabilityClaim,
    ComposabilityVerifier,
)
from evidence_first_harness.domain.evidence import EvidenceRecord, EvidenceRequirement

if TYPE_CHECKING:
    from evidence_first_harness.evidence.executors.base import EvidenceExecutionContext

EvidenceStatus = Literal["pass", "fail", "partial", "error", "unavailable"]


class ComposabilityCaseAdapter(Protocol):
    """Collect a JSON observation using a trusted, bounded target adapter."""

    async def collect(
        self, context: EvidenceExecutionContext, claim: ComposabilityClaim
    ) -> str | bytes:
        """Return serialized semantic observations for one claim."""
        ...


class ComposabilityExecutor:
    """Validate adapter output and evaluate its semantic property deterministically."""

    name = "composability"

    def __init__(
        self,
        adapter: ComposabilityCaseAdapter | None = None,
        verifier: ComposabilityVerifier | None = None,
    ) -> None:
        self._adapter = adapter
        self._verifier = verifier or ComposabilityVerifier()

    async def execute(
        self,
        context: EvidenceExecutionContext,
        requirement: EvidenceRequirement,
    ) -> EvidenceRecord:
        """Collect, validate, and verify one selected composability claim."""
        started_at = datetime.now(UTC)
        claim = requirement.composability_claim
        if claim is None:
            return self._record(
                requirement=requirement,
                started_at=started_at,
                status="error",
                summary="Composability requirement has no semantic claim",
                limitations=["input.required:composability_claim"],
            )
        if self._adapter is None:
            return self._record(
                requirement=requirement,
                started_at=started_at,
                status="unavailable",
                summary="No composability case adapter is configured",
                limitations=["Configure a trusted bounded adapter for this target."],
            )

        try:
            serialized_case = await self._adapter.collect(context, claim)
        except Exception:
            return self._record(
                requirement=requirement,
                started_at=started_at,
                status="error",
                summary="Composability adapter failed; details redacted",
                limitations=["adapter.execution_failed"],
            )

        try:
            case = COMPOSABILITY_CASE_ADAPTER.validate_json(serialized_case)
        except ValidationError as error:
            code, location = _map_validation_error(error)
            return self._record(
                requirement=requirement,
                started_at=started_at,
                status="error",
                summary="Composability adapter output was rejected",
                limitations=[f"{code}:{location}"],
            )
        except (TypeError, ValueError):
            return self._record(
                requirement=requirement,
                started_at=started_at,
                status="error",
                summary="Composability adapter output was rejected",
                limitations=["input.invalid"],
            )

        if case.claim_id != claim.id or case.family != claim.family:
            return self._record(
                requirement=requirement,
                started_at=started_at,
                status="error",
                summary="Composability adapter output did not match its claim",
                limitations=["input.invalid:claim_mismatch"],
            )

        result = self._verifier.verify(case)
        return self._record(
            requirement=requirement,
            started_at=started_at,
            status="pass" if result.passed else "fail",
            summary=(
                "Composability property passed"
                if result.passed
                else f"Composability property failed: {', '.join(result.violation_codes)}"
            ),
            metrics={
                "composability_passed": int(result.passed),
                "violation_count": len(result.violation_codes),
            },
            counterexample=result.counterexample_json,
        )

    def _record(
        self,
        *,
        requirement: EvidenceRequirement,
        started_at: datetime,
        status: EvidenceStatus,
        summary: str,
        metrics: dict[str, float | int | str] | None = None,
        limitations: list[str] | None = None,
        counterexample: str | None = None,
    ) -> EvidenceRecord:
        return EvidenceRecord(
            id=f"{requirement.id}_{self.name}",
            requirement_id=requirement.id,
            status=status,
            executor=self.name,
            started_at=started_at,
            completed_at=datetime.now(UTC),
            summary=summary,
            metrics=metrics or {},
            limitations=limitations or [],
            counterexample=counterexample,
        )


def _map_validation_error(error: ValidationError) -> tuple[str, str]:
    first_error = error.errors()[0]
    error_type = str(first_error.get("type", ""))
    if error_type == "missing":
        code = "input.required"
    elif error_type == "extra_forbidden":
        code = "input.unknown_field"
    elif error_type in {
        "bool_type",
        "float_type",
        "int_type",
        "string_type",
        "tuple_type",
    }:
        code = "input.type"
    elif error_type in {"union_tag_invalid", "union_tag_not_found"}:
        code = "input.variant"
    else:
        code = "input.invalid"
    location = ".".join(str(part) for part in first_error.get("loc", ()))
    return code, location
