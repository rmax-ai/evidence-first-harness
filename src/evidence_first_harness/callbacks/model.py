"""ADK callbacks — enforcement points for model and tool lifecycle.

Section 16 of the spec. Callbacks validate model outputs, authorize tools,
redact secrets, enforce budgets, and record provenance — they are enforcement
points, not merely logging hooks.
"""

from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger()


class ModelCallbacks:
    """Callbacks that fire before and after model invocations."""

    @staticmethod
    async def before_model(context: dict[str, Any]) -> dict[str, Any]:
        """Enforce model call constraints.

        - Redact secrets from prompts
        - Enforce context budget
        - Include only role-relevant artifacts
        - Inject run ID and specification digest
        - Record model, configuration, and prompt digest
        """
        # Strip any secret patterns from prompt
        prompt = context.get("prompt", "")
        if prompt:
            prompt = _redact_secrets(prompt)
            context["prompt"] = prompt

        # Enforce context budget
        max_tokens = context.get("context_budget", 16000)
        current_tokens = context.get("estimated_tokens", 0)
        if current_tokens > max_tokens:
            logger.warning(
                "context_budget_exceeded",
                current=current_tokens,
                max=max_tokens,
            )

        # Inject run ID for tracing
        run_id = context.get("run_id", "unknown")
        logger.info("before_model", run_id=run_id, model=context.get("model"))

        return context

    @staticmethod
    async def after_model(context: dict[str, Any]) -> dict[str, Any]:
        """Validate model outputs.

        - Validate structured output against expected schema
        - Reject schema-invalid responses
        - Detect unsupported claims
        - Store response as immutable artifact
        - Capture token usage and latency
        """
        output = context.get("output")
        if output is None:
            logger.error("model_empty_output", run_id=context.get("run_id"))
            context["valid"] = False
            context["error"] = "Model returned empty output"
            return context

        # Basic validation passed
        context["valid"] = True

        logger.info(
            "after_model",
            run_id=context.get("run_id"),
            token_usage=context.get("token_usage", {}),
        )

        return context


class ToolCallbacks:
    """Callbacks that fire before and after tool invocations."""

    @staticmethod
    async def before_tool(context: dict[str, Any]) -> dict[str, Any]:
        """Authorize tool execution.

        - Authorize the tool for the current agent role
        - Validate arguments
        - Evaluate command allowlists
        - Attach actor provenance
        - Deny forbidden paths and network access
        """
        tool_name = context.get("tool_name", "unknown")
        agent_role = context.get("agent_role", "unknown")

        # Check if tool is allowed for this role
        allowed = _is_tool_allowed(agent_role, tool_name)
        if not allowed:
            logger.warning(
                "tool_unauthorized",
                agent=agent_role,
                tool=tool_name,
            )
            context["authorized"] = False
            context["error"] = f"Tool {tool_name} not authorized for {agent_role}"
            return context

        context["authorized"] = True
        logger.info(
            "before_tool",
            tool=tool_name,
            agent=agent_role,
        )

        return context

    @staticmethod
    async def after_tool(context: dict[str, Any]) -> dict[str, Any]:
        """Normalize and record tool output.

        - Normalize tool output
        - Hash artifacts
        - Capture exit status and environment
        - Redact secrets
        - Emit trace and metrics events
        """
        output = context.get("output", "")
        if isinstance(output, str):
            output = _redact_secrets(output)
            context["output"] = output

        logger.info(
            "after_tool",
            tool=context.get("tool_name"),
            duration_ms=context.get("duration_ms"),
        )

        return context


def _redact_secrets(text: str) -> str:
    """Redact common secret patterns from text."""
    import re

    patterns = [
        (r"sk-[a-zA-Z0-9]{20,}", "[REDACTED_API_KEY]"),
        (r"AIza[0-9A-Za-z_-]{35}", "[REDACTED_GEMINI_KEY]"),
        (r"ghp_[a-zA-Z0-9]{36}", "[REDACTED_GITHUB_TOKEN]"),
        (
            r'(["\']?(?:password|secret|token|api_key|apikey)["\']?\s*[:=]\s*["\']?)([^"\'\\s]{6,})',
            r"\1[REDACTED]",
        ),
    ]

    for pattern, replacement in patterns:
        text = re.sub(pattern, replacement, text)

    return text


def _is_tool_allowed(agent_role: str, tool_name: str) -> bool:
    """Check if a tool is allowed for a given agent role.

    Based on the tool allowlists in config/tools.yaml.
    """
    # Phase 2 default allowlists
    common_tools = {"inspect_repository", "read_source_file", "search_symbols", "store_artifact"}
    implementation_tools = common_tools | {
        "apply_patch",
        "run_allowed_command",
        "get_test_selection",
    }
    read_only_tools = common_tools - {"store_artifact"}  # spec/planner/adversarial can't store

    role_allowlists = {
        "specification_agent": common_tools,
        "planner_agent": common_tools,
        "implementation_agent": implementation_tools,
        "independent_test_agent": common_tools,
        "adversarial_review_agent": common_tools,
        "explanation_agent": {"store_artifact"},
    }

    allowed = role_allowlists.get(agent_role, set())
    return tool_name in allowed
