"""Dependency graph for Python repositories.

Builds a directed graph of module dependencies, symbol references,
and test-to-source mappings from AST-derived ModuleInfo data.

Section 13.1 of the Evidence-First Harness specification.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from evidence_first_harness.impact.python_ast import ModuleInfo


@dataclass
class DependencyEdge:
    """An edge in the dependency graph between two modules or symbols."""

    source: str  # source file path or qualified symbol
    target: str  # target file path or qualified symbol
    kind: str  # "import", "call", "inheritance", "test_coverage"


@dataclass
class TestMapping:
    """Mapping from a test file to the source modules it exercises."""

    test_file: str
    source_modules: list[str] = field(default_factory=list)
    source_symbols: list[str] = field(default_factory=list)
    confidence: float = 1.0  # How confident we are in the mapping (1.0 = import-based)


@dataclass
class DependencyGraph:
    """Complete dependency graph for a repository snapshot."""

    modules: dict[str, ModuleInfo] = field(default_factory=dict)
    edges: list[DependencyEdge] = field(default_factory=list)
    test_mappings: list[TestMapping] = field(default_factory=list)
    # Fast lookup indexes (built during construction)
    _module_by_path: dict[str, ModuleInfo] = field(default_factory=dict)
    _importers_of: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    _symbol_to_file: dict[str, str] = field(default_factory=dict)

    @classmethod
    def build(cls, modules: dict[str, ModuleInfo]) -> "DependencyGraph":
        """Build a dependency graph from a module snapshot.

        Args:
            modules: Dict mapping file path to ModuleInfo (from parse_directory).

        Returns:
            A complete DependencyGraph with edges and test mappings.
        """
        graph = cls(modules=modules)
        graph._module_by_path = modules

        # Index: symbol name → file path
        for file_path, mod in modules.items():
            for sym in mod.symbols:
                graph._symbol_to_file[sym.name] = file_path

        # Build import edges
        for file_path, mod in modules.items():
            for imp in mod.imports:
                # Try to resolve the import target
                target_path = graph._resolve_import(file_path, imp.module)
                if target_path:
                    graph._importers_of[target_path].append(file_path)
                    graph.edges.append(
                        DependencyEdge(
                            source=file_path,
                            target=target_path,
                            kind="import",
                        )
                    )

        # Map tests to source modules
        graph._build_test_mappings()

        return graph

    def find_affected_modules(self, changed_files: list[str]) -> list[str]:
        """Find all modules affected by changes in the given files.

        Includes both direct and transitive dependents.

        Args:
            changed_files: List of changed file paths.

        Returns:
            Sorted list of all affected module paths (direct + transitive).
        """
        affected: set[str] = set(changed_files)
        queue = list(changed_files)

        while queue:
            current = queue.pop(0)
            for importer in self._importers_of.get(current, []):
                if importer not in affected:
                    affected.add(importer)
                    queue.append(importer)

        return sorted(affected)

    def find_tests_for_modules(self, module_paths: list[str]) -> list[TestMapping]:
        """Find test files that exercise the given source modules.

        Args:
            module_paths: List of source module paths.

        Returns:
            List of TestMappings for tests that cover these modules.
        """
        module_set = set(module_paths)
        return [tm for tm in self.test_mappings if any(m in module_set for m in tm.source_modules)]

    def find_tests_for_symbols(self, symbol_names: list[str]) -> list[TestMapping]:
        """Find test files that exercise the given symbols.

        Args:
            symbol_names: List of symbol names.

        Returns:
            List of TestMappings for tests that reference these symbols.
        """
        result: list[TestMapping] = []
        symbol_set = set(symbol_names)

        for tm in self.test_mappings:
            if any(s in symbol_set for s in tm.source_symbols):
                result.append(tm)

        return result

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _resolve_import(self, importer_path: str, import_module: str) -> str | None:
        """Resolve an import statement to a file path in the repository.

        Args:
            importer_path: Path of the file doing the import.
            import_module: The module being imported (e.g., "payments.service").

        Returns:
            Resolved file path or None if unresolvable.
        """
        import_dir = str(Path(importer_path).parent)

        # Try: import payments.service → payments/service.py
        as_path = import_module.replace(".", "/") + ".py"
        for base in [import_dir, str(Path(import_dir).parent)]:
            candidate = str(Path(base) / as_path)
            if candidate in self._module_by_path:
                return candidate

        # Try: from payments.service import X → payments/service.py
        if import_module in self._module_by_path:
            return import_module

        return None

    def _build_test_mappings(self) -> None:
        """Build test-to-source mappings by analyzing imports in test files."""
        for file_path, mod in self.modules.items():
            if not self._is_test_file(file_path):
                continue

            mapping = TestMapping(test_file=file_path)
            source_modules: set[str] = set()
            source_symbols: set[str] = set()

            for imp in mod.imports:
                target_path = self._resolve_import(file_path, imp.module)
                if target_path and not self._is_test_file(target_path):
                    source_modules.add(target_path)
                    # Add imported symbols
                    target_mod = self._module_by_path.get(target_path)
                    if target_mod:
                        for name in imp.names:
                            # Check if this name is a symbol in the target module
                            if any(s.name == name for s in target_mod.symbols):
                                source_symbols.add(name)
                            # Also add direct references
                            source_symbols.update(
                                s.name for s in target_mod.symbols if s.name in imp.names
                            )

            mapping.source_modules = sorted(source_modules)
            mapping.source_symbols = sorted(source_symbols)
            mapping.confidence = 1.0 if source_modules else 0.3

            if source_modules:
                self.test_mappings.append(mapping)

    @staticmethod
    def _is_test_file(file_path: str) -> bool:
        """Check if a file is a test file by name or parent directory."""
        path = Path(file_path)
        name = path.name
        if name.startswith("test_") or name.endswith("_test.py"):
            return True
        # Check if the immediate parent directory is a test directory
        parts = path.parts
        if len(parts) >= 2 and parts[-2] in ("tests", "test"):
            return True
        return False
