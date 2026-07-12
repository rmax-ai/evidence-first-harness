# Phase 3: Impact-Derived Verification — Implementation Plan

> **For Hermes:** Implement directly — all deterministic Python, no LLM agents.
> Wire into existing workflow (nodes.py, runner.py, CLI).

**Goal:** AST-based impact analysis: identify changed symbols, build dependency graph,
select targeted tests with confidence scoring, feed into evidence planner and CLI output.

**Architecture:** Five modules layered bottom-up:
1. `python_ast.py` — Parse Python source, extract symbols/imports/calls
2. `graph.py` — Build dependency graph from AST data
3. `coverage_map.py` — Parse coverage data (coverage.py JSON, pytest-cov)
4. `test_selector.py` — Select tests from graph + coverage + co-change history
5. `analyzer.py` — Top-level orchestrator: accepts diff + repo → produces ImpactReport

## Acceptance Criteria

- [ ] AST parser extracts top-level functions, classes, methods, imports from Python files
- [ ] Dependency graph links changed symbols to dependent modules and tests
- [ ] Test selector returns test paths + confidence + selection reasons
- [ ] Impact analyzer produces ImpactReport with confidence >= 0.7 for simple diffs
- [ ] Low confidence (< 0.5) correctly triggers "unknown_impact_areas" population
- [ ] Analyzer integrated into workflow nodes (handle_analyze_impact + handle_reclassify_risk)
- [ ] CLI output shows impact summary (changed files, confidence, affected tests)
- [ ] All 8+ new tests pass
- [ ] Existing 35 tests still pass

---

## Implementation Tasks

### Task 1: Create test fixture — sample Python repo

**Files:**
- Create: `tests/fixtures/sample_repo/payments/__init__.py`
- Create: `tests/fixtures/sample_repo/payments/service.py`
- Create: `tests/fixtures/sample_repo/payments/ledger.py`
- Create: `tests/fixtures/sample_repo/payments/auth.py`
- Create: `tests/fixtures/sample_repo/tests/test_service.py`
- Create: `tests/fixtures/sample_repo/tests/test_ledger.py`

Small payment-like service with REST endpoint + idempotency + auth + ledger.
Tests reference the modules. Used for all impact analysis tests.

### Task 2: Implement Python AST analyzer

**Files:**
- Create: `src/evidence_first_harness/impact/python_ast.py`

```python
@dataclass
class ModuleInfo:
    path: str
    imports: list[ImportInfo]
    symbols: list[SymbolInfo]

@dataclass
class SymbolInfo:
    name: str
    kind: str  # "function", "class", "method", "variable"
    file_path: str
    lineno: int

@dataclass
class ImportInfo:
    module: str
    names: list[str]
    lineno: int

def parse_module(file_path: Path) -> ModuleInfo: ...
def parse_directory(root: Path) -> dict[str, ModuleInfo]: ...
```

### Task 3: Implement dependency graph

**Files:**
- Create: `src/evidence_first_harness/impact/graph.py`

Build directed graph: module → imports, symbol → callers.
Map test files to source modules via import patterns.

### Task 4: Implement coverage map parser

**Files:**
- Create: `src/evidence_first_harness/impact/coverage_map.py`

Parse coverage.py JSON output. Map source files → covered lines.
Fall back gracefully when no coverage data exists.

### Task 5: Implement test selector

**Files:**
- Create: `src/evidence_first_harness/impact/test_selector.py`

Given changed symbols + dependency graph + coverage:
- Direct matches: tests that import changed modules
- Coverage matches: tests that cover changed symbols
- Co-change matches: git log --follow for historically co-changed files
- Return TestSelection with confidence + reasons

### Task 6: Implement impact analyzer orchestrator

**Files:**
- Create: `src/evidence_first_harness/impact/analyzer.py`

Accepts repo_path + diff → produces ImpactReport with confidence.
Orchestrates AST parsing, graph building, test selection.
Computes confidence from: match ratio, coverage availability, co-change data presence.

### Task 7: Wire into workflow

**Files:**
- Modify: `src/evidence_first_harness/workflows/nodes.py`
  - Add `handle_analyze_impact()` — calls analyzer, stores artifact
  - Add `handle_reclassify_risk()` — updates risk based on impact
- Modify: `src/evidence_first_harness/workflows/runner.py`
  - Replace placeholder ImpactReport with real analyzer call

### Task 8: Update CLI output

**Files:**
- Modify: `src/evidence_first_harness/cli.py`
  - `efh run` shows impact summary after analysis

### Task 9: Write tests

**Files:**
- Create: `tests/unit/test_impact_analyzer.py`

Tests:
- AST parser extracts symbols from sample_repo
- Dependency graph resolves imports
- Test selector finds relevant tests
- Analyzer returns ImpactReport with confidence > 0
- Empty diff → empty report
- Missing coverage → gracefully degraded confidence
- Low confidence → unknown_impact_areas populated

### Task 10: Update __init__.py

**Files:**
- Modify: `src/evidence_first_harness/impact/__init__.py`

Re-export key types: ImpactAnalyzer, TestSelection, ModuleInfo, etc.
