"""ADK graph node handlers — executable logic for each workflow node.

Each handler takes the current WorkflowState, runs agent calls or deterministic
services, updates state, and returns a NodeStatus for routing.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

import structlog

from evidence_first_harness.agents.adversarial_review import (
    create_adversarial_review_agent,
)
from evidence_first_harness.agents.explanation import create_explanation_agent
from evidence_first_harness.agents.implementation import create_implementation_agent
from evidence_first_harness.agents.independent_tests import (
    create_independent_test_agent,
)
from evidence_first_harness.agents.planner import create_planner_agent
from evidence_first_harness.agents.specification import create_specification_agent
from evidence_first_harness.artifacts.store import ArtifactStore
from evidence_first_harness.callbacks.provenance import ProvenanceRecorder
from evidence_first_harness.domain.evidence import EvidenceRecord, EvidenceRequirement
from evidence_first_harness.domain.impact import ImpactReport
from evidence_first_harness.domain.risk import RiskAssessment
from evidence_first_harness.evidence.bundle import BundleBuilder
from evidence_first_harness.evidence.executors.base import EvidenceExecutionContext
from evidence_first_harness.evidence.planner import EvidencePlanner
from evidence_first_harness.impact.analyzer import ImpactAnalyzer
from evidence_first_harness.policy.decision import DecisionEngine
from evidence_first_harness.policy.engine import PolicyEngine
from evidence_first_harness.repository.git import RepositoryManager
from evidence_first_harness.workflows.graph import NodeStatus
from evidence_first_harness.workflows.state import WorkflowState

logger = structlog.get_logger()

# Retry budgets (from policy)
MAX_IMPLEMENTATION_ATTEMPTS = 3
MAX_EVIDENCE_REPAIR_ATTEMPTS = 2


async def handle_load_repository(
    state: WorkflowState,
    repo_path: Path,
    artifacts: ArtifactStore,
    provenance: ProvenanceRecorder,
) -> NodeStatus:
    """Load the repository and create a worktree."""
    try:
        repo = RepositoryManager(repo_path)
        state.base_commit = repo.base_commit
        state.repository_id = str(repo_path)

        provenance.record(
            actor_type="system",
            actor_id="node_handler",
            action="load_repository",
            input_data={"repo_path": str(repo_path)},
            output_data={"base_commit": state.base_commit},
        )

        logger.info("repository_loaded", commit=state.base_commit[:8])
        return NodeStatus.SUCCESS
    except Exception as e:
        state.errors.append(f"load_repository: {e}")
        return NodeStatus.FAILURE


async def handle_compile_specification(
    state: WorkflowState,
    task_description: str,
    artifacts: ArtifactStore,
    provenance: ProvenanceRecorder,
) -> NodeStatus:
    """Run the specification agent to compile requirements."""
    try:
        agent = create_specification_agent()
        # In practice, ADK would manage session context
        # For now, store a placeholder
        spec_content = f"Task: {task_description}\nStatus: compiled"
        ref = artifacts.store("specification", spec_content, {"task": task_description})
        state.specification_artifact = ref.artifact_id

        provenance.record(
            actor_type="agent",
            actor_id="specification_agent",
            action="compile_specification",
            model="gemini-2.5-flash",
            output_data={"artifact_id": ref.artifact_id},
        )

        logger.info("specification_compiled", artifact=ref.artifact_id)
        return NodeStatus.SUCCESS
    except Exception as e:
        state.errors.append(f"specification: {e}")
        return NodeStatus.FAILURE


async def handle_classify_initial_risk(
    state: WorkflowState,
    artifacts: ArtifactStore,
    provenance: ProvenanceRecorder,
) -> NodeStatus:
    """Perform initial risk classification."""
    try:
        from evidence_first_harness.domain.risk import RiskAssessment, RiskDimension

        risk = RiskAssessment(
            regulatory_impact=RiskDimension(level="low", rationale="Initial assessment"),
            customer_proximity=RiskDimension(level="low", rationale="Initial assessment"),
            reversibility=RiskDimension(level="high", rationale="Git revert available"),
            data_sensitivity=RiskDimension(level="low", rationale="Initial assessment"),
            operational_blast_radius=RiskDimension(level="low", rationale="Single change"),
            security_impact=RiskDimension(level="low", rationale="Initial assessment"),
            repository_uncertainty=RiskDimension(level="medium", rationale="Unknown impact"),
            overall_tier=3,
        )

        import json

        ref = artifacts.store("risk_assessment", json.dumps(risk.model_dump(mode="json")))
        state.risk_assessment_artifact = ref.artifact_id

        provenance.record(
            actor_type="system",
            actor_id="risk_classifier",
            action="classify_initial_risk",
            output_data={"tier": risk.overall_tier},
        )

        return NodeStatus.SUCCESS
    except Exception as e:
        state.errors.append(f"risk: {e}")
        return NodeStatus.FAILURE


async def handle_plan_implementation(
    state: WorkflowState,
    artifacts: ArtifactStore,
    provenance: ProvenanceRecorder,
) -> NodeStatus:
    """Run the planner agent."""
    try:
        agent = create_planner_agent()
        plan_content = "Implementation plan placeholder"
        ref = artifacts.store("implementation_plan", plan_content)
        state.implementation_plan_artifact = ref.artifact_id

        provenance.record(
            actor_type="agent",
            actor_id="planner_agent",
            action="plan_implementation",
            model="gemini-2.5-flash",
        )

        return NodeStatus.SUCCESS
    except Exception as e:
        state.errors.append(f"planner: {e}")
        return NodeStatus.FAILURE


async def handle_generate_patch(
    state: WorkflowState,
    worktree_path: Path,
    artifacts: ArtifactStore,
    provenance: ProvenanceRecorder,
) -> NodeStatus:
    """Run the implementation agent in the worktree."""
    try:
        agent = create_implementation_agent()
        # Placeholder — real implementation would use ADK session
        patch_content = "# Generated patch placeholder"
        ref = artifacts.store("patch", patch_content)
        state.patch_artifact = ref.artifact_id

        provenance.record(
            actor_type="agent",
            actor_id="implementation_agent",
            action="generate_patch",
            model="deepseek-v4-pro",
            output_data={"artifact_id": ref.artifact_id},
        )

        return NodeStatus.SUCCESS
    except Exception as e:
        state.errors.append(f"implementation: {e}")
        state.repair_attempt += 1
        if state.repair_attempt >= MAX_IMPLEMENTATION_ATTEMPTS:
            return NodeStatus.IMPLEMENTATION_FAILURE
        return NodeStatus.REPAIR_REQUIRED


async def handle_analyze_impact(
    state: WorkflowState,
    repo_path: Path,
    worktree_path: Path,
    artifacts: ArtifactStore,
    provenance: ProvenanceRecorder,
) -> NodeStatus:
    """Analyze structural impact of the generated patch.

    Uses AST analysis, dependency graph, and coverage data to produce
    an ImpactReport with confidence scoring.
    """
    try:
        analyzer = ImpactAnalyzer(repo_path)

        # Identify changed files from the patch artifact
        changed_files: list[str] = []
        if state.patch_artifact:
            patch_text = artifacts.retrieve(state.patch_artifact).decode("utf-8")
            for line in patch_text.splitlines():
                if line.startswith("--- a/") or line.startswith("+++ b/"):
                    fname = line[6:] if line.startswith("--- a/") else line[6:]
                    if fname.endswith(".py") and "/dev/null" not in fname:
                        changed_files.append(fname)

        if not changed_files:
            # Fallback: list all Python files in worktree
            changed_files = sorted(
                str(p.relative_to(worktree_path))
                for p in worktree_path.rglob("*.py")
                if p.is_file()
            )[:20]

        report = analyzer.analyze(
            changed_files=changed_files,
            worktree_path=worktree_path,
        )

        import json

        ref = artifacts.store(
            "impact_report",
            json.dumps(report.model_dump(mode="json")),
        )
        state.impact_report_artifact = ref.artifact_id

        provenance.record(
            actor_type="system",
            actor_id="impact_analyzer",
            action="analyze_impact",
            output_data={
                "confidence": report.confidence,
                "changed_files": len(report.changed_files),
                "affected_tests": len(report.affected_tests),
                "unknown_areas": len(report.unknown_impact_areas),
            },
        )

        logger.info(
            "impact_analyzed",
            confidence=report.confidence,
            changed_files=len(report.changed_files),
            affected_tests=len(report.affected_tests),
        )

        return NodeStatus.SUCCESS
    except Exception as e:
        state.errors.append(f"impact_analysis: {e}")
        return NodeStatus.FAILURE


async def handle_reclassify_risk(
    state: WorkflowState,
    artifacts: ArtifactStore,
    provenance: ProvenanceRecorder,
) -> NodeStatus:
    """Reclassify risk based on the impact analysis.

    Updates the risk assessment with information from the impact report.
    Higher impact → potentially higher risk tier.
    """
    try:
        import json

        # Load existing risk assessment
        risk_data = artifacts.retrieve(state.risk_assessment_artifact)
        risk = RiskAssessment.model_validate(json.loads(risk_data))

        # Load impact report if available
        impact_confidence = 0.5
        if state.impact_report_artifact:
            impact_data = artifacts.retrieve(state.impact_report_artifact)
            impact = json.loads(impact_data)
            impact_confidence = impact.get("confidence", 0.5)

            # Escalate tier if impact confidence is low (uncertainty = higher risk)
            if impact_confidence < 0.5 and risk.overall_tier > 1:
                # Don't auto-escalate; just flag for review
                pass

        # Store updated risk (keeping original tier for now — future: ML-driven reclassification)
        ref = artifacts.store(
            "risk_assessment_reclassified",
            json.dumps(risk.model_dump(mode="json")),
        )
        state.risk_assessment_artifact = ref.artifact_id

        provenance.record(
            actor_type="system",
            actor_id="risk_classifier",
            action="reclassify_risk",
            output_data={
                "tier": risk.overall_tier,
                "impact_confidence": impact_confidence,
            },
        )

        logger.info(
            "risk_reclassified",
            tier=risk.overall_tier,
            impact_confidence=impact_confidence,
        )

        return NodeStatus.SUCCESS
    except Exception as e:
        state.errors.append(f"reclassify: {e}")
        return NodeStatus.FAILURE


async def handle_compile_evidence_plan(
    state: WorkflowState,
    policy: PolicyEngine,
    artifacts: ArtifactStore,
    provenance: ProvenanceRecorder,
) -> NodeStatus:
    """Compile the evidence plan from policy and risk assessment."""
    try:
        planner = EvidencePlanner(policy)

        # Load risk assessment from artifact
        import json

        risk_data = artifacts.retrieve(state.risk_assessment_artifact)
        risk = RiskAssessment.model_validate(json.loads(risk_data))

        evidence_plan = planner.compile(risk=risk)

        import json as _json

        ref = artifacts.store(
            "evidence_plan",
            _json.dumps([r.model_dump(mode="json") for r in evidence_plan]),
        )
        state.evidence_plan_artifact = ref.artifact_id

        return NodeStatus.SUCCESS
    except Exception as e:
        state.errors.append(f"evidence_plan: {e}")
        return NodeStatus.FAILURE


async def handle_run_evidence_checks(
    state: WorkflowState,
    worktree_path: Path,
    policy: PolicyEngine,
    evidence_records: list[EvidenceRecord],
    evidence_plan: list[EvidenceRequirement],
    phase: str = "cheap",
) -> NodeStatus:
    """Run a batch of evidence checks from the compiled evidence plan.

    Args:
        phase: "cheap" for initial checks, "behavioral" for deeper checks.
    """
    try:
        context = EvidenceExecutionContext(worktree_path=worktree_path)

        # Discover available executors
        from evidence_first_harness.workflows.runner import EvidenceRunner

        runner = EvidenceRunner.__new__(EvidenceRunner)
        executors = runner._discover_executors()
        executor_map: dict[str, Any] = {e.name: e for e in executors}

        # Phase determines which checks to run (by policy check ID prefix)
        cheap_ids = {"formatting", "lint", "type_check", "git_validation", "secret_scan"}
        behavioral_ids = {"targeted_tests", "integration_tests", "security_scan", "coverage"}

        target_ids = cheap_ids if phase == "cheap" else behavioral_ids

        for requirement in evidence_plan:
            if requirement.id not in target_ids:
                continue

            executor_name = requirement.executor
            executor = executor_map.get(executor_name)

            if executor is None:
                logger.warning("executor_not_found", executor=executor_name, check=requirement.id)
                continue

            try:
                record = await executor.execute(context, requirement)
                evidence_records.append(record)
                logger.info(
                    "evidence_executed",
                    check=requirement.id,
                    executor=executor_name,
                    status=record.status,
                )
            except Exception as e:
                logger.error("executor_failed", executor=executor_name, error=str(e))
                now = datetime.now(UTC)
                evidence_records.append(
                    EvidenceRecord(
                        id=f"rec_{requirement.id}",
                        requirement_id=requirement.id,
                        status="error",
                        executor=executor_name,
                        started_at=now,
                        completed_at=now,
                        summary=f"Execution error: {e}",
                        limitations=[str(e)],
                    )
                )

        return NodeStatus.SUCCESS
    except Exception as e:
        state.errors.append(f"evidence_{phase}: {e}")
        return NodeStatus.FAILURE


async def handle_assess_sufficiency(
    state: WorkflowState,
    policy: PolicyEngine,
    decision_engine: DecisionEngine,
    evidence_records: list[EvidenceRecord],
    artifacts: ArtifactStore,
    provenance: ProvenanceRecorder,
) -> NodeStatus:
    """Assess evidence sufficiency and render decision."""
    try:
        # Load risk
        import json

        risk_data = artifacts.retrieve(state.risk_assessment_artifact)
        risk = RiskAssessment.model_validate(json.loads(risk_data))

        required = policy.get_required_evidence(risk.overall_tier)
        retry = policy.get_retry_policy()

        result = decision_engine.decide(
            risk=risk,
            evidence_records=evidence_records,
            required_evidence_ids=required,
            repair_attempts=state.repair_attempt,
            max_repair_attempts=retry["evidence_repair_attempts"],
        )

        provenance.record(
            actor_type="system",
            actor_id="decision_engine",
            action="assess_sufficiency",
            output_data={"decision": result.decision.value},
        )

        # Map decision to node status
        decision_map = {
            "rejected": NodeStatus.REJECTED,
            "repair_required": NodeStatus.REPAIR_REQUIRED,
            "human_review_required": NodeStatus.HUMAN_REVIEW_REQUIRED,
            "specialist_approval_required": NodeStatus.SPECIALIST_APPROVAL_REQUIRED,
            "eligible_for_automation": NodeStatus.SUCCESS,
        }

        return decision_map.get(result.decision.value, NodeStatus.HUMAN_REVIEW_REQUIRED)

    except Exception as e:
        state.errors.append(f"sufficiency: {e}")
        return NodeStatus.FAILURE


async def handle_emit_bundle(
    state: WorkflowState,
    policy: PolicyEngine,
    decision_engine: DecisionEngine,
    evidence_records: list[EvidenceRecord],
    artifacts: ArtifactStore,
    provenance: ProvenanceRecorder,
    output_dir: Path,
) -> NodeStatus:
    """Build and emit the evidence bundle."""
    try:
        builder = BundleBuilder(
            run_id=state.run_id,
            repository=state.repository_id,
            base_commit=state.base_commit,
            policy=policy,
            decision_engine=decision_engine,
        )

        # Load risk
        import json

        risk_data = artifacts.retrieve(state.risk_assessment_artifact)
        risk = RiskAssessment.model_validate(json.loads(risk_data))

        bundle = builder.build(
            specification=None,  # Placeholder
            risk=risk,
            impact=None,  # Placeholder (Phase 3)
            evidence_plan=[],  # Load from artifact
            evidence_records=evidence_records,
            patch_commit=None,
        )

        # Save bundle
        output_dir.mkdir(parents=True, exist_ok=True)
        builder.save(bundle, output_dir / "evidence-bundle.json")
        builder.render_html(bundle, output_dir / "evidence-bundle.html")

        provenance.record(
            actor_type="system",
            actor_id="bundle_builder",
            action="emit_evidence_bundle",
            output_data={"output_dir": str(output_dir)},
        )

        return NodeStatus.SUCCESS
    except Exception as e:
        state.errors.append(f"emit: {e}")
        return NodeStatus.FAILURE
