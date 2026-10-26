"""Composability claims are planned only for matching impact dimensions."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from evidence_first_harness.domain.composability import ComposabilityClaim
from evidence_first_harness.domain.evidence import EvidenceRecord
from evidence_first_harness.domain.impact import ImpactReport
from evidence_first_harness.domain.risk import RiskAssessment, RiskDimension
from evidence_first_harness.evidence.bundle import BundleBuilder
from evidence_first_harness.evidence.planner import EvidencePlanner
from evidence_first_harness.policy.decision import DecisionEngine
from evidence_first_harness.policy.engine import PolicyEngine

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _risk() -> RiskAssessment:
    low = RiskDimension(level="low", rationale="Test risk")
    return RiskAssessment(
        regulatory_impact=low,
        customer_proximity=low,
        reversibility=low,
        data_sensitivity=low,
        operational_blast_radius=low,
        security_impact=low,
        repository_uncertainty=low,
        overall_tier=3,
    )


def _claims() -> tuple[ComposabilityClaim, ...]:
    return (
        ComposabilityClaim(
            id="worker-removal",
            family="temporal_cleanup",
            capability="worker",
            change_shapes=("removal",),
        ),
        ComposabilityClaim(
            id="worker-reconcile",
            family="reconciliation_idempotence",
            capability="worker",
            change_shapes=("reconciliation",),
        ),
        ComposabilityClaim(
            id="billing-removal",
            family="temporal_cleanup",
            capability="billing",
            change_shapes=("removal",),
        ),
    )


def test_planner_selects_mandatory_deterministic_claims_by_impact() -> None:
    """Matched capability and shape produce a mandatory deterministic check."""
    planner = EvidencePlanner(PolicyEngine(_REPO_ROOT / "config" / "policies.yaml"))
    impact = ImpactReport(
        affected_capabilities=("worker",),
        change_shapes=("removal",),
        confidence=1.0,
    )

    plan = planner.compile(
        risk=_risk(),
        impact=impact,
        composability_claims=_claims(),
    )
    selected = [item for item in plan if item.composability_claim is not None]

    assert len(selected) == 1
    requirement = selected[0]
    assert requirement.id == "composability_worker-removal"
    assert requirement.claim_ids == ["worker-removal"]
    assert requirement.evidence_type == "composability:temporal_cleanup"
    assert requirement.executor == "composability"
    assert requirement.mandatory
    assert requirement.independence_class == "deterministic"
    assert requirement.failure_action == "reject"
    assert requirement.composability_claim is not None
    assert requirement.composability_claim.capability == "worker"


def test_planner_does_not_run_claims_without_a_matching_impact() -> None:
    """Claims stay out of the plan when impact is missing or unrelated."""
    planner = EvidencePlanner(PolicyEngine(_REPO_ROOT / "config" / "policies.yaml"))
    claims = _claims()
    unrelated_impact = ImpactReport(
        affected_capabilities=("database",),
        change_shapes=("removal",),
        confidence=1.0,
    )

    no_impact_plan = planner.compile(risk=_risk(), composability_claims=claims)
    unrelated_plan = planner.compile(
        risk=_risk(),
        impact=unrelated_impact,
        composability_claims=claims,
    )

    assert all(item.composability_claim is None for item in no_impact_plan)
    assert all(item.composability_claim is None for item in unrelated_plan)


def test_selected_composability_failure_affects_sufficiency_and_decision() -> None:
    """A failed selected claim must block the evidence bundle."""
    policy = PolicyEngine(_REPO_ROOT / "config" / "policies.yaml")
    planner = EvidencePlanner(policy)
    claim = _claims()[0]
    impact = ImpactReport(
        affected_capabilities=("worker",),
        change_shapes=("removal",),
        confidence=1.0,
    )
    plan = planner.compile(
        risk=_risk(),
        impact=impact,
        composability_claims=(claim,),
    )
    now = datetime.now(UTC)
    records = [
        EvidenceRecord(
            id=f"record_{requirement.id}",
            requirement_id=requirement.id,
            status="fail" if requirement.composability_claim else "pass",
            executor=requirement.executor,
            started_at=now,
            completed_at=now,
        )
        for requirement in plan
    ]
    bundle = BundleBuilder(
        run_id="run_composability",
        repository="fixture",
        base_commit="base",
        policy=policy,
        decision_engine=DecisionEngine(),
    ).build(
        specification=None,
        risk=_risk(),
        impact=impact,
        evidence_plan=plan,
        evidence_records=records,
    )
    requirement_id = "composability_worker-removal"

    assert requirement_id in bundle.sufficiency["failed"]
    assert bundle.decision["decision"] == "repair_required"
