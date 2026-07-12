"""Evidence bundle builder — assembles the final evidence package.

Sections 10.6 and 20 of the spec. Gathers all artifacts, evidence records,
decisions, and provenance into a single verifiable EvidenceBundle.
"""

from __future__ import annotations

import json
from pathlib import Path

import structlog

from evidence_first_harness.domain.evidence import (
    EvidenceBundle,
    EvidenceRecord,
    EvidenceRequirement,
)
from evidence_first_harness.domain.impact import ImpactReport
from evidence_first_harness.domain.risk import RiskAssessment
from evidence_first_harness.domain.specification import CompiledSpecification
from evidence_first_harness.policy.decision import DecisionEngine
from evidence_first_harness.policy.engine import PolicyEngine

logger = structlog.get_logger()


class BundleBuilder:
    """Assembles an EvidenceBundle from all collected artifacts.

    The bundle is the primary output of the harness — not the patch.
    """

    def __init__(
        self,
        run_id: str,
        repository: str,
        base_commit: str,
        policy: PolicyEngine,
        decision_engine: DecisionEngine,
    ) -> None:
        self._run_id = run_id
        self._repository = repository
        self._base_commit = base_commit
        self._policy = policy
        self._decision_engine = decision_engine

    def build(
        self,
        specification: CompiledSpecification | None,
        risk: RiskAssessment | None,
        impact: ImpactReport | None,
        evidence_plan: list[EvidenceRequirement],
        evidence_records: list[EvidenceRecord],
        patch_commit: str | None = None,
        unsupported_claims: list[str] | None = None,
        contradictions: list[str] | None = None,
        limitations: list[str] | None = None,
        provenance: dict | None = None,
        repair_attempts: int = 0,
        approved_roles: list[str] | None = None,
    ) -> EvidenceBundle:
        """Build the complete evidence bundle.

        Args:
            specification: The compiled specification.
            risk: The risk assessment.
            impact: The impact report.
            evidence_plan: The evidence requirements.
            evidence_records: All executed evidence records.
            patch_commit: The commit hash of the proposed patch.
            unsupported_claims: Claims without evidence.
            contradictions: Contradictions found in evidence.
            limitations: Known limitations.
            provenance: Provenance data.
            repair_attempts: Number of repair cycles attempted.
            approved_roles: Roles that have approved.

        Returns:
            A complete EvidenceBundle with sufficiency assessment and decision.
        """
        unsupported_claims = unsupported_claims or []
        contradictions = contradictions or []
        limitations = limitations or []
        approved_roles = approved_roles or []

        # Evaluate sufficiency
        tier = risk.overall_tier if risk else 3
        impact_confidence = impact.confidence if impact else 0.0

        sufficiency = self._policy.evaluate_sufficiency(
            tier=tier,
            evidence_records=evidence_records,
            impact_confidence=impact_confidence,
            contradictions=contradictions,
        )

        # Produce decision
        if risk:
            required_ids = [r.id for r in evidence_plan]
            approval_roles = self._policy.get_approval_roles(tier)

            decision_result = self._decision_engine.decide(
                risk=risk,
                evidence_records=evidence_records,
                required_evidence_ids=required_ids,
                impact_confidence=impact_confidence,
                contradictions=contradictions,
                repair_attempts=repair_attempts,
                max_repair_attempts=self._policy.get_retry_policy()["evidence_repair_attempts"],
                approval_roles=approval_roles,
                approved_roles=approved_roles,
            )
            decision_dict = decision_result.model_dump()
        else:
            decision_dict = {"decision": "unknown", "rationale": "No risk assessment available"}

        # Build the bundle
        bundle = EvidenceBundle(
            schema_version="1.0",
            run_id=self._run_id,
            repository=self._repository,
            base_commit=self._base_commit,
            patch_commit=patch_commit,
            specification=specification,
            risk=risk,
            impact=impact,
            evidence_plan=evidence_plan,
            evidence=evidence_records,
            unsupported_claims=unsupported_claims,
            contradictions=contradictions,
            limitations=limitations,
            provenance=provenance or {},
            sufficiency=sufficiency,
            decision=decision_dict,
        )

        logger.info(
            "bundle_built",
            run_id=self._run_id,
            evidence_count=len(evidence_records),
            decision=decision_dict.get("decision", "unknown"),
        )

        return bundle

    def save(self, bundle: EvidenceBundle, output_path: Path) -> Path:
        """Save the evidence bundle as JSON to disk.

        Args:
            bundle: The bundle to save.
            output_path: Path to write the JSON file.

        Returns:
            The path where the bundle was saved.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        data = bundle.model_dump(mode="json")
        output_path.write_text(json.dumps(data, indent=2))
        logger.info("bundle_saved", path=str(output_path))
        return output_path

    def render_html(self, bundle: EvidenceBundle, output_path: Path) -> Path:
        """Render the evidence bundle as a standalone HTML page.

        Args:
            bundle: The bundle to render.
            output_path: Path to write the HTML file.

        Returns:
            The path where the HTML was saved.
        """
        decision = bundle.decision.get("decision", "unknown")
        risk_tier = bundle.risk.overall_tier if bundle.risk else "?"

        evidence_rows = ""
        for record in bundle.evidence:
            status_class = {
                "pass": "pass",
                "fail": "fail",
                "partial": "partial",
                "error": "fail",
                "unavailable": "unavailable",
            }.get(record.status, "")
            evidence_rows += f"""
            <tr class="{status_class}">
                <td>{record.executor}</td>
                <td class="status-{status_class}">{record.status.upper()}</td>
                <td>{record.summary}</td>
                <td>{record.metrics}</td>
            </tr>"""

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Evidence Bundle — {bundle.run_id}</title>
<style>
body {{ font-family: system-ui, sans-serif; max-width: 960px; margin: 2rem auto; padding: 0 1rem; color: #1a1a2e; background: #f8f9fa; }}
h1 {{ border-bottom: 2px solid #dee2e6; padding-bottom: 0.5rem; }}
.meta {{ color: #6c757d; font-size: 0.9rem; }}
table {{ width: 100%; border-collapse: collapse; margin: 1rem 0; }}
th, td {{ padding: 0.5rem; text-align: left; border-bottom: 1px solid #dee2e6; }}
th {{ background: #e9ecef; }}
.pass {{ background: #d4edda; }}
.fail {{ background: #f8d7da; }}
.partial {{ background: #fff3cd; }}
.unavailable {{ background: #e2e3e5; }}
.status-pass {{ color: #155724; font-weight: bold; }}
.status-fail {{ color: #721c24; font-weight: bold; }}
.decision {{ font-size: 1.2rem; font-weight: bold; padding: 1rem; border-radius: 4px; margin: 1rem 0; }}
.decision-eligible {{ background: #d4edda; color: #155724; }}
.decision-rejected {{ background: #f8d7da; color: #721c24; }}
.decision-review {{ background: #fff3cd; color: #856404; }}
.limitations {{ background: #e2e3e5; padding: 1rem; border-radius: 4px; }}
</style>
</head>
<body>
<h1>Evidence Bundle</h1>
<p class="meta">Run: {bundle.run_id} | Repository: {bundle.repository} | Base: {bundle.base_commit[:8]}</p>

<h2>Decision</h2>
<div class="decision decision-{decision}">
Decision: <strong>{decision.upper().replace("_", " ")}</strong>
<br>Risk Tier: {risk_tier}
</div>

<h2>Evidence Results</h2>
<table>
<tr><th>Executor</th><th>Status</th><th>Summary</th><th>Metrics</th></tr>
{evidence_rows}
</table>

<h2>Limitations</h2>
<div class="limitations">
<ul>
{"".join(f"<li>{lim}</li>" for lim in bundle.limitations) if bundle.limitations else "<li>None recorded</li>"}
</ul>
</div>

<h2>Sufficiency</h2>
<pre>{json.dumps(bundle.sufficiency, indent=2)}</pre>

<h2>Provenance</h2>
<pre>{json.dumps(bundle.provenance, indent=2)}</pre>
</body>
</html>"""

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html)
        logger.info("bundle_html_rendered", path=str(output_path))
        return output_path
