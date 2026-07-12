"""ADK session manager — creates, restores, and manages ADK sessions.

Each harness run uses one ADK session. The session carries compact
WorkflowState — large artifacts go to the artifact store.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import structlog

from evidence_first_harness.artifacts.store import ArtifactStore
from evidence_first_harness.callbacks.provenance import ProvenanceRecorder
from evidence_first_harness.domain.evidence import EvidenceRecord
from evidence_first_harness.policy.decision import DecisionEngine
from evidence_first_harness.policy.engine import PolicyEngine
from evidence_first_harness.repository.git import RepositoryManager
from evidence_first_harness.workflows.graph import EvidenceGraph, NodeStatus
from evidence_first_harness.workflows.nodes import (
    handle_assess_sufficiency,
    handle_classify_initial_risk,
    handle_compile_evidence_plan,
    handle_compile_specification,
    handle_emit_bundle,
    handle_generate_patch,
    handle_load_repository,
    handle_plan_implementation,
    handle_run_evidence_checks,
)
from evidence_first_harness.workflows.state import WorkflowState

logger = structlog.get_logger()


class SessionManager:
    """Manages a single evidence-first workflow session.

    Creates the ADK session, drives the graph workflow, and collects
    the final EvidenceBundle.
    """

    def __init__(
        self,
        repo_path: Path | str,
        policy_path: Path | str = "config/policies.yaml",
        artifact_dir: Path | str = ".artifacts",
    ) -> None:
        self._repo_path = Path(repo_path)
        self._artifact_dir = Path(artifact_dir)
        self._run_id = f"run_{uuid.uuid4().hex[:12]}"
        self._policy = PolicyEngine(policy_path)
        self._decision_engine = DecisionEngine()
        self._artifacts = ArtifactStore(self._artifact_dir)
        self._provenance = ProvenanceRecorder(
            self._run_id, self._artifact_dir / "provenance"
        )
        self._state = WorkflowState(run_id=self._run_id)
        self._graph = EvidenceGraph(self._state)
        self._evidence_records: list[EvidenceRecord] = []
        self._worktree_path: Path | None = None

    @property
    def run_id(self) -> str:
        return self._run_id

    @property
    def state(self) -> WorkflowState:
        return self._state

    async def run(
        self,
        task_description: str = "",
        patch_path: Path | str | None = None,
    ) -> dict:
        """Execute the full evidence-first workflow.

        Args:
            task_description: Natural language task description.
            patch_path: Optional path to an existing patch to evaluate.

        Returns:
            Dict with run_id, decision, and bundle path.
        """
        self._provenance.record(
            actor_type="system",
            actor_id="session_manager",
            action="workflow_start",
            input_data={
                "repo_path": str(self._repo_path),
                "task_description": task_description[:200],
                "patch_path": str(patch_path) if patch_path else None,
            },
        )

        logger.info("workflow_started", run_id=self._run_id)

        # Create repository worktree for isolation
        repo = RepositoryManager(self._repo_path)
        worktree = repo.create_worktree()
        self._worktree_path = worktree.path

        try:
            # Drive the graph workflow
            current_node = "start"
            status = NodeStatus.SUCCESS

            for _ in range(50):  # Safety limit
                next_node = self._graph.get_next_node(current_node, status)
                self._state.current_node = current_node

                if next_node is None:
                    logger.info(
                        "workflow_ended",
                        run_id=self._run_id,
                        terminal_node=current_node,
                        status=status.value,
                    )
                    break

                # Execute the next node
                status = await self._execute_node(next_node)
                current_node = next_node

                # Check terminal
                if self._graph.is_terminal(current_node):
                    logger.info(
                        "terminal_reached",
                        run_id=self._run_id,
                        node=current_node,
                    )
                    break

        finally:
            repo.remove_worktree(worktree)

        # Collect results
        decision_value = "unknown"
        bundle_path = ""

        if self._state.evidence_bundle_artifact:
            output_dir = self._artifact_dir / self._run_id
            bundle_file = output_dir / "evidence-bundle.json"
            if bundle_file.exists():
                bundle_path = str(bundle_file)
                import json

                data = json.loads(bundle_file.read_text())
                decision_value = data.get("decision", {}).get("decision", "unknown")

        result = {
            "run_id": self._run_id,
            "decision": decision_value,
            "bundle_path": bundle_path,
            "repository": str(self._repo_path),
            "base_commit": self._state.base_commit,
            "errors": self._state.errors,
        }

        self._provenance.record(
            actor_type="system",
            actor_id="session_manager",
            action="workflow_complete",
            output_data=result,
        )

        return result

    async def _execute_node(self, node_name: str) -> NodeStatus:
        """Execute a single workflow node.

        Maps node names to handler functions with required arguments.
        """
        import time

        start = time.monotonic()

        try:
            status = await self._dispatch(node_name)
        except Exception as e:
            logger.error("node_failed", node=node_name, error=str(e))
            self._state.errors.append(f"{node_name}: {e}")
            status = NodeStatus.FAILURE

        duration_ms = (time.monotonic() - start) * 1000
        self._state.node_timings[node_name] = duration_ms

        logger.info(
            "node_executed",
            node=node_name,
            status=status.value,
            duration_ms=round(duration_ms, 1),
        )

        return status

    async def _dispatch(self, node_name: str) -> NodeStatus:
        """Dispatch to the appropriate node handler."""
        worktree = self._worktree_path or Path(".")

        dispatch_map = {
            "load_repository": lambda: handle_load_repository(
                self._state, self._repo_path, self._artifacts, self._provenance
            ),
            "compile_specification": lambda: handle_compile_specification(
                self._state, "", self._artifacts, self._provenance
            ),
            "classify_initial_risk": lambda: handle_classify_initial_risk(
                self._state, self._artifacts, self._provenance
            ),
            "validate_baseline": lambda: _return_success(),
            "plan_implementation": lambda: handle_plan_implementation(
                self._state, self._artifacts, self._provenance
            ),
            "generate_patch": lambda: handle_generate_patch(
                self._state, worktree, self._artifacts, self._provenance
            ),
            "analyze_impact": lambda: _return_success(),  # Phase 3
            "reclassify_risk": lambda: _return_success(),  # Phase 3
            "compile_evidence_plan": lambda: handle_compile_evidence_plan(
                self._state, self._policy, self._artifacts, self._provenance
            ),
            "run_cheap_checks": lambda: handle_run_evidence_checks(
                self._state, worktree, self._policy, self._evidence_records, "cheap"
            ),
            "run_behavioral_checks": lambda: handle_run_evidence_checks(
                self._state, worktree, self._policy, self._evidence_records, "behavioral"
            ),
            "run_adversarial_checks": lambda: _return_success(),  # Phase 4
            "run_independent_review": lambda: _return_success(),  # Phase 4
            "assess_evidence_sufficiency": lambda: handle_assess_sufficiency(
                self._state,
                self._policy,
                self._decision_engine,
                self._evidence_records,
                self._artifacts,
                self._provenance,
            ),
            "route_decision": lambda: self._route_from_assessment(),
            "emit_evidence_bundle": lambda: handle_emit_bundle(
                self._state,
                self._policy,
                self._decision_engine,
                self._evidence_records,
                self._artifacts,
                self._provenance,
                self._artifact_dir / self._run_id,
            ),
        }

        handler = dispatch_map.get(node_name)
        if handler is None:
            logger.warning("no_handler", node=node_name)
            return NodeStatus.SUCCESS  # Skip unimplemented nodes

        return await handler()

    def _route_from_assessment(self) -> NodeStatus:
        """Route from sufficiency assessment to the appropriate decision node."""
        # In production, this reads the decision from the assessment
        # For now, route based on evidence state
        if self._state.repair_attempt >= MAX_EVIDENCE_REPAIR_ATTEMPTS:
            return NodeStatus.REJECTED

        # Check if any evidence failed
        failed = [r for r in self._evidence_records if r.status in ("fail", "error")]
        if failed:
            return NodeStatus.HUMAN_REVIEW_REQUIRED

        return NodeStatus.ELIGIBLE_FOR_AUTOMATION


async def _return_success() -> NodeStatus:
    """Stub for unimplemented nodes (Phases 3-4)."""
    return NodeStatus.SUCCESS


MAX_EVIDENCE_REPAIR_ATTEMPTS = 2
