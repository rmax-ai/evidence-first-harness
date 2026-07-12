"""Python AST analyzer for impact analysis.

Parses Python source files to extract symbols, imports, and call relationships.
Uses the stdlib `ast` module — zero external dependencies.

Section 13.1 of the Evidence-First Harness specification.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
@dataclass
class ImportInfo:
    """A single import statement in a module."""

    module: str
    names: list[str]
    lineno: int


@dataclass
class SymbolInfo:
    """A named symbol (function, class, method) in a module."""

    name: str
    kind: str  # "function", "class", "method", "variable", "async_function"
    file_path: str
    lineno: int
    parent_class: str | None = None
    docstring: str | None = None


@dataclass
class CallInfo:
    """A function/method call site."""

    caller_name: str
    called_name: str
    lineno: int
    resolved: bool = False  # True if we could statically resolve the target


@dataclass
class ModuleInfo:
    """Complete AST-derived information about a single Python module."""

    path: str
    imports: list[ImportInfo] = field(default_factory=list)
    symbols: list[SymbolInfo] = field(default_factory=list)
    calls: list[CallInfo] = field(default_factory=list)
    references: list[str] = field(default_factory=list)  # names referenced from imports


def parse_module(file_path: Path) -> ModuleInfo:
    """Parse a single Python source file and extract symbols, imports, and calls.

    Args:
        file_path: Path to a .py file to parse.

    Returns:
        ModuleInfo with all extracted symbols, imports, and calls.
    """
    try:
        source = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ModuleInfo(path=str(file_path))

    try:
        tree = ast.parse(source, filename=str(file_path))
    except SyntaxError:
        return ModuleInfo(path=str(file_path))

    module_path = str(file_path)
    imports: list[ImportInfo] = []
    symbols: list[SymbolInfo] = []
    calls: list[CallInfo] = []
    references: list[str] = []

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            info = _extract_import(node)
            imports.append(info)
            references.extend(info.names)
        elif isinstance(node, ast.FunctionDef):
            sym = _extract_function(node, module_path)
            symbols.append(sym)
            # Extract calls within this function
            calls.extend(_extract_calls(node, sym.name))
        elif isinstance(node, ast.AsyncFunctionDef):
            sym = _extract_async_function(node, module_path)
            symbols.append(sym)
            calls.extend(_extract_calls(node, sym.name))
        elif isinstance(node, ast.ClassDef):
            sym = _extract_class(node, module_path)
            symbols.append(sym)
            # Extract methods and inner calls
            for body_node in node.body:
                if isinstance(body_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    method = _extract_method(body_node, module_path, node.name)
                    symbols.append(method)
                    calls.extend(_extract_calls(body_node, method.name))
        elif isinstance(node, ast.Assign):
            # Top-level variable assignments
            for target in node.targets:
                if isinstance(target, ast.Name):
                    symbols.append(
                        SymbolInfo(
                            name=target.id,
                            kind="variable",
                            file_path=module_path,
                            lineno=node.lineno,
                        )
                    )

    return ModuleInfo(
        path=module_path,
        imports=imports,
        symbols=symbols,
        calls=calls,
        references=references,
    )


def parse_directory(root: Path) -> dict[str, ModuleInfo]:
    """Recursively parse all Python files in a directory.

    Args:
        root: Root directory to scan.

    Returns:
        Dict mapping file path to ModuleInfo.
    """
    modules: dict[str, ModuleInfo] = {}
    for py_file in root.rglob("*.py"):
        if py_file.is_symlink():
            continue
        info = parse_module(py_file)
        if info.symbols or info.imports:  # Skip empty/unparseable files
            modules[str(py_file)] = info
    return modules


def extract_changed_symbols(
    before: dict[str, ModuleInfo],
    after: dict[str, ModuleInfo],
) -> list[str]:
    """Compare before/after module snapshots to identify changed symbols.

    Args:
        before: Modules snapshot from base commit.
        after: Modules snapshot from patch commit.

    Returns:
        List of fully-qualified symbol names that changed.
    """
    changed: list[str] = []

    # Find added or modified files
    all_paths = set(before.keys()) | set(after.keys())

    for path in all_paths:
        before_mod = before.get(path)
        after_mod = after.get(path)

        if before_mod is None:
            # New file — all symbols are changed
            if after_mod is not None:
                changed.extend(_qualify_symbols(after_mod.symbols, path))
        elif after_mod is None:
            # Deleted file — all symbols removed
            changed.extend(_qualify_symbols(before_mod.symbols, path))
        else:
            # Compare symbols
            before_names = {s.name for s in before_mod.symbols}
            after_names = {s.name for s in after_mod.symbols}
            diff = before_names.symmetric_difference(after_names)
            for name in diff:
                changed.append(f"{path}::{name}")

    return changed


def extract_symbols_from_module(info: ModuleInfo) -> list[str]:
    """Get qualified symbol names from a module.

    Args:
        info: ModuleInfo from parse_module.

    Returns:
        List of fully-qualified symbol names.
    """
    return _qualify_symbols(info.symbols, info.path)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _extract_import(node: ast.Import | ast.ImportFrom) -> ImportInfo:
    if isinstance(node, ast.Import):
        names = [alias.name for alias in node.names]
        return ImportInfo(module=names[0] if names else "", names=names, lineno=node.lineno)
    else:
        module = node.module or ""
        names = [alias.name for alias in node.names]
        return ImportInfo(module=module, names=names, lineno=node.lineno)


def _extract_function(node: ast.FunctionDef, module_path: str) -> SymbolInfo:
    return SymbolInfo(
        name=node.name,
        kind="function",
        file_path=module_path,
        lineno=node.lineno,
        docstring=ast.get_docstring(node),
    )


def _extract_async_function(node: ast.AsyncFunctionDef, module_path: str) -> SymbolInfo:
    return SymbolInfo(
        name=node.name,
        kind="async_function",
        file_path=module_path,
        lineno=node.lineno,
        docstring=ast.get_docstring(node),
    )


def _extract_class(node: ast.ClassDef, module_path: str) -> SymbolInfo:
    return SymbolInfo(
        name=node.name,
        kind="class",
        file_path=module_path,
        lineno=node.lineno,
        docstring=ast.get_docstring(node),
    )


def _extract_method(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    module_path: str,
    parent_class: str,
) -> SymbolInfo:
    kind = "async_function" if isinstance(node, ast.AsyncFunctionDef) else "method"
    return SymbolInfo(
        name=node.name,
        kind=kind,
        file_path=module_path,
        lineno=node.lineno,
        parent_class=parent_class,
        docstring=ast.get_docstring(node),
    )


def _extract_calls(node: ast.FunctionDef | ast.AsyncFunctionDef, caller_name: str) -> list[CallInfo]:
    calls: list[CallInfo] = []
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            called = _resolve_call_target(child)
            if called:
                calls.append(
                    CallInfo(
                        caller_name=caller_name,
                        called_name=called,
                        lineno=child.lineno,
                        resolved=False,
                    )
                )
    return calls


def _resolve_call_target(call: ast.Call) -> str | None:
    """Attempt to statically resolve the target of a call expression."""
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        parts: list[str] = []
        current: ast.expr = func
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            parts.append(current.id)
        return ".".join(reversed(parts))
    return None


def _qualify_symbols(symbols: list[SymbolInfo], module_path: str) -> list[str]:
    """Qualify symbol names with their module path."""
    return [f"{module_path}::{s.name}" for s in symbols]
