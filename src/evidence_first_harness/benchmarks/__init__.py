"""Research benchmark runner for the Evidence-First Harness.

Section 25-26 of the spec. Runs controlled experiments with seeded defects
across multiple conditions and generates statistical analysis reports.

Usage:
    from evidence_first_harness.benchmarks.runner import BenchmarkRunner
    runner = BenchmarkRunner(config_path)
    results = runner.run()
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class ScenarioResult:
    """Result for a single seeded-defect scenario across one condition."""

    scenario_id: str
    scenario_name: str
    condition: str  # "A", "B", "C", "D", "E"
    decision: str = "unknown"
    defect_detected: bool = False
    escaped: bool = True
    detection_evidence: list[str] = field(default_factory=list)
    execution_time_seconds: float = 0.0
    evidence_count: int = 0
    mutation_score: float | None = None
    confidence: float = 0.0
    errors: list[str] = field(default_factory=list)


@dataclass
class BenchmarkReport:
    """Aggregated benchmark report with statistical analysis."""

    config_path: str
    total_scenarios: int = 0
    conditions_tested: list[str] = field(default_factory=list)
    results: list[ScenarioResult] = field(default_factory=list)

    # Aggregated metrics
    escaped_defect_rate: float = 0.0
    defect_detection_recall: float = 0.0
    false_positive_rate: float = 0.0
    avg_mutation_score: float = 0.0
    avg_execution_time: float = 0.0
    avg_evidence_count: float = 0.0

    # Per-condition breakdown
    per_condition: dict[str, dict[str, float]] = field(default_factory=dict)


class BenchmarkRunner:
    """Runs research benchmarks against the harness or a coding agent.

    Loads a benchmark config YAML, iterates through scenarios × conditions,
    collects results, and produces a statistical report.
    """

    def __init__(self, config_path: Path | str) -> None:
        self._config_path = Path(config_path)
        self._config = yaml.safe_load(self._config_path.read_text())
        self._work_dir = Path(self._config.get("paths", {}).get("work_dir", "benchmarks/work"))
        self._reports_dir = Path(self._config.get("paths", {}).get("reports_dir", "benchmarks/reports"))
        self._reports_dir.mkdir(parents=True, exist_ok=True)

    def run(
        self,
        conditions: list[str] | None = None,
        scenarios: list[str] | None = None,
    ) -> BenchmarkReport:
        """Run the benchmark.

        Args:
            conditions: List of conditions to test (default: all configured).
            scenarios: List of scenario IDs to test (default: all configured).

        Returns:
            BenchmarkReport with aggregated results and statistical analysis.
        """
        all_conditions = self._config.get("conditions", {})
        all_scenarios = self._config.get("scenarios", [])

        target_conditions = conditions or list(all_conditions.keys())
        target_scenario_ids = scenarios or [s["id"] for s in all_scenarios]

        report = BenchmarkReport(
            config_path=str(self._config_path),
            conditions_tested=target_conditions,
            total_scenarios=len(target_scenario_ids) * len(target_conditions),
        )

        # Run each scenario × condition
        for scenario_def in all_scenarios:
            if scenario_def["id"] not in target_scenario_ids:
                continue

            for condition_id in target_conditions:
                if condition_id not in all_conditions:
                    continue

                condition_def = all_conditions[condition_id]
                result = self._run_scenario(scenario_def, condition_id, condition_def)
                report.results.append(result)

        # Compute aggregate metrics
        self._compute_metrics(report)
        self._generate_report(report)

        return report

    def _run_scenario(
        self,
        scenario: dict[str, Any],
        condition_id: str,
        condition: dict[str, Any],
    ) -> ScenarioResult:
        """Run a single scenario-condition pair.

        Currently simulates results based on scenario metadata.
        Full integration requires live harness runs against seeded repos.
        """
        start = time.monotonic()

        result = ScenarioResult(
            scenario_id=scenario["id"],
            scenario_name=scenario["name"],
            condition=condition_id,
        )

        # Extract what evidence types this scenario needs for detection
        detection_requires = set(scenario.get("detection_requires", []))

        # Simulate: check if the condition's policy would include the needed evidence
        policy_name = condition.get("harness_policy", "tier_3_minimal")
        if policy_name == "tier_3_minimal":
            # Tier 3: formatting, lint, type_check, targeted_tests, secret_scan
            available_evidence = {"formatting", "lint", "type_check", "targeted_tests", "secret_scan"}
        elif policy_name == "tier_2_standard":
            available_evidence = {"formatting", "lint", "type_check", "targeted_tests", "integration_tests", "security_scan", "mutation_test"}
        elif policy_name == "tier_2_mutation":
            available_evidence = {"formatting", "lint", "type_check", "targeted_tests", "integration_tests", "security_scan", "mutation_test"}
        elif policy_name == "tier_1_full":
            available_evidence = {"formatting", "lint", "type_check", "targeted_tests", "integration_tests", "contract_tests", "security_scan", "dependency_scan", "mutation_test"}
        else:
            available_evidence = set()

        # Detect if the scenario's required evidence is available
        detected = detection_requires.intersection(available_evidence)
        result.defect_detected = len(detected) > 0
        result.escaped = not result.defect_detected
        result.detection_evidence = sorted(detected)
        result.confidence = min(1.0, len(detected) / max(1, len(detection_requires)))

        if result.escaped:
            result.errors.append(
                f"Defect escaped: requires {detection_requires}, "
                f"but condition {condition_id} only provides {available_evidence}"
            )

        result.execution_time_seconds = time.monotonic() - start
        result.evidence_count = len(detected)

        return result

    def _compute_metrics(self, report: BenchmarkReport) -> None:
        """Compute aggregate metrics from scenario results."""
        if not report.results:
            return

        total = len(report.results)
        escaped = sum(1 for r in report.results if r.escaped)
        detected = total - escaped

        report.escaped_defect_rate = escaped / total if total > 0 else 0.0
        report.defect_detection_recall = detected / total if total > 0 else 0.0
        report.false_positive_rate = 0.0  # No false positives in simulation mode
        report.avg_mutation_score = sum(
            r.mutation_score or 0.0 for r in report.results
        ) / total if total > 0 else 0.0
        report.avg_execution_time = sum(
            r.execution_time_seconds for r in report.results
        ) / total if total > 0 else 0.0
        report.avg_evidence_count = sum(
            r.evidence_count for r in report.results
        ) / total if total > 0 else 0.0

        # Per-condition breakdown
        for condition_id in report.conditions_tested:
            cond_results = [r for r in report.results if r.condition == condition_id]
            if not cond_results:
                continue
            c_total = len(cond_results)
            c_escaped = sum(1 for r in cond_results if r.escaped)
            report.per_condition[condition_id] = {
                "scenarios": c_total,
                "escaped_defects": c_escaped,
                "escaped_rate": c_escaped / c_total if c_total > 0 else 0.0,
                "avg_confidence": sum(r.confidence for r in cond_results) / c_total,
            }

    def _generate_report(self, report: BenchmarkReport) -> None:
        """Generate and save the benchmark report as JSON + markdown."""
        report_id = time.strftime("%Y%m%d_%H%M%S")

        # JSON report
        json_path = self._reports_dir / f"benchmark_{report_id}.json"
        json_path.write_text(json.dumps(
            {
                "config": report.config_path,
                "conditions": report.conditions_tested,
                "total_scenarios": report.total_scenarios,
                "escaped_defect_rate": report.escaped_defect_rate,
                "defect_detection_recall": report.defect_detection_recall,
                "false_positive_rate": report.false_positive_rate,
                "avg_mutation_score": report.avg_mutation_score,
                "avg_execution_time": report.avg_execution_time,
                "avg_evidence_count": report.avg_evidence_count,
                "per_condition": report.per_condition,
                "results": [
                    {
                        "scenario_id": r.scenario_id,
                        "scenario_name": r.scenario_name,
                        "condition": r.condition,
                        "defect_detected": r.defect_detected,
                        "escaped": r.escaped,
                        "detection_evidence": r.detection_evidence,
                        "confidence": r.confidence,
                        "errors": r.errors,
                    }
                    for r in report.results
                ],
            },
            indent=2,
        ))

        # Markdown report
        md_path = self._reports_dir / f"benchmark_{report_id}.md"
        md_lines = [
            "# Evidence-First Harness — Benchmark Report",
            "",
            f"**Generated:** {time.strftime('%Y-%m-%d %H:%M:%S UTC')}",
            f"**Config:** {report.config_path}",
            f"**Conditions:** {', '.join(report.conditions_tested)}",
            f"**Total scenarios:** {report.total_scenarios}",
            "",
            "## Aggregate Metrics",
            "",
            f"| Metric | Value |",
            f"|---|---|",
            f"| Escaped defect rate | {report.escaped_defect_rate:.2%} |",
            f"| Defect detection recall | {report.defect_detection_recall:.2%} |",
            f"| False positive rate | {report.false_positive_rate:.2%} |",
            f"| Avg mutation score | {report.avg_mutation_score:.2f} |",
            f"| Avg execution time | {report.avg_execution_time:.3f}s |",
            f"| Avg evidence count | {report.avg_evidence_count:.1f} |",
            "",
            "## Per-Condition Breakdown",
            "",
        ]

        for c_id, metrics in sorted(report.per_condition.items()):
            cond_name = self._config.get("conditions", {}).get(c_id, {}).get("name", c_id)
            md_lines.append(f"### Condition {c_id}: {cond_name}")
            md_lines.append(f"- Scenarios: {metrics['scenarios']}")
            md_lines.append(f"- Escaped defects: {metrics['escaped_defects']}")
            md_lines.append(f"- Escaped rate: {metrics['escaped_rate']:.2%}")
            md_lines.append(f"- Avg confidence: {metrics['avg_confidence']:.2f}")
            md_lines.append("")

        md_lines.append("## Hypothesis Evaluation")
        md_lines.append("")
        md_lines.append("*Full statistical analysis requires live harness runs against seeded repositories.*")
        md_lines.append("")

        md_path.write_text("\n".join(md_lines))

        print(f"Benchmark report saved:")
        print(f"  JSON: {json_path}")
        print(f"  Markdown: {md_path}")

    def print_summary(self, report: BenchmarkReport) -> None:
        """Print a compact summary to stdout."""
        print(f"\n{'='*60}")
        print(f"Benchmark Results — {report.config_path}")
        print(f"{'='*60}")
        print(f"Scenarios: {report.total_scenarios}")
        print(f"Conditions: {', '.join(report.conditions_tested)}")
        print(f"\nEscaped defect rate: {report.escaped_defect_rate:.2%}")
        print(f"Detection recall:   {report.defect_detection_recall:.2%}")
        print(f"False positive rate: {report.false_positive_rate:.2%}")
        print(f"Avg evidence count:  {report.avg_evidence_count:.1f}")

        if report.per_condition:
            print(f"\nPer condition:")
            for c_id, metrics in sorted(report.per_condition.items()):
                cond_name = self._config.get("conditions", {}).get(c_id, {}).get("name", c_id)
                print(f"  {c_id}: {metrics['escaped_rate']:.2%} escaped ({metrics['escaped_defects']}/{metrics['scenarios']})")
