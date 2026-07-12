"""Unit tests for domain models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from evidence_first_harness.domain.specification import (
    CompiledSpecification,
    Invariant,
    Requirement,
)
from evidence_first_harness.domain.risk import RiskAssessment, RiskDimension
from evidence_first_harness.domain.impact import ImpactReport
from evidence_first_harness.domain.evidence import (
    EvidenceBundle,
    EvidenceRecord,
    EvidenceRequirement,
)
from evidence_first_harness.domain.decision import Decision, DecisionResult


class TestCompiledSpecification:
    def test_valid_spec(self) -> None:
        spec = CompiledSpecification(
            task_id="task-1",
            objective="Add idempotency",
            requirements=[
                Requirement(
                    id="req-1", statement="Must deduplicate", source="issue", priority="must"
                ),
            ],
            invariants=[
                Invariant(id="inv-1", statement="No duplicates", scope=["api"], severity="critical"),
            ],
            forbidden_behaviors=["Double charge"],
            non_functional_requirements=["P99 < 10ms"],
            assumptions=["Gateway supports keys"],
            ambiguities=["Key expiry unclear"],
            acceptance_properties=["One charge per key"],
            source_digest="sha256:abc",
        )
        assert spec.task_id == "task-1"
        assert len(spec.requirements) == 1

    def test_empty_spec_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            CompiledSpecification(
                task_id="",
                objective="",
                source_digest="",
            )

    def test_invalid_requirement_id(self) -> None:
        with pytest.raises(ValidationError):
            Requirement(
                id="INVALID UPPERCASE",
                statement="test",
                source="issue",
                priority="must",
            )


class TestRiskAssessment:
    def test_valid_assessment(self) -> None:
        risk = RiskAssessment(
            regulatory_impact=RiskDimension(level="low", rationale="none"),
            customer_proximity=RiskDimension(level="high", rationale="direct"),
            reversibility=RiskDimension(level="medium", rationale="rollback"),
            data_sensitivity=RiskDimension(level="high", rationale="PII"),
            operational_blast_radius=RiskDimension(level="medium", rationale="single svc"),
            security_impact=RiskDimension(level="medium", rationale="financial"),
            repository_uncertainty=RiskDimension(level="low", rationale="known"),
            overall_tier=2,
            required_approval_roles=["code_owner"],
        )
        assert risk.overall_tier == 2
        assert risk.customer_proximity.level == "high"

    def test_invalid_tier_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RiskAssessment(
                regulatory_impact=RiskDimension(level="low", rationale="t"),
                customer_proximity=RiskDimension(level="low", rationale="t"),
                reversibility=RiskDimension(level="low", rationale="t"),
                data_sensitivity=RiskDimension(level="low", rationale="t"),
                operational_blast_radius=RiskDimension(level="low", rationale="t"),
                security_impact=RiskDimension(level="low", rationale="t"),
                repository_uncertainty=RiskDimension(level="low", rationale="t"),
                overall_tier=99,  # type: ignore[arg-type]
            )


class TestImpactReport:
    def test_valid_report(self) -> None:
        report = ImpactReport(
            changed_files=["src/app.py"],
            changed_symbols=["process_payment"],
            direct_dependencies=["payments/service.py"],
            confidence=0.85,
        )
        assert report.confidence == 0.85
        assert "src/app.py" in report.changed_files

    def test_confidence_bounds(self) -> None:
        with pytest.raises(ValidationError):
            ImpactReport(confidence=1.5)
        with pytest.raises(ValidationError):
            ImpactReport(confidence=-0.1)


class TestDecision:
    def test_decision_values(self) -> None:
        assert Decision.REJECTED == "rejected"
        assert Decision.ELIGIBLE_FOR_AUTOMATION == "eligible_for_automation"
        assert len(list(Decision)) == 5

    def test_decision_result(self) -> None:
        result = DecisionResult(
            decision=Decision.ELIGIBLE_FOR_AUTOMATION,
            rationale="All checks passed",
            risk_tier=3,
            mandatory_evidence_passed=True,
            mandatory_evidence_count=5,
            impact_confidence=0.85,
        )
        assert result.decision == Decision.ELIGIBLE_FOR_AUTOMATION
        assert result.repair_attempts_remaining == 0
