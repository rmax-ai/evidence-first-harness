"""Tests for the fail-closed implementation patch boundary."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from evidence_first_harness.agents.invoker import AgentCallResult
from evidence_first_harness.artifacts.store import ArtifactStore
from evidence_first_harness.callbacks.provenance import ProvenanceRecorder
from evidence_first_harness.workflows.graph import NodeStatus
from evidence_first_harness.workflows.nodes import (
    handle_analyze_impact,
    handle_generate_patch,
)
from evidence_first_harness.workflows.state import WorkflowState


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def _initialize_repository(path: Path) -> None:
    _git(["init"], path)
    _git(["config", "user.email", "efh-test@example.com"], path)
    _git(["config", "user.name", "EFH Test"], path)
    (path / "README.md").write_text("test repository\n")
    _git(["add", "README.md"], path)
    _git(["commit", "-m", "initial"], path)


def _state() -> WorkflowState:
    return WorkflowState(run_id="run_patchboundary")


@pytest.mark.asyncio
async def test_agent_error_is_not_stored_as_patch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Provider errors stop before a patch artifact is created."""
    _initialize_repository(tmp_path)

    async def fake_call_agent(**_: object) -> AgentCallResult:
        return AgentCallResult(
            text="",
            model="deepseek-chat",
            provider="deepseek",
            error="No API key found for provider 'deepseek'",
        )

    monkeypatch.setattr("evidence_first_harness.agents.invoker.call_agent", fake_call_agent)
    artifacts = ArtifactStore(tmp_path / "artifacts")
    state = _state()
    provenance = ProvenanceRecorder(state.run_id, tmp_path / "provenance")

    status = await handle_generate_patch(state, tmp_path, artifacts, provenance)

    assert status is NodeStatus.IMPLEMENTATION_FAILURE
    assert state.patch_artifact == ""
    assert state.final_decision == "implementation_failure"
    assert any("No API key" in error for error in state.errors)


@pytest.mark.asyncio
async def test_invalid_agent_output_is_rejected_before_impact_analysis(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Prose output cannot enter the patch or impact-analysis stages."""
    _initialize_repository(tmp_path)

    async def fake_call_agent(**_: object) -> AgentCallResult:
        return AgentCallResult(
            text="I changed the requested code successfully.",
            model="deepseek-chat",
            provider="deepseek",
        )

    monkeypatch.setattr("evidence_first_harness.agents.invoker.call_agent", fake_call_agent)
    artifacts = ArtifactStore(tmp_path / "artifacts")
    state = _state()
    provenance = ProvenanceRecorder(state.run_id, tmp_path / "provenance")

    status = await handle_generate_patch(state, tmp_path, artifacts, provenance)

    assert status is NodeStatus.IMPLEMENTATION_FAILURE
    assert state.patch_artifact == ""
    assert not (tmp_path / "example.py").exists()


@pytest.mark.asyncio
async def test_valid_patch_is_applied_and_stored(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A parseable, applicable unified diff is stored and applied."""
    _initialize_repository(tmp_path)
    patch = """diff --git a/example.py b/example.py
new file mode 100644
index 0000000..a4a226f
--- /dev/null
+++ b/example.py
@@ -0,0 +1 @@
+value = 1
"""

    async def fake_call_agent(**_: object) -> AgentCallResult:
        return AgentCallResult(text=patch, model="deepseek-chat", provider="deepseek")

    monkeypatch.setattr("evidence_first_harness.agents.invoker.call_agent", fake_call_agent)
    artifacts = ArtifactStore(tmp_path / "artifacts")
    state = _state()
    provenance = ProvenanceRecorder(state.run_id, tmp_path / "provenance")

    status = await handle_generate_patch(state, tmp_path, artifacts, provenance)

    assert status is NodeStatus.SUCCESS
    assert (tmp_path / "example.py").read_text() == "value = 1\n"
    assert artifacts.retrieve(state.patch_artifact).decode() == patch


@pytest.mark.asyncio
async def test_impact_analysis_refuses_missing_patch(
    tmp_path: Path,
) -> None:
    """Impact analysis cannot invent changed files when no patch exists."""
    _initialize_repository(tmp_path)
    artifacts = ArtifactStore(tmp_path / "artifacts")
    state = _state()
    provenance = ProvenanceRecorder(state.run_id, tmp_path / "provenance")

    status = await handle_analyze_impact(state, tmp_path, tmp_path, artifacts, provenance)

    assert status is NodeStatus.IMPLEMENTATION_FAILURE
    assert state.final_decision == "implementation_failure"
    assert "no valid patch artifact" in state.errors[-1]
