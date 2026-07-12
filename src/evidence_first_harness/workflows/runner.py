"""Evidence runner orchestrator — ties all Phase 1 components together.

Coordinates repository intake, worktree creation, evidence plan compilation,
executor dispatch, evidence collection, decision rendering, and bundle creation.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, UTC
from pathlib import Path

import structlog

from evidence_first_harness.artifacts.store import ArtifactStore
from evidence_first_harness.callbacks.provenance import ProvenanceRecorder
from evidence_first_harness.domain.decision import Decision
from evidence_first_harness.domain.evidence import (
    EvidenceBundle,
    EvidenceRecord,
    EvidenceRequirement,
)
from evidence_first_harness.domain.exceptions import EvidenceError
from evidence_first_harness.domain.impact import ImpactReport
from evidence_first_harness.domain.risk import RiskAssessment, RiskDimension
from evidence_first_harness.domain.specification import CompiledSpecification
from evidence_first_harness.evidence.bundle import BundleBuilder
from evidence_first_harness.evidence.executors.base import EvidenceExecutionContext
from evidence_first_harness.evidence.planner import EvidencePlanner
from evidence_first_harness.policy.decision import DecisionEngine
from evidence_first_harness.policy.engine import PolicyEngine
from evidence_first_harness.repository.git import RepositoryManager

logger = structlog.get_logger()


class EvidenceRunner:
    """Orchestrates the evidence-first workflow for a single repository."""

    def __init__(
        self,
        repo_path: Path | str,
        policy_path: Path | str = "config/policies.yaml",
        artifact_dir: Path | str = ".artifacts",
    ) -> None:
        self._repo = RepositoryManager(repo_path)
        self._policy = PolicyEngine(policy_path)
        self._decision_engine = DecisionEngine()
        self._planner = EvidencePlanner(self._policy)
        self._artifacts = ArtifactStore(artifact_dir)
        self._run_id = f"run_{uuid.uuid4().hex[:12]}"
        self._provenance = ProvenanceRecorder(
            self._run_id, Path(artifact_dir) / "provenance"
        )

    @property
    def run_id(self) -> str:
        return self._run_id

    async def run_existing_patch(
        self,
        patch_path: Path | str | None = None,
        specification: CompiledSpecification | None = None,
        risk: RiskAssessment | None = None,
    ) -> EvidenceBundle:
        """Evaluate an existing patch and produce an evidence bundle.

        This is the Phase 1 MVP workflow — no implementation agent yet.
        Evaluates a human-created patch against the policy.

        Args:
            patch_path: Path to a .patch or .diff file to evaluate.
            specification: Optional pre-compiled specification.
            risk: Optional pre-computed risk assessment.

        Returns:
            A complete EvidenceBundle with evidence and decision.
        """
        self._provenance.record(
            actor_type="system",
            actor_id="evidence_runner",
            action="run_existing_patch_start",
            input_data={"patch_path": str(patch_path) if patch_path else None},
        )

        # Create worktree for evaluation
        worktree = self._repo.create_worktree()

        try:
            base_commit = self._repo.base_commit

            # If patch provided, apply it to the worktree
            patch_commit = None
            if patch_path:
                patch_content = Path(patch_path).read_text()
                # Apply patch to worktree
                import subprocess

                subprocess.run(
                    ["git", "apply", str(Path(patch_path).resolve())],
                    cwd=worktree.path,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=True,
                )
                patch_commit = worktree.commit("efh: apply evaluated patch")

            # Compile risk if not provided
            if risk is None:
                risk = self._default_risk()

            # Build impact report (placeholder in Phase 1)
            impact = ImpactReport(
                changed_files=list(
                    {str(p.relative_to(worktree.path)) for p in worktree.path.rglob("*.py")}
                )[:20],  # top-level approximation
                confidence=0.5,  # low confidence without AST analysis (Phase 3)
            )

            # Compile evidence plan
            evidence_plan = self._planner.compile(risk=risk, impact=impact)

            # Build execution context
            context = EvidenceExecutionContext(
                worktree_path=worktree.path,
                timeout_seconds=120,
            )

            # Execute all evidence checks in cost order
            evidence_records = await self._execute_evidence(evidence_plan, context)

            # Build the bundle
            builder = BundleBuilder(
                run_id=self._run_id,
                repository=str(self._repo.repo_path),
                base_commit=base_commit,
                policy=self._policy,
                decision_engine=self._decision_engine,
            )

            bundle = builder.build(
                specification=specification,
                risk=risk,
                impact=impact,
                evidence_plan=evidence_plan,
                evidence_records=evidence_records,
                patch_commit=patch_commit,
            )

            # Save bundle
            output_dir = Path(self._artifacts._root) / self._run_id
            output_dir.mkdir(parents=True, exist_ok=True)
            builder.save(bundle, output_dir / "evidence-bundle.json")
            builder.render_html(bundle, output_dir / "evidence-bundle.html")

            self._provenance.record(
                actor_type="system",
                actor_id="evidence_runner",
                action="run_existing_patch_complete",
                output_data={"decision": bundle.decision.get("decision")},
            )

            return bundle

        finally:
            self._repo.remove_worktree(worktree)

    async def _execute_evidence(
        self,
        plan: list[EvidenceRequirement],
        context: EvidenceExecutionContext,
    ) -> list[EvidenceRecord]:
        """Execute all evidence checks in the plan.

        Runs checks in cost order. Independent checks may run in parallel.
        """
        # Discover executors
        executors = self._discover_executors()
        executor_map = {ex.name: ex for ex in executors}

        records: list[EvidenceRecord] = []

        for requirement in plan:
            executor = executor_map.get(requirement.executor)
            if executor is None:
                logger.warning(
                    "executor_not_found",
                    executor_name=requirement.executor,
                    run_id=self._run_id,
                )
                # Create an unavailable record
                now = datetime.now(UTC)
                records.append(
                    EvidenceRecord(
                        id=f"rec_{requirement.id}",
                        requirement_id=requirement.id,
                        status="unavailable",
                        executor=requirement.executor,
                        started_at=now,
                        completed_at=now,
                        summary=f"Executor not found: {requirement.executor}",
                        limitations=["Executor not registered"],
                    )
                )
                continue

            self._provenance.record(
                actor_type="system",
                actor_id="evidence_runner",
                action="execute_evidence",
                tool=requirement.executor,
                input_data={"requirement_id": requirement.id},
            )

            try:
                record = await executor.execute(context, requirement)
                records.append(record)
                logger.info(
                    "evidence_executed",
                    executor=requirement.executor,
                    status=record.status,
                )
            except Exception as e:
                logger.error(
                    "evidence_execution_failed",
                    executor=requirement.executor,
                    error=str(e),
                )
                now = datetime.now(UTC)
                records.append(
                    EvidenceRecord(
                        id=f"rec_{requirement.id}",
                        requirement_id=requirement.id,
                        status="error",
                        executor=requirement.executor,
                        started_at=now,
                        completed_at=now,
                        summary=f"Execution error: {e}",
                        limitations=[str(e)],
                    )
                )

        return records

    def _discover_executors(self) -> list:
        """Discover available evidence executors via registration."""
        executors = []

        # Import all known executors
        try:
            from evidence_first_harness.evidence.executors.ruff import RuffExecutor
            executors.append(RuffExecutor())
        except ImportError:
            pass

        try:
            from evidence_first_harness.evidence.executors.pyright import PyrightExecutor
            executors.append(PyrightExecutor())
        except ImportError:
            pass

        try:
            from evidence_first_harness.evidence.executors.pytest import PytestExecutor
            executors.append(PytestExecutor())
        except ImportError:
            pass

        try:
            from evidence_first_harness.evidence.executors.coverage import CoverageExecutor
            executors.append(CoverageExecutor())
        except ImportError:
            pass

        try:
            from evidence_first_harness.evidence.executors.semgrep import SemgrepExecutor
            executors.append(SemgrepExecutor())
        except ImportError:
            pass

        try:
            from evidence_first_harness.evidence.executors.secrets import SecretScanExecutor
            executors.append(SecretScanExecutor())
        except ImportError:
            pass

        try:
            from evidence_first_harness.evidence.executors.dependency import DependencyExecutor
            executors.append(DependencyExecutor())
        except ImportError:
            pass

        try:
            from evidence_first_harness.evidence.executors.mutation import MutationExecutor
            executors.append(MutationExecutor())
        except ImportError:
            pass

        try:
            from evidence_first_harness.evidence.executors.gitdiff import GitDiffExecutor
            executors.append(GitDiffExecutor())
        except ImportError:
            pass

        return executors

    @staticmethod
    def _default_risk() -> RiskAssessment:
        """Return a default low-risk assessment."""
        return RiskAssessment(
            regulatory_impact=RiskDimension(level="low", rationale="Not assessed"),
            customer_proximity=RiskDimension(level="low", rationale="Not assessed"),
            reversibility=RiskDimension(level="high", rationale="Git revert available"),
            data_sensitivity=RiskDimension(level="low", rationale="Not assessed"),
            operational_blast_radius=RiskDimension(level="low", rationale="Single change"),
            security_impact=RiskDimension(level="low", rationale="Not assessed"),
            repository_uncertainty=RiskDimension(level="low", rationale="Not assessed"),
            overall_tier=3,
        )
