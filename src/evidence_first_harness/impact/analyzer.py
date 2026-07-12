"""Impact analyzer orchestrator.

Top-level component that coordinates AST parsing, dependency graph building,
test selection, and coverage analysis to produce an ImpactReport.

This is the public API that workflow nodes and the CLI consume.

Section 13 of the Evidence-First Harness specification.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import structlog

from evidence_first_harness.domain.impact import ImpactReport
from evidence_first_harness.impact.coverage_map import CoverageMap
from evidence_first_harness.impact.graph import DependencyGraph
from evidence_first_harness.impact.python_ast import (
    ModuleInfo,
    extract_changed_symbols,
    parse_directory,
)
from evidence_first_harness.impact.test_selector import TestSelection, TestSelector

logger = structlog.get_logger()


class ImpactAnalyzer:
    """Analyzes the impact of a code change on a repository.

    Coordinates AST parsing, dependency graph construction, coverage analysis,
    and test selection to produce a structured ImpactReport with confidence scoring.
    """

    def __init__(
        self,
        repo_path: Path,
        coverage_path: Path | None = None,
    ) -> None:
        """Initialize the impact analyzer.

        Args:
            repo_path: Path to the repository root.
            coverage_path: Optional path to coverage.json.
        """
        self._repo_path = repo_path
        self._coverage_path = coverage_path

    def analyze(
        self,
        changed_files: list[str],
        worktree_path: Path | None = None,
    ) -> ImpactReport:
        """Analyze the impact of the given changed files.

        Args:
            changed_files: List of changed file paths (relative to repo root).
            worktree_path: Optional worktree path if changes are in a separate tree.

        Returns:
            A complete ImpactReport with confidence and affected components.
        """
        root = worktree_path or self._repo_path

        # Parse the repository
        modules = parse_directory(root)
        if not modules:
            return ImpactReport(
                changed_files=changed_files,
                confidence=0.0,
                unknown_impact_areas=["No Python modules found in repository"],
            )

        # Build dependency graph
        graph = DependencyGraph.build(modules)

        # Extract changed symbols
        changed_symbols = self._derive_changed_symbols(changed_files, modules)

        # Find affected modules (direct + transitive)
        affected_modules = graph.find_affected_modules(changed_files)

        # Load coverage data
        coverage = self._load_coverage(root)

        # Select tests
        selector = TestSelector(graph=graph, coverage=coverage, repo_path=self._repo_path)
        test_selection = selector.select(changed_files, changed_symbols)

        # Compute confidence
        confidence = test_selection.confidence

        # Identify affected interfaces (public symbols in changed modules)
        affected_interfaces = self._find_affected_interfaces(
            changed_files, modules, graph
        )

        # Identify affected data models (dataclasses, Pydantic models)
        affected_data_models = self._find_affected_data_models(
            changed_files, modules
        )

        return ImpactReport(
            changed_files=changed_files,
            changed_symbols=changed_symbols,
            direct_dependencies=self._extract_direct_deps(changed_files, modules),
            transitive_dependencies=self._extract_transitive_deps(
                changed_files, affected_modules, graph
            ),
            affected_tests=test_selection.selected_tests,
            affected_services=self._find_affected_services(changed_files, modules),
            affected_data_models=affected_data_models,
            affected_interfaces=affected_interfaces,
            confidence=confidence,
            unknown_impact_areas=test_selection.unknown_areas,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _derive_changed_symbols(
        self,
        changed_files: list[str],
        modules: dict[str, ModuleInfo],
    ) -> list[str]:
        """Derive changed symbols from file paths."""
        symbols: list[str] = []
        for cf in changed_files:
            # Try relative and absolute paths
            for key, mod in modules.items():
                if key.endswith(cf) or cf.endswith(key) or cf in key:
                    for sym in mod.symbols:
                        symbols.append(f"{key}::{sym.name}")
                    break
        return symbols

    def _load_coverage(self, root: Path) -> CoverageMap:
        """Try to load coverage data from known locations."""
        candidates = [
            self._coverage_path,
            root / "coverage.json",
            root / ".coverage",
        ]

        for candidate in candidates:
            if candidate and candidate.exists():
                if candidate.suffix == ".json":
                    return CoverageMap.from_json(candidate)
                # .coverage binary — try to convert via `coverage json`
                if candidate.name == ".coverage":
                    try:
                        import subprocess
                        import tempfile

                        with tempfile.NamedTemporaryFile(
                            suffix=".json", delete=False
                        ) as tmp:
                            tmp_path = Path(tmp.name)

                        subprocess.run(
                            ["coverage", "json", "-o", str(tmp_path)],
                            cwd=root,
                            capture_output=True,
                            timeout=30,
                        )
                        if tmp_path.exists():
                            cm = CoverageMap.from_json(tmp_path)
                            tmp_path.unlink(missing_ok=True)
                            return cm
                    except (OSError, subprocess.TimeoutExpired):
                        pass

        return CoverageMap.empty()

    def _extract_direct_deps(
        self, changed_files: list[str], modules: dict[str, ModuleInfo]
    ) -> list[str]:
        """Extract direct dependencies from changed files' imports."""
        deps: set[str] = set()
        for cf in changed_files:
            for key, mod in modules.items():
                if key.endswith(cf) or cf in key:
                    for imp in mod.imports:
                        if not imp.module.startswith("_"):
                            deps.add(imp.module)
        return sorted(deps)

    def _extract_transitive_deps(
        self,
        changed_files: list[str],
        affected_modules: list[str],
        graph: DependencyGraph,
    ) -> list[str]:
        """Extract transitive dependencies (affected modules beyond direct)."""
        direct = set(changed_files)
        transitive = [m for m in affected_modules if m not in direct]
        return sorted(transitive)[:30]  # Cap to avoid explosion

    def _find_affected_interfaces(
        self,
        changed_files: list[str],
        modules: dict[str, ModuleInfo],
        graph: DependencyGraph,
    ) -> list[str]:
        """Find public interfaces affected by the changes."""
        interfaces: list[str] = []

        for cf in changed_files:
            for key, mod in modules.items():
                if key.endswith(cf) or cf in key:
                    for sym in mod.symbols:
                        if not sym.name.startswith("_"):
                            interfaces.append(sym.name)

        return sorted(set(interfaces))[:20]

    def _find_affected_data_models(
        self,
        changed_files: list[str],
        modules: dict[str, ModuleInfo],
    ) -> list[str]:
        """Find data model classes affected by the changes."""
        models: list[str] = []

        for cf in changed_files:
            for key, mod in modules.items():
                if key.endswith(cf) or cf in key:
                    for sym in mod.symbols:
                        if sym.kind == "class":
                            models.append(sym.name)

        return sorted(set(models))

    def _find_affected_services(
        self,
        changed_files: list[str],
        modules: dict[str, ModuleInfo],
    ) -> list[str]:
        """Find service-like classes affected by the changes."""
        services: list[str] = []

        service_suffixes = ("Service", "Manager", "Handler", "Controller")

        for cf in changed_files:
            for key, mod in modules.items():
                if key.endswith(cf) or cf in key:
                    for sym in mod.symbols:
                        if sym.kind == "class" and sym.name.endswith(service_suffixes):
                            services.append(sym.name)

        return sorted(set(services))
