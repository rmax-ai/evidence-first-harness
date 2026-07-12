"""Evidence planner — compiles evidence requirements from policy and impact.

Section 11 of the spec. Takes a risk tier, impact report, and policy config,
produces an ordered list of EvidenceRequirements with appropriate thresholds
and independence classifications.
"""

from __future__ import annotations

import uuid
from typing import Literal

import structlog

from evidence_first_harness.domain.evidence import EvidenceRequirement
from evidence_first_harness.domain.impact import ImpactReport
from evidence_first_harness.domain.risk import RiskAssessment
from evidence_first_harness.policy.engine import PolicyEngine

logger = structlog.get_logger()


class EvidencePlanner:
    """Compiles evidence plans from policy, risk, and impact.

    The planner is deterministic — it maps tiered policy requirements
    to concrete EvidenceRequirement objects with per-check configuration.
    """

    def __init__(self, policy: PolicyEngine) -> None:
        self._policy = policy

    def compile(
        self,
        risk: RiskAssessment,
        impact: ImpactReport | None = None,
        claim_ids: list[str] | None = None,
    ) -> list[EvidenceRequirement]:
        """Compile an evidence plan for a given risk assessment.

        Args:
            risk: The risk assessment for the change.
            impact: Optional impact report (affects test selection strategy).
            claim_ids: Optional claim IDs to link requirements to.

        Returns:
            Ordered list of evidence requirements.
        """
        tier = risk.overall_tier
        required_ids = self._policy.get_required_evidence(tier)
        thresholds = self._policy.get_minimum_thresholds(tier)
        execution_order = self._policy.get_execution_order()

        # Sort required checks by execution order
        ordered = [c for c in execution_order if c in required_ids]
        ordered.extend(c for c in required_ids if c not in ordered)

        plan: list[EvidenceRequirement] = []
        for i, check_id in enumerate(ordered):
            threshold = thresholds.get(check_id)
            independence = self._classify_independence(check_id)
            failure_action = self._classify_failure_action(check_id, tier)

            plan.append(
                EvidenceRequirement(
                    id=check_id,  # Use policy check ID directly so decision engine matches
                    claim_ids=claim_ids or [],
                    evidence_type=check_id,
                    executor=self._policy.get_executor_map().get(check_id, check_id),
                    mandatory=True,
                    minimum_threshold=threshold,
                    independence_class=independence,
                    failure_action=failure_action,
                )
            )

        # If impact confidence is low, add broader testing
        if impact and impact.confidence < 0.70:
            logger.info(
                "impact_confidence_low",
                confidence=impact.confidence,
                tier=tier,
            )
            # Could add a full-test-suite requirement here

        logger.info(
            "evidence_plan_compiled",
            tier=tier,
            check_count=len(plan),
            checks=[r.id for r in plan],
        )

        return plan

    @staticmethod
    def _classify_independence(
        check_id: str,
    ) -> Literal["deterministic", "external_oracle", "independent_model", "same_model"]:
        """Classify a check's independence level."""
        # All Phase 1 checks are deterministic (static analysis, test execution)
        deterministic_checks = {
            "formatting",
            "lint",
            "type_check",
            "targeted_tests",
            "integration_tests",
            "security_scan",
            "secret_scan",
            "dependency_scan",
            "mutation_test",
            "performance_check",
            "rollback_check",
            "contract_tests",
            "git_validation",
        }
        if check_id in deterministic_checks:
            return "deterministic"
        return "same_model"

    @staticmethod
    def _classify_failure_action(
        check_id: str, tier: int
    ) -> Literal["reject", "repair", "review", "warn"]:
        """Determine what happens when this check fails."""
        # Formatting/lint failures can be auto-repaired
        auto_fixable = {"formatting", "lint"}
        if check_id in auto_fixable:
            return "repair"

        # Security/type failures are hard blockers
        hard_blockers = {"type_check", "secret_scan", "security_scan", "dependency_scan"}
        if check_id in hard_blockers:
            return "reject"

        # For tier 3, test failures trigger repair; for tier 2/1, they trigger review
        if check_id in {"targeted_tests", "integration_tests", "contract_tests"}:
            if tier == 3:
                return "repair"
            return "reject"

        return "reject"

    @staticmethod
    def _short_id() -> str:
        """Generate a short unique suffix."""
        return uuid.uuid4().hex[:8]
