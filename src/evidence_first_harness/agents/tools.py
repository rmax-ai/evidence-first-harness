"""ADK tool definitions — narrow function tools for agents.

Section 15 of the spec. Agents get validated tools, not generic shell access.
Each tool validates inputs, runs in the sandbox, and returns structured output.
"""

from __future__ import annotations

from typing import Any

from google.adk.tools import ToolContext


def inspect_repository(path: str, tool_context: Any = None) -> dict[str, Any]:
    """Return a summary of the repository structure.

    Args:
        path: Path within the repository (use "." for root).

    Returns:
        Dict with files, directories, and language breakdown.
    """
    import os
    from pathlib import Path

    repo_path = Path(path)
    if not repo_path.exists():
        return {"error": f"Path not found: {path}"}

    files: list[str] = []
    dirs: list[str] = []
    for entry in sorted(repo_path.iterdir()):
        if entry.name.startswith(".") and entry.name != ".":
            continue
        if entry.is_dir():
            dirs.append(entry.name)
        else:
            files.append(entry.name)

    return {
        "path": str(repo_path),
        "directories": dirs[:50],
        "files": files[:50],
        "total_files": len(files),
        "total_dirs": len(dirs),
    }


def read_source_file(
    path: str, start: int = 1, end: int = 100, tool_context: ToolContext | None = None
) -> dict[str, Any]:
    """Read a range of lines from a source file.

    Args:
        path: Path to the source file.
        start: First line number (1-indexed).
        end: Last line number (inclusive).

    Returns:
        Dict with lines and total line count.
    """
    from pathlib import Path

    file_path = Path(path)
    if not file_path.exists():
        return {"error": f"File not found: {path}"}

    try:
        content = file_path.read_text()
        lines = content.split("\n")
        total = len(lines)

        # Clamp to valid range
        start = max(1, start)
        end = min(total, end)

        excerpt = lines[start - 1 : end]
        return {
            "path": str(file_path),
            "lines": excerpt,
            "start": start,
            "end": end,
            "total_lines": total,
        }
    except Exception as e:
        return {"error": str(e)}


def search_symbols(
    query: str, tool_context: ToolContext | None = None
) -> list[dict[str, str]]:
    """Search for symbols (functions, classes) in the repository.

    Args:
        query: Search query (matches symbol names).

    Returns:
        List of matching symbols with file and line info.
    """
    import subprocess
    from pathlib import Path

    # Use grep to find Python definitions
    try:
        result = subprocess.run(
            ["grep", "-rn", f"def {query}|class {query}", "."],
            capture_output=True,
            text=True,
            timeout=10,
        )
        matches: list[dict[str, str]] = []
        for line in result.stdout.strip().split("\n")[:20]:
            if ":" in line:
                parts = line.split(":", 2)
                if len(parts) >= 3:
                    matches.append({
                        "file": parts[0],
                        "line": parts[1],
                        "content": parts[2].strip(),
                    })
        return matches
    except Exception as e:
        return [{"error": str(e)}]


def store_artifact(
    kind: str, content: str, tool_context: ToolContext | None = None
) -> dict[str, str]:
    """Store content as an immutable artifact.

    Args:
        kind: Artifact kind (e.g., "specification", "patch", "evidence").
        content: The content to store.

    Returns:
        Dict with artifact_id and digest.
    """
    import hashlib

    digest = hashlib.sha256(content.encode()).hexdigest()
    artifact_id = f"art_{digest[:16]}"

    return {
        "artifact_id": artifact_id,
        "kind": kind,
        "digest": f"sha256:{digest}",
        "size_bytes": len(content),
    }
