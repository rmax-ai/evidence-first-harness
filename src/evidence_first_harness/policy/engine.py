"""Policy engine — loads, validates, and evaluates evidence policies.

Section 11 of the spec. Policies are version-controlled YAML with tiered
evidence requirements. The engine is deterministic — no LLM involvement.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog
import yaml

from evidence_first_harness.domain.evidence import EvidenceRequirement, EvidenceRecord
from evidence_first_harness.domain.exceptions import PolicyError

logger = structlog.get_logger()


class PolicyEngine:
    """Deterministic policy evaluation engine.

    Loads a YAML policy file, resolves tier-specific requirements, and
    evaluates evidence records against thresholds.
    """

    def __init__(self, policy_path: Path | str) -> None:
        self._policy_path = Path(policy_path)
        self._raw: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        """Load and validate the policy YAML."""
        if not self._policy_path.exists():
            raise PolicyError(f"Policy file not found: {self._policy_path}")

        try:
            with open(self._policy_path) as f:
                self._raw = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise PolicyError(f"Invalid policy YAML: {e}") from e

        if not isinstance(self._raw, dict):
            raise PolicyError("Policy must be a YAML mapping")

        if "version" not in self._raw:
            raise PolicyError("Policy missing required field: version")

        if "tiers" not in self._raw:
            raise PolicyError("Policy missing required field: tiers")

    @property
    def version(self) -> str:
        return str(self._raw.get("version", "unknown"))

    def get_retry_policy(self) -> dict[str, int]:
        """Return the retry policy with defaults."""
        defaults = {
            "implementation_attempts": 3,
            "evidence_repair_attempts": 2,
            "tool_retry_attempts": 2,
            "maximum_agent_turns": 20,
            "maximum_total_runtime_minutes": 45,
        }
        return {**defaults, **self._raw.get("retry_policy", {})}

    def get_executor_map(self) -> dict[str, str]:
        """Return the mapping from policy check IDs to executor names."""
        return dict(self._raw.get("executor_map", {}))

    def get_execution_order(self) -> list[str]:
        """Return ordered list of evidence check IDs (cheapest first)."""
        return list(self._raw.get("execution_order", []))

    def get_required_evidence(self, tier: int) -> list[str]:
        """Return required evidence check IDs for a given risk tier.

        Args:
            tier: Risk tier (1, 2, or 3).

        Returns:
            List of evidence check IDs required by this tier.

        Raises:
            PolicyError: If the tier is not defined in the policy.
        """
        tiers = self._raw.get("tiers", {})
        if tier not in tiers:
            raise PolicyError(f"Tier {tier} not defined in policy")

        return list(tiers[tier].get("required", []))

    def get_minimum_thresholds(self, tier: int) -> dict[str, float]:
        """Return minimum thresholds for a given risk tier.

        Args:
            tier: Risk tier (1, 2, or 3).

        Returns:
            Dict mapping metric names to minimum values.
        """
        tiers = self._raw.get("tiers", {})
        if tier not in tiers:
            raise PolicyError(f"Tier {tier} not defined in policy")

        return dict(tiers[tier].get("minimum", {}))

    def get_approval_roles(self, tier: int) -> list[str]:
        """Return required approval roles for a given risk tier."""
        tiers = self._raw.get("tiers", {})
        if tier not in tiers:
            raise PolicyError(f"Tier {tier} not defined in policy")

        return list(tiers[tier].get("approval", []))

    def compile_evidence_plan(
        self, tier: int, claim_ids: list[str] | None = None
    ) -> list[EvidenceRequirement]:
        """Compile an evidence plan for a risk tier.

        Produces a list of EvidenceRequirement objects with per-check
        configuration: mandatory flag, independence class, failure action.

        Args:
            tier: Risk tier (1, 2, or 3).
            claim_ids: Optional claim IDs to link requirements to.

        Returns:
            Ordered list of EvidenceRequirement objects.
        """
        required = self.get_required_evidence(tier)
        thresholds = self.get_minimum_thresholds(tier)
        execution_order = self.get_execution_order()

        # Sort required checks by execution order
        ordered = [c for c in execution_order if c in required]
        # Append any required checks not in the execution order
        ordered.extend(c for c in required if c not in ordered)

        plan: list[EvidenceRequirement] = []
        for check_id in ordered:
            threshold = thresholds.get(check_id)
            plan.append(
                EvidenceRequirement(
                    id=check_id,
                    claim_ids=claim_ids or [],
                    evidence_type=check_id,
                    executor=check_id,
                    mandatory=True,
                    minimum_threshold=threshold,
                    independence_class="deterministic",
                    failure_action="reject",
                )
            )

        return plan

    def evaluate_sufficiency(
        self,
        tier: int,
        evidence_records: list[EvidenceRecord],
        impact_confidence: float = 0.0,
        contradictions: list[str] | None = None,
    ) -> dict[str, Any]:
        """Evaluate whether collected evidence is sufficient.

        Returns a sufficiency dict with pass/fail per requirement and overall verdict.

        Args:
            tier: Risk tier.
            evidence_records: Collected evidence records.
            impact_confidence: Current impact confidence score.
            contradictions: Any detected contradictions.

        Returns:
            Sufficiency assessment dict with 'passed', 'failed', 'unavailable',
            'thresholds_met', 'thresholds_missed', 'overall'.
        """
        thresholds = self.get_minimum_thresholds(tier)
        required_ids = set(self.get_required_evidence(tier))
        contradictions = contradictions or []

        records_by_id = {r.requirement_id: r for r in evidence_records}

        passed: list[str] = []
        failed: list[str] = []
        unavailable: list[str] = []

        for req_id in required_ids:
            record = records_by_id.get(req_id)
            if record is None:
                unavailable.append(req_id)
                continue

            if record.status == "pass":
                passed.append(req_id)
            elif record.status == "fail":
                failed.append(req_id)
            elif record.status == "error":
                failed.append(req_id)
            elif record.status == "unavailable":
                unavailable.append(req_id)
            elif record.status == "partial":
                passed.append(req_id)  # partial passes — threshold check below

        # Check thresholds
        thresholds_met: list[str] = []
        thresholds_missed: list[str] = []

        for metric, minimum in thresholds.items():
            for record in evidence_records:
                if metric in record.metrics:
                    value = record.metrics[metric]
                    if isinstance(value, (int, float)) and float(value) >= minimum:
                        thresholds_met.append(metric)
                    else:
                        thresholds_missed.append(metric)

        # Impact confidence check
        min_impact = thresholds.get("impact_confidence", 0.0)
        impact_met = impact_confidence >= min_impact

        overall = (
            len(failed) == 0
            and len(unavailable) == 0
            and len(thresholds_missed) == 0
            and impact_met
            and len(contradictions) == 0
        )

        return {
            "passed": passed,
            "failed": failed,
            "unavailable": unavailable,
            "thresholds_met": thresholds_met,
            "thresholds_missed": thresholds_missed,
            "impact_confidence_met": impact_met,
            "contradictions": contradictions,
            "overall": overall,
        }


def load_policy(path: Path | str) -> PolicyEngine:
    """Load and return a PolicyEngine from a YAML file path."""
    return PolicyEngine(path)
