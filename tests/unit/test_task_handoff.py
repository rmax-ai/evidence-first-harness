"""Tests for preserving explicit task context across the agent workflow."""

from __future__ import annotations

import subprocess
from pathlib import Path

import click
import pytest

from evidence_first_harness.agents.invoker import AgentCallResult
from evidence_first_harness.artifacts.store import ArtifactStore
from evidence_first_harness.callbacks.provenance import ProvenanceRecorder
from evidence_first_harness.cli import _resolve_task_description
from evidence_first_harness.workflows.graph import NodeStatus
from evidence_first_harness.workflows.nodes import (
    _build_repository_context,
    handle_compile_specification,
    handle_plan_implementation,
)
from evidence_first_harness.workflows.session import SessionManager
from evidence_first_harness.workflows.state import WorkflowState


def _state() -> WorkflowState:
    return WorkflowState(
        run_id="run_taskhandoff",
        task_description="Add a regression test for task handoff.",
    )


def test_task_option_is_required() -> None:
    """The CLI refuses to spend agent calls on an invented default task."""
    with pytest.raises(click.UsageError, match="--task or --spec"):
        _resolve_task_description(None, None)


def test_yaml_specification_is_loaded(tmp_path: Path) -> None:
    """A non-empty YAML specification becomes the explicit task input."""
    specification = tmp_path / "task.yaml"
    specification.write_text("title: Add a regression test\n")

    task = _resolve_task_description(None, str(specification))

    assert task == "Task specification (YAML):\ntitle: Add a regression test"


def test_repository_context_includes_complete_task_matched_file(tmp_path: Path) -> None:
    """Task-matched files are not cut off at the old four-kilobyte limit."""
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    source = tmp_path / "tests" / "test_policy_engine.py"
    source.parent.mkdir()
    source.write_text("policy context\n" + "x" * 7_000)
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)

    context, selected_files = _build_repository_context(
        tmp_path, "Add a focused test for the policy engine."
    )

    assert selected_files == ["tests/test_policy_engine.py"]
    assert source.read_text() in context


@pytest.mark.asyncio
async def test_session_dispatch_passes_stored_task_to_specification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The dispatch layer preserves the task that SessionManager accepted."""
    state = _state()
    manager = object.__new__(SessionManager)
    manager._state = state
    manager._worktree_path = None
    manager._artifacts = object()
    manager._provenance = object()

    received: dict[str, object] = {}

    async def fake_handler(*args: object) -> NodeStatus:
        received["task"] = args[1]
        return NodeStatus.SUCCESS

    monkeypatch.setattr(
        "evidence_first_harness.workflows.session.handle_compile_specification",
        fake_handler,
    )

    status = await manager._dispatch("compile_specification")

    assert status is NodeStatus.SUCCESS
    assert received["task"] == state.task_description


@pytest.mark.asyncio
async def test_agents_receive_task_specification_and_repository_context(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Prompts share the same immutable task and repository context artifacts."""
    requests: list[dict[str, object]] = []

    async def fake_call_agent(**kwargs: object) -> AgentCallResult:
        requests.append(kwargs)
        return AgentCallResult(
            text="compiled response",
            model="test-model",
            provider="test",
        )

    monkeypatch.setattr("evidence_first_harness.agents.invoker.call_agent", fake_call_agent)
    artifacts = ArtifactStore(tmp_path / "artifacts")
    state = _state()
    state.repository_context_artifact = artifacts.store(
        "repository_context", "Tracked files:\nsrc/example.py\n"
    ).artifact_id
    provenance = ProvenanceRecorder(state.run_id, tmp_path / "provenance")

    specification_status = await handle_compile_specification(
        state, state.task_description, artifacts, provenance
    )
    planner_status = await handle_plan_implementation(state, artifacts, provenance)

    assert specification_status is NodeStatus.SUCCESS
    assert planner_status is NodeStatus.SUCCESS
    assert all(state.task_description in str(request["user_prompt"]) for request in requests)
    assert all("src/example.py" in str(request["user_prompt"]) for request in requests)
    assert "compiled response" in str(requests[1]["user_prompt"])
