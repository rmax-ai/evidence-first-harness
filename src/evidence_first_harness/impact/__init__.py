"""Impact analysis — AST dependency graphs, test selection, coverage mapping.

Section 13 of the Evidence-First Harness specification.

Public API:
    ImpactAnalyzer — top-level orchestrator for impact analysis
    TestSelection — result of test selection with confidence scoring
    ModuleInfo — AST-derived module information
    DependencyGraph — import/symbol dependency graph
    CoverageMap — per-file coverage data
"""

from evidence_first_harness.impact.analyzer import ImpactAnalyzer
from evidence_first_harness.impact.coverage_map import CoverageMap
from evidence_first_harness.impact.graph import DependencyGraph
from evidence_first_harness.impact.python_ast import (
    ModuleInfo,
    SymbolInfo,
    parse_directory,
    parse_module,
)
from evidence_first_harness.impact.test_selector import TestSelection, TestSelector

__all__ = [
    "CoverageMap",
    "DependencyGraph",
    "ImpactAnalyzer",
    "ModuleInfo",
    "SymbolInfo",
    "TestSelection",
    "TestSelector",
    "parse_directory",
    "parse_module",
]
