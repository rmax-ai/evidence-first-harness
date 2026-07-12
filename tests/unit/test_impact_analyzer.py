"""Unit tests for impact analysis modules.

Tests AST parsing, dependency graph construction, coverage map parsing,
test selection, and the top-level impact analyzer.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from evidence_first_harness.domain.impact import ImpactReport
from evidence_first_harness.impact.analyzer import ImpactAnalyzer
from evidence_first_harness.impact.coverage_map import CoverageMap
from evidence_first_harness.impact.graph import DependencyGraph
from evidence_first_harness.impact.python_ast import (
    extract_changed_symbols,
    parse_directory,
    parse_module,
)
from evidence_first_harness.impact.test_selector import TestSelection, TestSelector

SAMPLE_REPO = Path(__file__).parent.parent / "fixtures" / "sample_repo"


@pytest.fixture
def sample_modules() -> dict:
    """Parse the sample repo and return module dict."""
    return parse_directory(SAMPLE_REPO)


@pytest.fixture
def sample_graph(sample_modules: dict) -> DependencyGraph:
    """Build dependency graph from sample repo."""
    return DependencyGraph.build(sample_modules)


# ---------------------------------------------------------------------------
# AST Parser Tests
# ---------------------------------------------------------------------------


class TestASTParser:
    def test_parse_service_module(self) -> None:
        """AST parser extracts all symbols from the sample payment service."""
        svc_path = SAMPLE_REPO / "payments" / "service.py"
        info = parse_module(svc_path)

        # Should have classes: AuthorizationError, Payment, PaymentService, Ledger
        class_names = {s.name for s in info.symbols if s.kind == "class"}
        assert "PaymentService" in class_names
        assert "Ledger" in class_names
        assert "Payment" in class_names
        assert "AuthorizationError" in class_names

        # Methods on PaymentService
        symbol_names = {s.name for s in info.symbols}
        assert "process_payment" in symbol_names
        assert "validate_currency" in symbol_names
        assert "__init__" in symbol_names  # multiple __init__ across classes

        # Verify imports
        import_modules = {imp.module for imp in info.imports}
        assert "dataclasses" in import_modules or "typing" in import_modules
        assert "uuid" in import_modules

    def test_parse_test_module(self) -> None:
        """AST parser extracts test classes and methods."""
        test_path = SAMPLE_REPO / "tests" / "test_service.py"
        info = parse_module(test_path)

        class_names = {s.name for s in info.symbols if s.kind == "class"}
        assert "TestPaymentService" in class_names
        assert "TestLedger" in class_names

        method_names = {s.name for s in info.symbols if s.kind == "method"}
        assert "test_process_payment_success" in method_names
        assert "test_idempotency_prevents_duplicate" in method_names
        assert "test_unauthorized_payment_raises" in method_names

    def test_parse_directory(self, sample_modules: dict) -> None:
        """parse_directory returns all .py files."""
        assert len(sample_modules) >= 2
        # Should have both source and test files
        paths = list(sample_modules.keys())
        has_service = any("service.py" in p for p in paths)
        has_test = any("test_service.py" in p for p in paths)
        assert has_service
        assert has_test

    def test_parse_nonexistent_file(self) -> None:
        """Parsing a nonexistent file returns empty ModuleInfo."""
        info = parse_module(Path("/nonexistent/path.py"))
        assert info.symbols == []
        assert info.imports == []

    def test_parse_non_python_file(self) -> None:
        """Parsing a non-Python file returns empty ModuleInfo."""
        with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False) as f:
            f.write("not valid python {{")
            tmp_path = f.name

        try:
            info = parse_module(Path(tmp_path))
            assert info.symbols == []
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_extract_changed_symbols(self, sample_modules: dict) -> None:
        """extract_changed_symbols finds differences between module snapshots."""
        # Simulate: same modules → no changes
        changes = extract_changed_symbols(sample_modules, sample_modules)
        assert changes == []

        # Simulate: new file added
        empty = {}
        changes = extract_changed_symbols(empty, sample_modules)
        assert len(changes) > 0


# ---------------------------------------------------------------------------
# Dependency Graph Tests
# ---------------------------------------------------------------------------


class TestDependencyGraph:
    def test_build_graph(self, sample_graph: DependencyGraph) -> None:
        """Graph construction creates edges and test mappings."""
        assert len(sample_graph.edges) >= 1
        assert len(sample_graph.test_mappings) >= 1

    def test_test_mapping(self, sample_graph: DependencyGraph) -> None:
        """Test file correctly maps to source module."""
        mappings = sample_graph.test_mappings
        test_mapping = None
        for tm in mappings:
            if "test_service.py" in tm.test_file:
                test_mapping = tm
                break

        assert test_mapping is not None
        assert any("service.py" in src for src in test_mapping.source_modules)
        assert test_mapping.confidence >= 0.9

    def test_find_affected_modules(self, sample_graph: DependencyGraph) -> None:
        """find_affected_modules returns dependents of changed files."""
        # Find the service module path
        svc_path = ""
        for path in sample_graph.modules:
            if path.endswith("service.py"):
                svc_path = path
                break

        assert svc_path, "service.py not found in graph"

        affected = sample_graph.find_affected_modules([svc_path])
        # The test file should be affected (it imports the service)
        has_test = any("test_service.py" in a for a in affected)
        assert has_test, f"Test file not in affected modules: {affected}"

    def test_find_tests_for_modules(self, sample_graph: DependencyGraph) -> None:
        """find_tests_for_modules returns tests for given source modules."""
        svc_path = ""
        for path in sample_graph.modules:
            if path.endswith("service.py"):
                svc_path = path
                break

        test_mappings = sample_graph.find_tests_for_modules([svc_path])
        assert len(test_mappings) >= 1
        assert any("test_service.py" in tm.test_file for tm in test_mappings)


# ---------------------------------------------------------------------------
# Coverage Map Tests
# ---------------------------------------------------------------------------


class TestCoverageMap:
    def test_from_json(self) -> None:
        """CoverageMap parses coverage.py JSON format."""
        coverage_data = {
            "files": {
                "src/app.py": {
                    "executed_lines": [1, 2, 3, 5, 10],
                    "missing_lines": [4, 6, 7],
                    "summary": {
                        "covered_lines": 5,
                        "num_statements": 8,
                        "percent_covered": 62.5,
                    },
                },
            },
            "totals": {
                "covered_lines": 5,
                "num_statements": 8,
                "percent_covered": 62.5,
            },
        }

        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            json.dump(coverage_data, f)
            tmp_path = f.name

        try:
            cm = CoverageMap.from_json(Path(tmp_path))
            assert cm.available is True
            assert cm.overall_coverage_pct == 62.5

            fc = cm.get_coverage("src/app.py")
            assert fc is not None
            assert fc.total_lines == 8
            assert len(fc.covered_lines) == 5
            assert len(fc.uncovered_lines) == 3

            # Symbol coverage check
            symbol_lines = {"init": 1, "bad_func": 4, "good_func": 5}
            covered = cm.symbols_covered("src/app.py", symbol_lines)
            assert covered["init"] is True  # line 1 is covered
            assert covered["bad_func"] is False  # line 4 is uncovered
            assert covered["good_func"] is True  # line 5 is covered
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_empty_map(self) -> None:
        """Empty coverage map reports unavailable."""
        cm = CoverageMap.empty()
        assert cm.available is False
        assert cm.files == {}

    def test_missing_file(self) -> None:
        """Nonexistent coverage file returns empty map."""
        cm = CoverageMap.from_json(Path("/nonexistent/coverage.json"))
        assert cm.available is False


# ---------------------------------------------------------------------------
# Test Selector Tests
# ---------------------------------------------------------------------------


class TestTestSelector:
    def test_select_tests(self, sample_graph: DependencyGraph) -> None:
        """TestSelector returns relevant tests for changed files."""
        selector = TestSelector(graph=sample_graph)

        # Find the service module path
        svc_path = ""
        for path in sample_graph.modules:
            if path.endswith("service.py"):
                svc_path = path
                break

        selection = selector.select(
            changed_files=[svc_path],
            changed_symbols=[],
        )

        assert len(selection.selected_tests) >= 1
        assert any("test_service.py" in t for t in selection.selected_tests)
        assert selection.confidence > 0
        # Should have reasons for each selected test
        for test in selection.selected_tests:
            assert test in selection.selection_reasons

    def test_select_no_changes(self, sample_graph: DependencyGraph) -> None:
        """No changed files returns empty selection with full confidence."""
        selector = TestSelector(graph=sample_graph)
        selection = selector.select(changed_files=[], changed_symbols=[])
        assert selection.confidence == 1.0
        assert selection.selected_tests == []

    def test_selection_reasons(self, sample_graph: DependencyGraph) -> None:
        """Selection includes reasons for each selected test."""
        selector = TestSelector(graph=sample_graph)

        svc_path = ""
        for path in sample_graph.modules:
            if path.endswith("service.py"):
                svc_path = path
                break

        selection = selector.select(
            changed_files=[svc_path],
            changed_symbols=[],
        )

        for test in selection.selected_tests:
            reasons = selection.selection_reasons[test]
            assert len(reasons) >= 1
            assert any(
                "direct import" in r or "transitive" in r or "co-change" in r
                for r in reasons
            )


# ---------------------------------------------------------------------------
# Impact Analyzer Tests
# ---------------------------------------------------------------------------


class TestImpactAnalyzer:
    def test_analyze_sample_repo(self) -> None:
        """ImpactAnalyzer produces ImpactReport for the sample repo."""
        analyzer = ImpactAnalyzer(SAMPLE_REPO)

        # Find changed files
        svc_file = str(SAMPLE_REPO / "payments" / "service.py")

        report = analyzer.analyze(changed_files=[svc_file])

        assert isinstance(report, ImpactReport)
        assert len(report.changed_files) == 1
        assert len(report.changed_symbols) > 0
        assert report.confidence > 0

        # Should have detected some data models (dataclasses)
        assert len(report.affected_data_models) >= 1
        # Should have detected the service class
        assert any("PaymentService" in s for s in report.affected_services)

    def test_analyze_empty_repo(self) -> None:
        """Analyzing a non-Python directory returns low-confidence report."""
        with tempfile.TemporaryDirectory() as tmpdir:
            analyzer = ImpactAnalyzer(Path(tmpdir))
            report = analyzer.analyze(changed_files=["nonexistent.py"])
            assert report.confidence == 0.0
            assert len(report.unknown_impact_areas) >= 1

    def test_analyze_with_specific_files(self) -> None:
        """Analyzer correctly identifies affected components for specific files."""
        analyzer = ImpactAnalyzer(SAMPLE_REPO)

        svc_file = str(SAMPLE_REPO / "payments" / "service.py")

        report = analyzer.analyze(changed_files=[svc_file])

        # Affected tests should include test_service.py
        has_test = any("test_service" in t for t in report.affected_tests)
        assert has_test, f"Expected test_service in affected_tests, got: {report.affected_tests}"

        # Impact confidence should be reasonable
        assert 0.0 < report.confidence <= 1.0

        # Should have direct dependencies (imports from the file)
        assert len(report.direct_dependencies) >= 1
