"""Test selector for impact analysis.

Given changed symbols, a dependency graph, and coverage data,
selects the most relevant tests with confidence scoring.

Section 13.2 of the Evidence-First Harness specification.
"""

from __future__ import annotations

import subprocess
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from evidence_first_harness.impact.coverage_map import CoverageMap
from evidence_first_harness.impact.graph import DependencyGraph


@dataclass
class TestSelection:
    """Result of test selection for a set of changes."""

    selected_tests: list[str] = field(default_factory=list)
    confidence: float = 0.0
    selection_reasons: dict[str, list[str]] = field(default_factory=dict)
    unknown_areas: list[str] = field(default_factory=list)


class TestSelector:
    """Selects tests based on impact analysis of changed symbols.

    Uses three strategies in descending order of confidence:
    1. Direct symbol coverage (tests that import/use changed symbols)
    2. Dependency-driven (tests for modules that depend on changed modules)
    3. Historical co-change (tests that were changed alongside these files before)
    """

    def __init__(
        self,
        graph: DependencyGraph,
        coverage: CoverageMap | None = None,
        repo_path: Path | None = None,
    ) -> None:
        self._graph = graph
        self._coverage = coverage or CoverageMap.empty()
        self._repo_path = repo_path

    def select(
        self,
        changed_files: list[str],
        changed_symbols: list[str],
    ) -> TestSelection:
        """Select tests for the given changes.

        Args:
            changed_files: List of changed file paths (relative to repo root).
            changed_symbols: List of changed symbol names (qualified).

        Returns:
            TestSelection with selected tests, confidence, and reasoning.
        """
        selection = TestSelection()
        reasons: dict[str, list[str]] = defaultdict(list)
        selected: set[str] = set()

        # Strategy 1: Direct symbol coverage — find tests that import changed modules
        affected_tests = self._graph.find_tests_for_modules(changed_files)
        for tm in affected_tests:
            selected.add(tm.test_file)
            reasons[tm.test_file].append(f"direct import of [{' ,'.join(tm.source_modules)}]")

        # Strategy 2: Dependency-driven — find tests for modules that depend on changed ones
        dependents = self._graph.find_affected_modules(changed_files)
        dependent_tests = self._graph.find_tests_for_modules(dependents)
        for tm in dependent_tests:
            if tm.test_file not in selected:
                selected.add(tm.test_file)
                reasons[tm.test_file].append("transitive dependency")

        # Strategy 3: Historical co-change — git log for files changed together
        if self._repo_path and changed_files:
            co_changed = self._find_co_changed_tests(changed_files)
            for test_file in co_changed:
                if test_file not in selected:
                    selected.add(test_file)
                    reasons[test_file].append("historical co-change")

        # Compute confidence
        confidence = self._compute_confidence(changed_files, list(selected))

        selection.selected_tests = sorted(selected)
        selection.confidence = round(confidence, 2)
        selection.selection_reasons = dict(reasons)
        selection.unknown_areas = self._identify_unknown_areas(changed_files, confidence)

        return selection

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _compute_confidence(self, changed_files: list[str], selected_tests: list[str]) -> float:
        """Compute confidence score for the test selection.

        Factors:
        - Ratio of changed files that have matching tests (direct coverage)
        - Coverage data availability
        - Number of test files selected
        """
        if not changed_files:
            return 1.0

        # Base: how many changed files have at least one matching test?
        files_with_tests: set[str] = set()
        for tm in self._graph.test_mappings:
            for src in tm.source_modules:
                files_with_tests.add(src)

        covered_changed = sum(1 for f in changed_files if f in files_with_tests)
        direct_ratio = covered_changed / len(changed_files) if changed_files else 0.0

        # Coverage bonus
        coverage_bonus = 0.1 if self._coverage.available else 0.0

        # Test count factor: more tests = lower confidence per test
        test_factor = min(1.0, 1.0 / max(1, len(selected_tests) * 0.1))

        return min(0.95, direct_ratio * 0.7 + coverage_bonus + test_factor * 0.2)

    def _find_co_changed_tests(self, changed_files: list[str]) -> list[str]:
        """Find test files that were historically changed alongside these files.

        Uses `git log` to find files that appeared in the same commits.
        """
        if not self._repo_path:
            return []

        test_files: set[str] = set()
        try:
            for changed_file in changed_files[:5]:  # Limit to avoid expensive searches
                result = subprocess.run(
                    [
                        "git",
                        "-C",
                        str(self._repo_path),
                        "log",
                        "--oneline",
                        "--name-only",
                        "-n",
                        "10",
                        "--",
                        changed_file,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if result.returncode != 0:
                    continue
                for line in result.stdout.splitlines():
                    line = line.strip()
                    if line and "/" in line and not line.startswith("#"):
                        name = Path(line).name
                        if name.startswith("test_") or name.endswith("_test.py"):
                            test_files.add(line)
        except (subprocess.TimeoutExpired, OSError):
            pass

        return sorted(test_files)

    def _identify_unknown_areas(
        self,
        changed_files: list[str],
        confidence: float,
    ) -> list[str]:
        """Identify areas where test selection is uncertain.

        Args:
            changed_files: List of changed files.
            confidence: Current confidence score.

        Returns:
            List of unknown impact area descriptions.
        """
        unknown: list[str] = []

        if confidence < 0.5:
            unknown.append(
                f"Low confidence ({confidence:.2f}) in test selection for {len(changed_files)} changed files"
            )

        if not self._coverage.available:
            unknown.append(
                "No coverage data available — test selection based on static analysis only"
            )

        # Check for untested changed files
        files_with_tests: set[str] = set()
        for tm in self._graph.test_mappings:
            files_with_tests.update(tm.source_modules)

        untested = [f for f in changed_files if f not in files_with_tests]
        if untested:
            unknown.append(f"No matching tests found for: {', '.join(untested[:3])}")

        return unknown
