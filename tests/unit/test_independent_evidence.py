"""Unit tests for Phase 4: Independent Evidence handlers.

Tests adversarial review, independent review, and mutation testing
integration within the workflow nodes.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest

from evidence_first_harness.artifacts.store import ArtifactStore
from evidence_first_harness.callbacks.provenance import ProvenanceRecorder
from evidence_first_harness.domain.evidence import EvidenceRecord, EvidenceRequirement
from evidence_first_harness.policy.engine import PolicyEngine
from evidence_first_harness.workflows.graph import NodeStatus
from evidence_first_harness.workflows.nodes import (
    _run_adversarial_review,
    handle_run_adversarial_checks,
    handle_run_independent_review,
)
from evidence_first_harness.workflows.state import WorkflowState


def _make_store() -> ArtifactStore:
    path = Path(tempfile.mkdtemp(prefix="efh_test_store_"))
    return ArtifactStore(path)


def _make_provenance() -> ProvenanceRecorder:
    path = Path(tempfile.mkdtemp(prefix="efh_test_prov_"))
    return ProvenanceRecorder(f"run_prov{uuid4().hex[:8]}", path)


def _make_worktree() -> Path:
    return Path(tempfile.mkdtemp(prefix="efh_test_worktree_"))


@pytest.fixture
def temp_store() -> ArtifactStore:
    return _make_store()


@pytest.fixture
def temp_provenance() -> ProvenanceRecorder:
    return _make_provenance()


@pytest.fixture
def temp_worktree() -> Path:
    return _make_worktree()


@pytest.fixture
def workflow_state() -> WorkflowState:
    return WorkflowState(run_id=f"run_wf{uuid4().hex[:8]}")


@pytest.fixture
def policy() -> PolicyEngine:
    path = Path(tempfile.mkstemp(suffix=".yaml")[1])
    path.write_text("""
version: "1.0"
tiers:
  3:
    required: [formatting, lint, targeted_tests, secret_scan]
    minimum:
      test_pass_rate: 1.0
    approval: []
  2:
    required: [formatting, lint, targeted_tests, security_scan, mutation_test]
    minimum:
      test_pass_rate: 1.0
      mutation_score: 0.70
    approval: [code_owner]
execution_order: [formatting, lint, targeted_tests, secret_scan, security_scan, mutation_test]
executor_map:
  formatting: ruff
  lint: ruff
  targeted_tests: pytest
  secret_scan: secrets
  security_scan: semgrep
  mutation_test: mutation_test
retry_policy:
  implementation_attempts: 3
  evidence_repair_attempts: 2
  tool_retry_attempts: 2
  maximum_agent_turns: 20
  maximum_total_runtime_minutes: 45
