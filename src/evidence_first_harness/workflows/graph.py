"""ADK graph workflow — deterministic orchestration of the evidence-first pipeline.

Section 8 of the spec. A directed graph of 20+ nodes controlling:
- Repository intake
- Specification compilation
- Risk classification
- Implementation planning and execution
- Evidence collection and evaluation
- Decision routing (reject, repair, review, specialist, eligible)

The graph is deterministic — LLM agents execute at specific nodes but
do not control transitions or routing.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

import structlog

from evidence_first_harness.workflows.state import WorkflowState

logger = structlog.get_logger()


class NodeStatus(StrEnum):
    """Possible outcomes of a graph node execution."""

    SUCCESS = "success"
    FAILURE = "failure"
    NEEDS_CLARIFICATION = "needs_clarification"
    BASELINE_FAILURE = "baseline_failure"
    IMPLEMENTATION_FAILURE = "implementation_failure"
    REJECTED = "rejected"
    REPAIR_REQUIRED = "repair_required"
    HUMAN_REVIEW_REQUIRED = "human_review_required"
    SPECIALIST_APPROVAL_REQUIRED = "specialist_approval_required"
    ELIGIBLE_FOR_AUTOMATION = "eligible_for_automation"


class EvidenceGraph:
    """The deterministic evidence-first workflow graph.

    Routes between nodes based on status outcomes. LLM agents execute
    within specific nodes but do not control transitions.
    """

    def __init__(self, state: WorkflowState) -> None:
        self._state = state
        self._node_map = self._build_node_map()

    @property
    def state(self) -> WorkflowState:
        return self._state

    def _build_node_map(self) -> dict[str, Any]:
        """Build the adjacency map for the workflow graph.

        Each entry maps: node_name -> (handler_func, {status: next_node})
        """
        return {
            "start": (None, {NodeStatus.SUCCESS: "load_repository"}),
            "load_repository": (None, {NodeStatus.SUCCESS: "compile_specification"}),
            "compile_specification": (
                None,
                {
                    NodeStatus.SUCCESS: "classify_initial_risk",
                    NodeStatus.NEEDS_CLARIFICATION: "needs_clarification",
                },
            ),
            "needs_clarification": (None, {}),  # Terminal — requires human input
            "classify_initial_risk": (None, {NodeStatus.SUCCESS: "validate_baseline"}),
            "validate_baseline": (
                None,
                {
                    NodeStatus.SUCCESS: "plan_implementation",
                    NodeStatus.BASELINE_FAILURE: "baseline_failure",
                },
            ),
            "baseline_failure": (None, {}),  # Terminal
            "plan_implementation": (None, {NodeStatus.SUCCESS: "generate_patch"}),
            "generate_patch": (
                None,
                {
                    NodeStatus.SUCCESS: "analyze_impact",
                    NodeStatus.IMPLEMENTATION_FAILURE: "implementation_failure",
                },
            ),
            "implementation_failure": (None, {}),  # Terminal
            "analyze_impact": (None, {NodeStatus.SUCCESS: "reclassify_risk"}),
            "reclassify_risk": (None, {NodeStatus.SUCCESS: "compile_evidence_plan"}),
            "compile_evidence_plan": (None, {NodeStatus.SUCCESS: "run_cheap_checks"}),
            "run_cheap_checks": (
                None,
                {
                    NodeStatus.SUCCESS: "run_behavioral_checks",
                    NodeStatus.FAILURE: "repair_loop",
                },
            ),
            "repair_loop": (
                None,
                {
                    NodeStatus.REPAIR_REQUIRED: "generate_patch",
                    NodeStatus.REJECTED: "rejected",
                },
            ),
            "run_behavioral_checks": (
                None,
                {
                    NodeStatus.SUCCESS: "run_adversarial_checks",
                    NodeStatus.FAILURE: "repair_loop",
                },
            ),
            "run_adversarial_checks": (
                None,
                {NodeStatus.SUCCESS: "run_independent_review"},
            ),
            "run_independent_review": (
                None,
                {NodeStatus.SUCCESS: "assess_evidence_sufficiency"},
            ),
            "assess_evidence_sufficiency": (
                None,
                {
                    NodeStatus.SUCCESS: "route_decision",
                    NodeStatus.HUMAN_REVIEW_REQUIRED: "needs_human_review",
                    NodeStatus.REJECTED: "rejected",
                },
            ),
            "needs_human_review": (None, {}),  # Terminal — awaits human
            "route_decision": (
                None,
                {
                    NodeStatus.ELIGIBLE_FOR_AUTOMATION: "emit_evidence_bundle",
                    NodeStatus.HUMAN_REVIEW_REQUIRED: "needs_human_review",
                    NodeStatus.SPECIALIST_APPROVAL_REQUIRED: "needs_specialist_approval",
                },
            ),
            "needs_specialist_approval": (None, {}),  # Terminal — awaits specialist
            "emit_evidence_bundle": (None, {}),  # Terminal — success
            "rejected": (None, {}),  # Terminal — failure
        }

    def get_next_node(self, current_node: str, status: NodeStatus) -> str | None:
        """Determine the next graph node based on current node and status.

        Args:
            current_node: The node that just completed.
            status: The outcome of the current node.

        Returns:
            The next node name, or None if terminal.
        """
        if current_node not in self._node_map:
            logger.warning("unknown_node", node=current_node, run_id=self._state.run_id)
            return None

        _, transitions = self._node_map[current_node]
        next_node = transitions.get(status)

        if next_node is None:
            logger.info(
                "terminal_node_reached",
                node=current_node,
                status=status.value,
                run_id=self._state.run_id,
            )
        else:
            logger.info(
                "node_transition",
                from_node=current_node,
                to_node=next_node,
                status=status.value,
                run_id=self._state.run_id,
            )

        return next_node

    def get_terminal_nodes(self) -> set[str]:
        """Return the set of terminal nodes (no outgoing transitions)."""
        return {
            "needs_clarification",
            "baseline_failure",
            "implementation_failure",
            "needs_human_review",
            "needs_specialist_approval",
            "emit_evidence_bundle",
            "rejected",
        }

    def is_terminal(self, node: str) -> bool:
        """Check if a node is terminal."""
        return node in self.get_terminal_nodes()
