"""Unit tests for the PolicyEngine."""

from __future__ import annotations

from pathlib import Path

import pytest

from evidence_first_harness.domain.exceptions import PolicyError
from evidence_first_harness.policy.engine import PolicyEngine, load_policy


class TestPolicyEngine:
    """Tests for policy loading and evaluation."""

    def test_loads_valid_policy(self, sample_policy_yaml: str) -> None:
        """A valid policy YAML should load without errors."""
        path = _write_temp_policy(sample_policy_yaml)
        engine = PolicyEngine(path)
        assert engine.version == "1.0"

    def test_missing_file_raises(self) -> None:
        """Missing policy file should raise PolicyError."""
        with pytest.raises(PolicyError, match="not found"):
            PolicyEngine("/nonexistent/policy.yaml")

    def test_invalid_yaml_raises(self, tmp_path: Path) -> None:
        """Invalid YAML should raise PolicyError."""
        bad_path = tmp_path / "bad.yaml"
        bad_path.write_text("{{{ invalid")
        with pytest.raises(PolicyError, match="Invalid policy YAML"):
            PolicyEngine(bad_path)

    def test_missing_version_raises(self, tmp_path: Path) -> None:
        """Policy without version field should raise."""
        path = tmp_path / "no_version.yaml"
        path.write_text("tiers: {}")
        with pytest.raises(PolicyError, match="version"):
            PolicyEngine(path)

    def test_missing_tiers_raises(self, tmp_path: Path) -> None:
        """Policy without tiers field should raise."""
        path = tmp_path / "no_tiers.yaml"
        path.write_text("version: '1.0'")
        with pytest.raises(PolicyError, match="tiers"):
            PolicyEngine(path)

    def test_get_required_evidence_tier3(self, sample_policy_yaml: str) -> None:
        """Tier 3 should return lightweight checks."""
        engine = PolicyEngine(_write_temp_policy(sample_policy_yaml))
        required = engine.get_required_evidence(3)
        assert "formatting" in required
        assert "lint" in required
        assert "secret_scan" not in required  # not in tier 3

    def test_get_required_evidence_tier1(self, sample_policy_yaml: str) -> None:
        """Tier 1 should return comprehensive checks."""
        engine = PolicyEngine(_write_temp_policy(sample_policy_yaml))
        required = engine.get_required_evidence(1)
        assert "integration_tests" in required
        assert len(required) >= 5  # tier 1 has many checks

    def test_unknown_tier_raises(self, sample_policy_yaml: str) -> None:
        """Unknown tier should raise PolicyError."""
        engine = PolicyEngine(_write_temp_policy(sample_policy_yaml))
        with pytest.raises(PolicyError, match="not defined"):
            engine.get_required_evidence(99)

    def test_get_approval_roles_tier2(self, sample_policy_yaml: str) -> None:
        """Tier 2 requires code owner approval."""
        engine = PolicyEngine(_write_temp_policy(sample_policy_yaml))
        roles = engine.get_approval_roles(2)
        assert "code_owner" in roles

    def test_get_approval_roles_tier3(self, sample_policy_yaml: str) -> None:
        """Tier 3 requires no approval."""
        engine = PolicyEngine(_write_temp_policy(sample_policy_yaml))
        roles = engine.get_approval_roles(3)
        assert roles == []

    def test_thresholds(self, sample_policy_yaml: str) -> None:
        """Should return correct minimum thresholds per tier."""
        engine = PolicyEngine(_write_temp_policy(sample_policy_yaml))
        t2 = engine.get_minimum_thresholds(2)
        assert t2["test_pass_rate"] == 1.0
        assert t2["mutation_score"] == 0.70
        assert t2["impact_confidence"] == 0.80

    def test_compile_evidence_plan(self, sample_policy_yaml: str) -> None:
        """Should compile ordered evidence requirements."""
        engine = PolicyEngine(_write_temp_policy(sample_policy_yaml))
        plan = engine.compile_evidence_plan(tier=2)
        # Should be ordered by execution_order
        assert len(plan) > 0
        for req in plan:
            assert req.mandatory is True
            assert req.independence_class == "deterministic"
            assert req.failure_action == "reject"

    def test_retry_policy_defaults(self, sample_policy_yaml: str) -> None:
        engine = PolicyEngine(_write_temp_policy(sample_policy_yaml))
        retry = engine.get_retry_policy()
        assert retry["implementation_attempts"] == 3
        assert retry["evidence_repair_attempts"] == 2

    def test_load_policy_helper(self, sample_policy_yaml: str) -> None:
        """load_policy() should return a PolicyEngine."""
        engine = load_policy(_write_temp_policy(sample_policy_yaml))
        assert isinstance(engine, PolicyEngine)

    def test_evaluate_sufficiency_all_pass(self, sample_policy_yaml: str) -> None:
        """All evidence passing should return sufficiency overall=True."""
        from datetime import datetime, UTC

        from evidence_first_harness.domain.evidence import EvidenceRecord

        engine = PolicyEngine(_write_temp_policy(sample_policy_yaml))
        now = datetime.now(UTC)
        # Provide all tier-3 required evidence (formatting, lint, type_check, targeted_tests, secret_scan)
        tier3_required = engine.get_required_evidence(3)
        records = [
            EvidenceRecord(
                id=f"r_{req_id}", requirement_id=req_id, status="pass",
                executor="ruff", started_at=now, completed_at=now,
            )
            for req_id in tier3_required
        ]
        result = engine.evaluate_sufficiency(
            tier=3,
            evidence_records=records,
            impact_confidence=0.85,  # meet the 0.70 minimum
        )
        assert result["overall"] is True
        assert len(result["passed"]) == len(tier3_required)
        assert len(result["failed"]) == 0

    def test_evaluate_sufficiency_with_failures(self, sample_policy_yaml: str) -> None:
        """Failed evidence should make overall=False."""
        from datetime import datetime, UTC

        from evidence_first_harness.domain.evidence import EvidenceRecord

        engine = PolicyEngine(_write_temp_policy(sample_policy_yaml))
        now = datetime.now(UTC)
        records = [
            EvidenceRecord(
                id="r1", requirement_id="formatting", status="pass",
                executor="ruff", started_at=now, completed_at=now,
            ),
            EvidenceRecord(
                id="r2", requirement_id="lint", status="fail",
                executor="ruff", started_at=now, completed_at=now,
            ),
        ]
        result = engine.evaluate_sufficiency(tier=3, evidence_records=records)
        assert result["overall"] is False
        assert "lint" in result["failed"]


def _write_temp_policy(yaml_content: str) -> Path:
    """Write policy YAML to a temp file and return its path."""
    import tempfile

    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
    tmp.write(yaml_content)
    tmp.close()
    return Path(tmp.name)