""")
    return PolicyEngine(path)


@pytest.fixture
def tier3_evidence_plan() -> list[EvidenceRequirement]:
    """Evidence plan for tier 3 (no mutation_test)."""
    return [
        EvidenceRequirement(
            id="formatting",
            claim_ids=[],
            evidence_type="formatting",
            executor="ruff",
            mandatory=True,
            failure_action="repair",
            independence_class="deterministic",
        ),
        EvidenceRequirement(
            id="lint",
            claim_ids=[],
            evidence_type="lint",
            executor="ruff",
            mandatory=True,
            failure_action="repair",
            independence_class="deterministic",
        ),
        EvidenceRequirement(
            id="targeted_tests",
            claim_ids=[],
            evidence_type="targeted_tests",
            executor="pytest",
            mandatory=True,
            failure_action="repair",
            independence_class="deterministic",
        ),
        EvidenceRequirement(
            id="secret_scan",
            claim_ids=[],
            evidence_type="secret_scan",
            executor="secrets",
            mandatory=True,
            failure_action="reject",
            independence_class="deterministic",
        ),
    ]


@pytest.fixture
def tier2_evidence_plan() -> list[EvidenceRequirement]:
    """Evidence plan for tier 2 (includes mutation_test)."""
    return [
        EvidenceRequirement(
            id="formatting",
            claim_ids=[],
            evidence_type="formatting",
            executor="ruff",
            mandatory=True,
            failure_action="repair",
            independence_class="deterministic",
        ),
        EvidenceRequirement(
            id="lint",
            claim_ids=[],
            evidence_type="lint",
            executor="ruff",
            mandatory=True,
            failure_action="repair",
            independence_class="deterministic",
        ),
        EvidenceRequirement(
            id="targeted_tests",
            claim_ids=[],
            evidence_type="targeted_tests",
            executor="pytest",
            mandatory=True,
            failure_action="reject",
            independence_class="deterministic",
        ),
        EvidenceRequirement(
            id="security_scan",
            claim_ids=[],
            evidence_type="security_scan",
            executor="semgrep",
            mandatory=True,
            failure_action="reject",
            independence_class="deterministic",
        ),
        EvidenceRequirement(
            id="mutation_test",
            claim_ids=[],
            evidence_type="mutation_test",
            executor="mutation_test",
            mandatory=True,
            minimum_threshold=0.70,
            failure_action="reject",
            independence_class="deterministic",
        ),
    ]


# ---------------------------------------------------------------------------
# Adversarial Review Tests
# ---------------------------------------------------------------------------


class TestAdversarialReview:
    async def test_handler_succeeds_without_mutation(
        self,
        workflow_state: WorkflowState,
        temp_store: ArtifactStore,
        temp_provenance: ProvenanceRecorder,
        policy: PolicyEngine,
        tier3_evidence_plan: list[EvidenceRequirement],
        temp_worktree: Path,
    ) -> None:
        """Adversarial checks handler works even when mutation_test is not in plan."""
        evidence_records: list[EvidenceRecord] = []

        status = await handle_run_adversarial_checks(
            state=workflow_state,
            worktree_path=temp_worktree,
            evidence_records=evidence_records,
            evidence_plan=tier3_evidence_plan,
            policy=policy,
            artifacts=temp_store,
            provenance=temp_provenance,
        )

        assert status == NodeStatus.SUCCESS, f"Errors: {workflow_state.errors}"
        mutation_records = [r for r in evidence_records if r.executor == "mutation_test"]
        assert len(mutation_records) == 0

    async def test_adversarial_review_stores_artifact(
        self,
        workflow_state: WorkflowState,
        temp_store: ArtifactStore,
        temp_provenance: ProvenanceRecorder,
        policy: PolicyEngine,
        tier3_evidence_plan: list[EvidenceRequirement],
        temp_worktree: Path,
    ) -> None:
        """Adversarial review handler stores an advisory report artifact."""
        evidence_records: list[EvidenceRecord] = []

        await handle_run_adversarial_checks(
            state=workflow_state,
            worktree_path=temp_worktree,
            evidence_records=evidence_records,
            evidence_plan=tier3_evidence_plan,
            policy=policy,
            artifacts=temp_store,
            provenance=temp_provenance,
        )

        # Verify adversarial review artifact was stored
        advisory_ref = None
        for entry in temp_store._index_path.read_text().splitlines():
            entry_data = json.loads(entry)
            if entry_data.get("kind") == "adversarial_review":
                advisory_ref = entry_data["artifact_id"]
                break

        assert advisory_ref is not None, "Adversarial review artifact should be stored"
        content = temp_store.retrieve(advisory_ref).decode("utf-8")
        advisory = json.loads(content)

        assert "unsupported_claims" in advisory
        assert "counterexamples" in advisory
        assert "missing_evidence" in advisory
        assert advisory["recommendation"] == "advisory_only"

    def test_static_review_with_impact(
        self,
        workflow_state: WorkflowState,
        temp_store: ArtifactStore,
    ) -> None:
        """_run_adversarial_review picks up impact confidence from artifacts."""
        # Store a low-confidence impact report
        impact = {"confidence": 0.3, "unknown_impact_areas": ["dynamic plugin loading"]}
        ref = temp_store.store("impact_report", json.dumps(impact))
        workflow_state.impact_report_artifact = ref.artifact_id

        advisory = _run_adversarial_review(temp_store, workflow_state)

        assert advisory["unsupported_claims"] == []
        assert advisory["counterexamples"] == []
        assert len(advisory["missing_evidence"]) >= 1
        assert "Low impact confidence" in advisory["missing_evidence"][0]
        assert len(advisory["overlooked_edge_cases"]) >= 1
        assert "dynamic plugin loading" in advisory["overlooked_edge_cases"]


# ---------------------------------------------------------------------------
# Independent Review Tests
# ---------------------------------------------------------------------------


class TestIndependentReview:
    async def test_handler_succeeds(
        self,
        workflow_state: WorkflowState,
        temp_store: ArtifactStore,
        temp_provenance: ProvenanceRecorder,
    ) -> None:
        """Independent review handler succeeds and stores artifact."""
        status = await handle_run_independent_review(
            state=workflow_state,
            artifacts=temp_store,
            provenance=temp_provenance,
        )

        assert status == NodeStatus.SUCCESS, f"Errors: {workflow_state.errors}"

        # Verify artifact was stored
        review_ref = None
        for entry in temp_store._index_path.read_text().splitlines():
            entry_data = json.loads(entry)
            if entry_data.get("kind") == "independent_review":
                review_ref = entry_data["artifact_id"]
                break

        assert review_ref is not None, "Independent review artifact should be stored"
        content = temp_store.retrieve(review_ref).decode("utf-8")
        review = json.loads(content)

        assert "independent_tests_generated" in review
        assert "independent_tests_passed" in review
        assert "model_isolation" in review
        assert "gemini-2.5-pro" in review["model_isolation"]
        assert "deepseek-v4-pro" in review["model_isolation"]

    async def test_model_isolation_is_documented(
        self,
        workflow_state: WorkflowState,
        temp_store: ArtifactStore,
        temp_provenance: ProvenanceRecorder,
    ) -> None:
        """Independent review documents that implementation model ≠ test model."""
        status = await handle_run_independent_review(
            state=workflow_state,
            artifacts=temp_store,
            provenance=temp_provenance,
        )

        assert status == NodeStatus.SUCCESS, f"Errors: {workflow_state.errors}"

        # Find the stored artifact
        review_ref = None
        for entry in temp_store._index_path.read_text().splitlines():
            entry_data = json.loads(entry)
            if entry_data.get("kind") == "independent_review":
                review_ref = entry_data["artifact_id"]
                break

        content = temp_store.retrieve(review_ref).decode("utf-8")
        review = json.loads(content)

        # The key invariant from Section 7.2.4:
        # implementation model ≠ independent test model
        assert "≠" in review["model_isolation"]


# ---------------------------------------------------------------------------
# Mutation Testing Integration Tests
# ---------------------------------------------------------------------------


class TestMutationIntegration:
    async def test_mutation_executed_for_tier2(
        self,
        workflow_state: WorkflowState,
        temp_store: ArtifactStore,
        temp_provenance: ProvenanceRecorder,
        policy: PolicyEngine,
        tier2_evidence_plan: list[EvidenceRequirement],
        temp_worktree: Path,
    ) -> None:
        """Mutation testing is attempted when mutation_test is in the evidence plan."""
        evidence_records: list[EvidenceRecord] = []

        await handle_run_adversarial_checks(
            state=workflow_state,
            worktree_path=temp_worktree,
            evidence_records=evidence_records,
            evidence_plan=tier2_evidence_plan,
            policy=policy,
            artifacts=temp_store,
            provenance=temp_provenance,
        )

        # With tier 2 plan containing mutation_test, the executor should attempt to run
        # (may fail if mutmut not installed, but should still produce a record)
        mutation_records = [r for r in evidence_records if r.executor == "mutation_test"]
        assert len(mutation_records) >= 1, (
            f"Mutation test should produce at least one evidence record. "
            f"Got {len(evidence_records)}: {[r.executor for r in evidence_records]}. "
            f"Errors: {workflow_state.errors}"
        )

        record = mutation_records[0]
        # mutmut not installed → expect "error" or "unavailable"
        assert record.status in ("error", "unavailable", "pass", "fail", "partial")
        assert record.requirement_id == "mutation_test"
