"""Coverage map parser for impact analysis.

Parses coverage.py JSON output to map source files → covered lines.
Used by the test selector to identify which tests cover which symbols.

Section 13.1 of the Evidence-First Harness specification.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class CoverageLine:
    """A single coverage line in a source file."""

    lineno: int
    covered: bool
    branches: int = 0


@dataclass
class FileCoverage:
    """Coverage data for a single source file."""

    file_path: str
    covered_lines: list[int] = field(default_factory=list)
    uncovered_lines: list[int] = field(default_factory=list)
    total_lines: int = 0
    coverage_pct: float = 0.0


@dataclass
class CoverageMap:
    """Complete coverage map for a repository snapshot."""

    files: dict[str, FileCoverage] = field(default_factory=dict)
    overall_coverage_pct: float = 0.0
    available: bool = False

    @classmethod
    def from_json(cls, json_path: Path) -> CoverageMap:
        """Parse a coverage.py JSON report.

        Args:
            json_path: Path to coverage.json (produced by `coverage json`).

        Returns:
            CoverageMap with per-file coverage data.
        """
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            return cls(available=False)

        files: dict[str, FileCoverage] = {}
        total_lines = 0
        total_covered = 0

        raw_files = data.get("files", {})
        for file_path, file_data in raw_files.items():
            executed_lines = file_data.get("executed_lines", [])
            missing_lines = file_data.get("missing_lines", [])
            summary = file_data.get("summary", {})

            num_statements = summary.get("num_statements", 0)
            covered = summary.get("covered_lines", 0)
            total_lines += num_statements
            total_covered += covered

            pct = (covered / num_statements * 100) if num_statements > 0 else 0.0

            files[file_path] = FileCoverage(
                file_path=file_path,
                covered_lines=sorted(executed_lines),
                uncovered_lines=sorted(missing_lines),
                total_lines=num_statements,
                coverage_pct=round(pct, 1),
            )

        overall = (total_covered / total_lines * 100) if total_lines > 0 else 0.0

        return cls(
            files=files,
            overall_coverage_pct=round(overall, 1),
            available=True,
        )

    @classmethod
    def empty(cls) -> CoverageMap:
        """Return an empty coverage map for when no data is available."""
        return cls(available=False)

    def get_coverage(self, file_path: str) -> FileCoverage | None:
        """Get coverage data for a specific file.

        Args:
            file_path: Path to the source file.

        Returns:
            FileCoverage if available, None otherwise.
        """
        # Normalize path — coverage.py may use relative or absolute paths
        for key, fc in self.files.items():
            if key.endswith(file_path) or file_path.endswith(key):
                return fc
        return self.files.get(file_path)

    def symbols_covered(self, file_path: str, symbol_lines: dict[str, int]) -> dict[str, bool]:
        """Check which symbols are covered by tests.

        Args:
            file_path: Path to the source file.
            symbol_lines: Dict mapping symbol name → line number.

        Returns:
            Dict mapping symbol name → covered (True/False).
        """
        fc = self.get_coverage(file_path)
        if fc is None:
            return dict.fromkeys(symbol_lines, False)

        return {name: lineno in fc.covered_lines for name, lineno in symbol_lines.items()}
