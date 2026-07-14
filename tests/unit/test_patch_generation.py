"""Tests for the fail-closed implementation patch boundary."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from evidence_first_harness.agents.invoker import AgentCallResult, _call_litellm
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


def test_openai_gpt5_uses_provider_default_temperature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GPT-5 requests omit temperature when the provider rejects overrides."""
    import litellm

    captured: dict[str, object] = {}

    def fake_completion(**kwargs: object) -> SimpleNamespace:
        captured.update(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="{}"))],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
        )

    monkeypatch.setattr(litellm, "completion", fake_completion)

    _call_litellm(
        model="openai/gpt-5.6-terra",
        system_prompt="system",
        user_prompt="user",
        api_key="test-key",
        provider="openai",
        temperature=0.0,
        max_tokens=100,
    )

    assert "temperature" not in captured


def test_sonnet5_uses_adaptive_thinking_without_effort(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sonnet 5 rejects the optional adaptive-thinking effort parameter."""
    import litellm

    captured: dict[str, object] = {}

    def fake_completion(**kwargs: object) -> SimpleNamespace:
        captured.update(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="{}"))],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
        )

    monkeypatch.setattr(litellm, "completion", fake_completion)

    _call_litellm(
        model="anthropic/claude-sonnet-5",
        system_prompt="system",
        user_prompt="user",
        api_key="test-key",
        provider="anthropic",
        temperature=0.0,
        max_tokens=100,
        effort="medium",
    )

    assert captured["thinking"] == {"type": "adaptive"}


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
    responses = list((tmp_path / "artifacts" / "objects").glob("*"))
    assert any(response.read_text() == "" for response in responses)


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
    assert any(
        response.read_text() == "I changed the requested code successfully."
        for response in (tmp_path / "artifacts" / "objects").glob("*")
    )


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
    requests: list[dict[str, object]] = []

    async def fake_call_agent(**kwargs: object) -> AgentCallResult:
        requests.append(kwargs)
        return AgentCallResult(
            text=json.dumps(
                {
                    "patch": patch,
                    "summary": "Add an example module.",
                    "deviations": [],
                }
            ),
            model="gpt-5.6-terra",
            provider="openai",
        )

    monkeypatch.setattr("evidence_first_harness.agents.invoker.call_agent", fake_call_agent)
    artifacts = ArtifactStore(tmp_path / "artifacts")
    state = _state()
    state.specification_artifact = artifacts.store(
        "specification", "The specification."
    ).artifact_id
    state.implementation_plan_artifact = artifacts.store(
        "implementation_plan", "The implementation plan."
    ).artifact_id
    provenance = ProvenanceRecorder(state.run_id, tmp_path / "provenance")

    status = await handle_generate_patch(state, tmp_path, artifacts, provenance)

    assert status is NodeStatus.SUCCESS
    assert (tmp_path / "example.py").read_text() == "value = 1\n"
    assert artifacts.retrieve(state.patch_artifact).decode() == patch
    assert "The specification." in str(requests[0]["user_prompt"])
    assert "The implementation plan." in str(requests[0]["user_prompt"])
    assert requests[0]["model"] == "gpt-5.6-terra"
    assert requests[0]["provider"] == "openai"
    response_format = requests[0]["response_format"]
    assert isinstance(response_format, dict)
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["strict"] is True


@pytest.mark.asyncio
async def test_applicable_patch_with_incorrect_hunk_count_is_recounted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Git recount accepts a patch whose content is valid but count is stale."""
    _initialize_repository(tmp_path)
    patch = """diff --git a/example.py b/example.py
new file mode 100644
index 0000000..a4a226f
--- /dev/null
+++ b/example.py
@@ -0,0 +1,3 @@
+value = 1
"""

    async def fake_call_agent(**_: object) -> AgentCallResult:
        return AgentCallResult(
            text=json.dumps({"patch": patch, "summary": "Add module.", "deviations": []}),
            model="gpt-5.6-terra",
            provider="openai",
        )

    monkeypatch.setattr("evidence_first_harness.agents.invoker.call_agent", fake_call_agent)
    artifacts = ArtifactStore(tmp_path / "artifacts")
    state = _state()
    provenance = ProvenanceRecorder(state.run_id, tmp_path / "provenance")

    status = await handle_generate_patch(state, tmp_path, artifacts, provenance)

    assert status is NodeStatus.SUCCESS
    assert (tmp_path / "example.py").read_text() == "value = 1\n"


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
