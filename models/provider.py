"""
models/provider.py

LLM provider factory for Hermes agents.

Supported provider/model formats
─────────────────────────────────
Native Gemini (Vertex AI — no prefix needed):
  "gemini-2.0-flash"
  "gemini-2.5-flash"
  "gemini-2.5-flash-lite"
  "gemini-2.5-pro"

OpenAI (via LiteLLM):
  "openai/gpt-4o"
  "openai/gpt-4o-mini"
  "openai/gpt-4-turbo"

Anthropic / Claude (via LiteLLM):
  "anthropic/claude-sonnet-4-5"
  "anthropic/claude-3-5-haiku-20241022"
  "anthropic/claude-opus-4"

Azure OpenAI (via LiteLLM):
  "azure/my-gpt4o-deployment"

AWS Bedrock (via LiteLLM):
  "bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0"

Ollama / local models (via LiteLLM):
  "ollama/llama3"
  "ollama/mistral"

Any other LiteLLM-supported provider:
  "<provider>/<model>"

Resolution logic
────────────────
• Strings that do NOT contain "/" and do NOT start with a known
  non-Gemini prefix are treated as native Gemini model IDs.
• Strings that contain "/" are wrapped in LiteLlm().
• Environment variables for the relevant provider are automatically
  picked up by LiteLLM at runtime (e.g. OPENAI_API_KEY, ANTHROPIC_API_KEY).
"""
from __future__ import annotations

import logging
from typing import Union

logger = logging.getLogger(__name__)

# Prefixes that indicate a non-Gemini model even if they lack "/"
_NON_GEMINI_PREFIXES = (
    "gpt-",
    "text-davinci",
    "claude-",
    "llama",
    "mistral",
    "command",
)

# Type alias for ADK model parameter: either a plain string or LiteLlm instance
ModelType = Union[str, object]


def resolve_model_str(model_str: str) -> str:
    """
    Normalise the raw model string.

    Returns the model string unchanged (LiteLlm wrapping happens in get_model).
    """
    return model_str.strip()


def get_model(model_str: str) -> ModelType:
    """
    Return the correct ADK model value for the given model string.

    - Native Gemini IDs are returned as plain strings.
    - Everything else is wrapped in google.adk.models.LiteLlm so that
      OpenAI, Anthropic, Bedrock, Ollama, etc. all work transparently.

    Args:
        model_str: Model identifier in "<provider>/<model>" format for
                   non-Gemini models, or bare Gemini model name.

    Returns:
        str | LiteLlm: Value suitable for LlmAgent(model=...).
    """
    model_str = model_str.strip()

    # Detect native Gemini
    if _is_native_gemini(model_str):
        logger.debug("Using native Gemini model: %s", model_str)
        return model_str

    # Non-Gemini — wrap with LiteLLM
    try:
        from google.adk.models.lite_llm import LiteLlm  # lazy import

        logger.debug("Using LiteLLM wrapper for model: %s", model_str)
        return LiteLlm(model=model_str)
    except ImportError as exc:
        raise ImportError(
            f"google-adk LiteLLM integration not available. "
            f"Install 'google-adk[litellm]>=0.5.0' to use non-Gemini models. "
            f"Original error: {exc}"
        ) from exc


def _is_native_gemini(model_str: str) -> bool:
    """Return True if model_str refers to a native Gemini/Vertex AI model."""
    if "/" not in model_str:
        # No provider prefix — check for known non-Gemini bare names
        lower = model_str.lower()
        if any(lower.startswith(p) for p in _NON_GEMINI_PREFIXES):
            return False
        return True  # assumed Gemini
    # Has a prefix — Gemini models can be "google/gemini-*"
    prefix, _ = model_str.split("/", 1)
    return prefix.lower() in ("google", "vertex_ai", "vertex_ai_preview")
