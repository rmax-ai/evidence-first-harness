"""Deterministic decision engine.

Section 20 of the spec. Evaluates evidence against policy and produces
a Decision. The LLM may explain the result but cannot modify it.
"""

from __future__ import annotations

import structlog

from evidence_first_harness.domain.decision import Decision, DecisionResult
from evidence_first_harness.domain.evidence import EvidenceRecord
from evidence_first_harness.domain.risk import RiskAssessment

logger = structlog.get_logger()


class DecisionEngine:
    """Deterministic decision engine.

    Takes risk tier, evidence records, impact confidence, contradictions,
    retry budget, and approval status — produces a DecisionResult.

    Rules (from section 20):
    - Any required evidence failed → REPAIR_REQUIRED
    - Any required evidence unavailable → HUMAN_REVIEW_REQUIRED
    - Contradictions present → HUMAN_REVIEW_REQUIRED
    - Tier 1 → SPECIALIST_APPROVAL_REQUIRED
    - Tier 2 → HUMAN_REVIEW_REQUIRED
    - Otherwise → ELIGIBLE_FOR_AUTOMATION
    """

    def decide(
        self,
        risk: RiskAssessment,
        evidence_records: list[EvidenceRecord],
        required_evidence_ids: list[str],
        impact_confidence: float = 0.0,
        contradictions: list[str] | None = None,
        repair_attempts: int = 0,
        max_repair_attempts: int = 2,
        approval_roles: list[str] | None = None,
        approved_roles: list[str] | None = None,
    ) -> DecisionResult:
        """Produce a deterministic decision.

        Args:
            risk: The risk assessment for this change.
            evidence_records: All collected evidence records.
            required_evidence_ids: IDs of required evidence checks.
            impact_confidence: Impact analysis confidence (0.0-1.0).
            contradictions: Detected contradictions in evidence.
            repair_attempts: How many repair cycles have been attempted.
            max_repair_attempts: Maximum allowed repair attempts.
            approval_roles: Roles that must approve.
            approved_roles: Roles that have approved.

        Returns:
            A DecisionResult with the deterministic outcome.
        """
        contradictions = contradictions or []
        approval_roles = approval_roles or []
        approved_roles = approved_roles or []

        records_by_id: dict[str, EvidenceRecord] = {r.requirement_id: r for r in evidence_records}

        # Classify evidence
        failed: list[str] = []
        unavailable: list[str] = []
        mandatory_failed: list[str] = []
        mandatory_unavailable: list[str] = []

        for req_id in required_evidence_ids:
            record = records_by_id.get(req_id)
            if record is None:
                unavailable.append(req_id)
                mandatory_unavailable.append(req_id)
            elif record.status == "fail" or record.status == "error":
                failed.append(req_id)
                mandatory_failed.append(req_id)
            elif record.status == "unavailable":
                unavailable.append(req_id)
                mandatory_unavailable.append(req_id)

        mandatory_passed_count = len(required_evidence_ids) - len(failed) - len(unavailable)

        # Determine decision
        decision = self._route_decision(
            risk_tier=risk.overall_tier,
            has_mandatory_failed=len(mandatory_failed) > 0,
            has_mandatory_unavailable=len(mandatory_unavailable) > 0,
            has_contradictions=len(contradictions) > 0,
            repair_attempts=repair_attempts,
            max_repair_attempts=max_repair_attempts,
            approval_roles=approval_roles,
            approved_roles=approved_roles,
        )

        # Build rationale
        rationale = self._build_rationale(
            decision=decision,
            risk_tier=risk.overall_tier,
            mandatory_passed=mandatory_passed_count,
            total_required=len(required_evidence_ids),
            failed=mandatory_failed,
            unavailable=mandatory_unavailable,
            contradictions=list(contradictions),
            impact_confidence=impact_confidence,
            repair_attempts=repair_attempts,
        )

        logger.info(
            "decision_rendered",
            decision=decision.value,
            risk_tier=risk.overall_tier,
            mandatory_passed=mandatory_passed_count,
            mandatory_failed=len(mandatory_failed),
            contradictions=len(contradictions),
        )

        return DecisionResult(
            decision=decision,
            rationale=rationale,
            risk_tier=risk.overall_tier,
            mandatory_evidence_passed=len(mandatory_failed) == 0
            and len(mandatory_unavailable) == 0,
            mandatory_evidence_count=mandatory_passed_count,
            mandatory_evidence_failed=mandatory_failed,
            mandatory_evidence_unavailable=mandatory_unavailable,
            contradictions=list(contradictions),
            impact_confidence=impact_confidence,
            repair_attempts_remaining=max(0, max_repair_attempts - repair_attempts),
            required_approvals=approval_roles,
        )

    @staticmethod
    def _route_decision(
        risk_tier: int,
        has_mandatory_failed: bool,
        has_mandatory_unavailable: bool,
        has_contradictions: bool,
        repair_attempts: int,
        max_repair_attempts: int,
        approval_roles: list[str],
        approved_roles: list[str],
    ) -> Decision:
        """Route to the correct decision based on deterministic rules."""
        # Repair logic
        if has_mandatory_failed:
            if repair_attempts < max_repair_attempts:
                return Decision.REPAIR_REQUIRED
            return Decision.REJECTED

        # Missing evidence
        if has_mandatory_unavailable:
            return Decision.HUMAN_REVIEW_REQUIRED

        # Contradictions
        if has_contradictions:
            return Decision.HUMAN_REVIEW_REQUIRED

        # Risk-tier routing
        if risk_tier == 1:
            if set(approval_roles) <= set(approved_roles):
                return Decision.ELIGIBLE_FOR_AUTOMATION
            return Decision.SPECIALIST_APPROVAL_REQUIRED

        if risk_tier == 2:
            if set(approval_roles) <= set(approved_roles):
                return Decision.ELIGIBLE_FOR_AUTOMATION
            return Decision.HUMAN_REVIEW_REQUIRED

        # Tier 3: eligible if all evidence passed
        return Decision.ELIGIBLE_FOR_AUTOMATION

    @staticmethod
    def _build_rationale(
        decision: Decision,
        risk_tier: int,
        mandatory_passed: int,
        total_required: int,
        failed: list[str],
        unavailable: list[str],
        contradictions: list[str],
        impact_confidence: float,
        repair_attempts: int,
    ) -> str:
        """Build a human-readable rationale for the decision."""
        parts: list[str] = []

        parts.append(f"Risk tier: {risk_tier}")
        parts.append(f"Evidence: {mandatory_passed}/{total_required} mandatory checks passed")

        if failed:
            parts.append(f"Failed checks: {', '.join(failed)}")
        if unavailable:
            parts.append(f"Unavailable checks: {', '.join(unavailable)}")
        if contradictions:
            parts.append(f"Contradictions: {len(contradictions)} detected")
        if repair_attempts > 0:
            parts.append(f"Repair attempts: {repair_attempts}")

        parts.append(f"Impact confidence: {impact_confidence:.2f}")

        decision_reasons: dict[Decision, str] = {
            Decision.REJECTED: "Mandatory evidence failed and repair budget exhausted.",
            Decision.REPAIR_REQUIRED: "Mandatory evidence failed — repair attempt available.",
            Decision.HUMAN_REVIEW_REQUIRED: "Evidence gaps or contradictions require human review.",
            Decision.SPECIALIST_APPROVAL_REQUIRED: "High-risk change requires specialist approval.",
            Decision.ELIGIBLE_FOR_AUTOMATION: "All mandatory evidence passed. Change eligible for automated acceptance.",
        }

        parts.append(f"Decision: {decision.value} — {decision_reasons.get(decision, '')}")

        return "\n".join(parts)
