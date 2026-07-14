"""Agent invocation helper — calls LLMs via native SDKs and LiteLLM.

Google Gemini: uses google-genai SDK (already installed via google-adk)
DeepSeek, OpenAI, Anthropic: uses LiteLLM

Returns AgentCallResult with text, model, token counts, timing.
"""

from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass
from typing import Any

import structlog

logger = structlog.get_logger()

# Provider → pass store key path mapping
PROVIDER_KEY_MAP = {
    "google": "hermes/gemini/api-key",
    "gemini": "hermes/gemini/api-key",
    "deepseek": "hermes/deepseek/api-key",
    "openai": "hermes/openai/api-key",
    "anthropic": "hermes/anthropic/api-key",
}


@dataclass
class AgentCallResult:
    """Result of an LLM agent call."""

    text: str
    model: str
    provider: str
    input_tokens: int = 0
    output_tokens: int = 0
    duration_ms: float = 0.0
    error: str | None = None


def resolve_api_key(provider: str) -> str | None:
    """Resolve an API key from the pass store or environment."""
    store_path = os.path.expanduser("~/.hermes/.password-store")

    pass_key_name = PROVIDER_KEY_MAP.get(provider)
    if pass_key_name:
        gpg_path = os.path.join(store_path, f"{pass_key_name}.gpg")
        if os.path.exists(gpg_path):
            try:
                result = subprocess.run(
                    ["gpg", "-d", "-q", gpg_path],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if result.returncode == 0:
                    return result.stdout.strip()
            except Exception as e:
                logger.warning("key_resolution_failed", provider=provider, error=str(e))

    # Fallback env vars
    env_map = {
        "google": "GEMINI_API_KEY", "gemini": "GEMINI_API_KEY",
        "deepseek": "DEEPSEEK_API_KEY",
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
    }
    env_var = env_map.get(provider)
    if env_var:
        return os.environ.get(env_var)

    return None


async def call_agent(
    model: str,
    system_prompt: str,
    user_prompt: str,
    provider: str = "",
    temperature: float = 0.2,
    max_tokens: int = 4096,
    effort: str | None = None,
    response_format: dict[str, Any] | None = None,
) -> AgentCallResult:
    """Call an LLM and return the response.

    Uses native Google Gen AI SDK for Gemini models, LiteLLM for everything else.
    """
    import asyncio

    start = time.monotonic()

    if not provider:
        provider = model  # For Google, model IS the provider hint

    api_key = resolve_api_key(provider)
    if not api_key:
        duration_ms = (time.monotonic() - start) * 1000
        return AgentCallResult(
            text="", model=model, provider=provider,
            duration_ms=duration_ms,
            error=f"No API key found for provider '{provider}'",
        )

    try:
        if provider in ("google", "gemini"):
            result = await _call_gemini(
                model=model, system_prompt=system_prompt,
                user_prompt=user_prompt, api_key=api_key,
                temperature=temperature, max_tokens=max_tokens,
            )
        else:
            result = await asyncio.to_thread(
                _call_litellm,
                model=_litellm_model_name(model, provider),
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                api_key=api_key,
                provider=provider,
                temperature=temperature,
                max_tokens=max_tokens,
                effort=effort,
                response_format=response_format,
            )
    except Exception as e:
        duration_ms = (time.monotonic() - start) * 1000
        return AgentCallResult(
            text="", model=model, provider=provider,
            duration_ms=duration_ms, error=str(e),
        )

    duration_ms = (time.monotonic() - start) * 1000

    return AgentCallResult(
        text=result.get("content", ""),
        model=model,
        provider=provider,
        input_tokens=result.get("input_tokens", 0),
        output_tokens=result.get("output_tokens", 0),
        duration_ms=duration_ms,
    )


# ---------------------------------------------------------------------------
# Google Gemini — native SDK
# ---------------------------------------------------------------------------


async def _call_gemini(
    model: str,
    system_prompt: str,
    user_prompt: str,
    api_key: str,
    temperature: float,
    max_tokens: int,
) -> dict[str, Any]:
    """Call Gemini via google-genai SDK."""
    import asyncio

    return await asyncio.to_thread(
        _call_gemini_sync,
        model=model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        api_key=api_key,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def _call_gemini_sync(
    model: str,
    system_prompt: str,
    user_prompt: str,
    api_key: str,
    temperature: float,
    max_tokens: int,
) -> dict[str, Any]:
    """Synchronous Gemini call via google-genai."""
    from google import genai

    client = genai.Client(api_key=api_key)

    # Combine system + user into a single prompt if needed
    config = genai.types.GenerateContentConfig(
        temperature=temperature,
        max_output_tokens=max_tokens,
        system_instruction=system_prompt,
    )

    response = client.models.generate_content(
        model=model,
        contents=user_prompt,
        config=config,
    )

    content = ""
    input_tokens = 0
    output_tokens = 0

    if response.candidates and response.candidates[0].content:
        content = "".join(
            part.text for part in response.candidates[0].content.parts
            if hasattr(part, "text") and part.text
        )

    if response.usage_metadata:
        input_tokens = response.usage_metadata.prompt_token_count or 0
        output_tokens = response.usage_metadata.candidates_token_count or 0

    return {
        "content": content,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }


# ---------------------------------------------------------------------------
# LiteLLM — DeepSeek, OpenAI, Anthropic
# ---------------------------------------------------------------------------


def _litellm_model_name(model: str, provider: str) -> str:
    """Convert short model name to LiteLLM format."""
    # If already has provider prefix, use as-is
    if "/" in model:
        return model
    # Map short names to litellm format
    prefix_map = {
        "deepseek": "deepseek",
        "openai": "openai",
        "anthropic": "anthropic",
    }
    prefix = prefix_map.get(provider, provider)
    return f"{prefix}/{model}"


def _call_litellm(
    model: str,
    system_prompt: str,
    user_prompt: str,
    api_key: str,
    provider: str,
    temperature: float,
    max_tokens: int,
    effort: str | None = None,
    response_format: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Synchronous LiteLLM call."""
    import litellm

    # Set the correct env var per provider
    env_vars = {
        "deepseek": "DEEPSEEK_API_KEY",
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
    }
    for p, var in env_vars.items():
        if p == provider or provider == p:
            os.environ[var] = api_key

    litellm.api_key = api_key

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    try:
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "timeout": 120,
        }
        # Anthropic adaptive-thinking and OpenAI GPT-5-family models use their
        # provider defaults rather than accepting an explicit temperature.
        base_model = model.split("/")[-1]
        uses_provider_default_temperature = provider == "anthropic" or (
            provider == "openai" and base_model.startswith("gpt-5")
        )
        if not uses_provider_default_temperature:
            kwargs["temperature"] = temperature

        if response_format is not None:
            kwargs["response_format"] = response_format

        # Anthropic adaptive thinking
        # Models that support effort in adaptive thinking:
        #   claude-fable-5, claude-mythos-5, claude-opus-4-8, claude-opus-4-7
        # Models that only support type:adaptive (no effort):
        #   claude-opus-4-6, claude-sonnet-4-6, claude-sonnet-5
        if effort and provider == "anthropic":
            effort_models = {
                "claude-fable-5", "claude-mythos-5",
                "claude-opus-4-8", "claude-opus-4-7",
            }
            base = model.split("/")[-1]  # strip litellm prefix like "anthropic/"
            if base in effort_models:
                kwargs["thinking"] = {"type": "adaptive", "effort": effort}
            else:
                kwargs["thinking"] = {"type": "adaptive"}

        response = litellm.completion(**kwargs)
    except Exception as e:
        logger.error("litellm_call_error", model=model, error=str(e)[:200])
        raise

    content = ""
    if response.choices:
        content = response.choices[0].message.content or ""

    usage = getattr(response, "usage", None)
    input_tokens = getattr(usage, "prompt_tokens", 0) if usage else 0
    output_tokens = getattr(usage, "completion_tokens", 0) if usage else 0

    return {
        "content": content,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }
