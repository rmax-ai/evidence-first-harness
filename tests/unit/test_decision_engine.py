"""Unit tests for the DecisionEngine."""

from __future__ import annotations

from datetime import datetime, UTC

from evidence_first_harness.domain.decision import Decision, DecisionResult
from evidence_first_harness.domain.evidence import EvidenceRecord
from evidence_first_harness.domain.risk import RiskAssessment, RiskDimension
from evidence_first_harness.policy.decision import DecisionEngine


def _make_risk(tier: int) -> RiskAssessment:
    """Create a minimal risk assessment for testing."""
    return RiskAssessment(
        regulatory_impact=RiskDimension(level="low", rationale="test"),
        customer_proximity=RiskDimension(level="low", rationale="test"),
        reversibility=RiskDimension(level="high", rationale="test"),
        data_sensitivity=RiskDimension(level="low", rationale="test"),
        operational_blast_radius=RiskDimension(level="low", rationale="test"),
        security_impact=RiskDimension(level="low", rationale="test"),
        repository_uncertainty=RiskDimension(level="low", rationale="test"),
        overall_tier=tier,
    )


def _make_record(
    req_id: str, status: str = "pass", metrics: dict | None = None
) -> EvidenceRecord:
    now = datetime.now(UTC)
    return EvidenceRecord(
        id=f"rec-{req_id}",
        requirement_id=req_id,
        executor=req_id,
        status=status,  # type: ignore[arg-type]
        started_at=now,
        completed_at=now,
        metrics=metrics or {},
    )


class TestDecisionEngine:
    """Tests for the deterministic decision engine."""

    def test_tier3_all_pass_eligible(self) -> None:
        """Tier 3 with all passing evidence should be eligible for automation."""
        engine = DecisionEngine()
        risk = _make_risk(3)
        records = [
            _make_record("formatting"),
            _make_record("lint"),
        ]
        result = engine.decide(risk, records, ["formatting", "lint"])
        assert result.decision == Decision.ELIGIBLE_FOR_AUTOMATION

    def test_single_fail_repair_required(self) -> None:
        """One failing check with repair budget should trigger repair."""
        engine = DecisionEngine()
        risk = _make_risk(3)
        records = [
            _make_record("formatting"),
            _make_record("lint", "fail"),
        ]
        result = engine.decide(
            risk, records, ["formatting", "lint"],
            repair_attempts=0, max_repair_attempts=2,
        )
        assert result.decision == Decision.REPAIR_REQUIRED

    def test_repair_exhausted_rejected(self) -> None:
        """Repair budget exhausted should result in rejection."""
        engine = DecisionEngine()
        risk = _make_risk(3)
        records = [
            _make_record("lint", "fail"),
        ]
        result = engine.decide(
            risk, records, ["lint"],
            repair_attempts=2, max_repair_attempts=2,
        )
        assert result.decision == Decision.REJECTED

    def test_unavailable_triggers_human_review(self) -> None:
        """Unavailable required evidence should require human review."""
        engine = DecisionEngine()
        risk = _make_risk(3)
        records: list[EvidenceRecord] = []  # No evidence for lint
        result = engine.decide(risk, records, ["lint"])
        assert result.decision == Decision.HUMAN_REVIEW_REQUIRED

    def test_tier1_specialist_approval(self) -> None:
        """Tier 1 should require specialist approval."""
        engine = DecisionEngine()
        risk = _make_risk(1)
        records = [
            _make_record("integration_tests"),
        ]
        result = engine.decide(
            risk, records, ["integration_tests"],
            approval_roles=["code_owner", "security_owner"],
            approved_roles=["code_owner"],  # missing security_owner
        )
        assert result.decision == Decision.SPECIALIST_APPROVAL_REQUIRED

    def test_tier1_with_all_approvals_eligible(self) -> None:
        """Tier 1 with all approvals should be eligible."""
        engine = DecisionEngine()
        risk = _make_risk(1)
        records = [
            _make_record("integration_tests"),
        ]
        result = engine.decide(
            risk, records, ["integration_tests"],
            approval_roles=["code_owner", "security_owner"],
            approved_roles=["code_owner", "security_owner"],
        )
        assert result.decision == Decision.ELIGIBLE_FOR_AUTOMATION

    def test_tier2_no_approval_review(self) -> None:
        """Tier 2 without approval should require human review."""
        engine = DecisionEngine()
        risk = _make_risk(2)
        records = [
            _make_record("formatting"),
            _make_record("integration_tests"),
        ]
        result = engine.decide(
            risk, records, ["formatting", "integration_tests"],
            approval_roles=["code_owner"],
        )
        assert result.decision == Decision.HUMAN_REVIEW_REQUIRED

    def test_contradictions_force_review(self) -> None:
        """Contradictions in evidence should force human review."""
        engine = DecisionEngine()
        risk = _make_risk(3)
        records = [
            _make_record("formatting"),
        ]
        result = engine.decide(
            risk, records, ["formatting"],
            contradictions=["Test A passes but Test B fails for same input"],
        )
        assert result.decision == Decision.HUMAN_REVIEW_REQUIRED

    def test_result_includes_counts(self) -> None:
        """DecisionResult should include evidence counts."""
        engine = DecisionEngine()
        risk = _make_risk(3)
        records = [
            _make_record("formatting"),
            _make_record("lint", "fail"),
            _make_record("type_check"),
        ]
        result = engine.decide(
            risk, records, ["formatting", "lint", "type_check"],
        )
        assert result.mandatory_evidence_count == 2
        assert result.mandatory_evidence_failed == ["lint"]
        assert result.risk_tier == 3

    def test_rejected_when_tier1_and_no_evidence(self) -> None:
        """No evidence for tier 1 → specialist approval (not eligible)."""
        engine = DecisionEngine()
        risk = _make_risk(1)
        result = engine.decide(
            risk, [], ["integration_tests"],
            approval_roles=["code_owner", "security_owner"],
        )
        assert result.decision == Decision.HUMAN_REVIEW_REQUIRED
