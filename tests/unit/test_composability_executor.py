"""EvidenceExecutor integration for deterministic composability claims."""

from __future__ import annotations

from pathlib import Path

from evidence_first_harness.domain.composability import (
    ComposabilityClaim,
    OwnedState,
    TemporalCleanupCase,
)
from evidence_first_harness.domain.evidence import EvidenceRequirement
from evidence_first_harness.evidence.executors.base import EvidenceExecutionContext
from evidence_first_harness.evidence.executors.composability import ComposabilityExecutor
from evidence_first_harness.workflows.runner import EvidenceRunner


class _StaticAdapter:
    """Return a fixed serialized case for executor contract tests."""

    def __init__(self, payload: str | bytes) -> None:
        self._payload = payload

    async def collect(
        self, _context: EvidenceExecutionContext, _claim: ComposabilityClaim
    ) -> str | bytes:
        return self._payload


def _claim() -> ComposabilityClaim:
    return ComposabilityClaim(
        id="worker-removal",
        family="temporal_cleanup",
        capability="worker",
        change_shapes=("removal",),
    )


def _requirement() -> EvidenceRequirement:
    claim = _claim()
    return EvidenceRequirement(
        id="composability_worker-removal",
        claim_ids=[claim.id],
        evidence_type=f"composability:{claim.family}",
        executor="composability",
        mandatory=True,
        independence_class="deterministic",
        failure_action="reject",
        composability_claim=claim,
    )


def _case(*, state_remains: bool) -> TemporalCleanupCase:
    owned_state = OwnedState(state_id="worker-lease", component_id="worker")
    return TemporalCleanupCase(
        family="temporal_cleanup",
        claim_id="worker-removal",
        component_id="worker",
        explicitly_owned_state=(owned_state,),
        state_after_removal=(owned_state,) if state_remains else (),
    )


async def test_executor_returns_pass_and_fail_as_evidence_records(tmp_path: Path) -> None:
    """Successful and violating observations become structured evidence."""
    context = EvidenceExecutionContext(worktree_path=tmp_path)
    requirement = _requirement()

    passing_case = _case(state_remains=False).model_dump_json()
    failing_case = _case(state_remains=True).model_dump_json()
    passing = await ComposabilityExecutor(_StaticAdapter(passing_case)).execute(
        context,
        requirement,
    )
    failing = await ComposabilityExecutor(_StaticAdapter(failing_case)).execute(
        context,
        requirement,
    )

    assert passing.status == "pass"
    assert passing.requirement_id == requirement.id
    assert passing.executor == "composability"
    assert passing.counterexample is None
    assert failing.status == "fail"
    assert failing.counterexample is not None
    assert "owned_state_survived_removal" in failing.summary


async def test_executor_fails_closed_without_adapter_or_semantic_claim(tmp_path: Path) -> None:
    """Missing adapters or claims produce unavailable or error evidence."""
    context = EvidenceExecutionContext(worktree_path=tmp_path)
    requirement = _requirement()

    unavailable = await ComposabilityExecutor().execute(context, requirement)
    missing_claim = requirement.model_copy(update={"composability_claim": None})
    error = await ComposabilityExecutor(_StaticAdapter("{}")).execute(context, missing_claim)

    assert unavailable.status == "unavailable"
    assert error.status == "error"
    assert error.limitations == ["input.required:composability_claim"]


async def test_executor_maps_malformed_and_mismatched_adapter_output(tmp_path: Path) -> None:
    """Malformed serialized cases and unrelated claims cannot pass."""
    context = EvidenceExecutionContext(worktree_path=tmp_path)
    requirement = _requirement()
    malformed = await ComposabilityExecutor(
        _StaticAdapter('{"family":"not-a-property","claim_id":"worker-removal"}')
    ).execute(context, requirement)
    mismatched_case = _case(state_remains=False).model_copy(update={"claim_id": "other"})
    mismatched = await ComposabilityExecutor(
        _StaticAdapter(mismatched_case.model_dump_json())
    ).execute(
        context,
        requirement,
    )

    assert malformed.status == "error"
    assert malformed.limitations[0].startswith("input.variant:")
    assert mismatched.status == "error"
    assert mismatched.limitations == ["input.invalid:claim_mismatch"]


def test_executor_registry_supports_workflow_runner_without_initialization() -> None:
    """The ADK workflow discovers executors without running EvidenceRunner.__init__."""
    runner = EvidenceRunner.__new__(EvidenceRunner)

    executors = runner._discover_executors()

    assert any(executor.name == "composability" for executor in executors)
