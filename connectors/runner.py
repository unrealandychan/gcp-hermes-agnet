"""
connectors/runner.py

Shared helper used by all platform connectors (Telegram, Slack, Teams).

Unlike the Web Chat SSE endpoint, platform bots need a single complete reply
text — not a stream. run_agent() collects all final-response parts and returns
the joined text.

Session ID scheme: <platform>_<platform_user_id>
  e.g.  telegram_123456789
        slack_U04AB12XY
        teams_29:1XYZ...

This ensures each user has a single persistent session per platform, giving
them continuity across conversations (long-term memory via VertexAiMemoryBankService
and PreloadMemoryTool).
"""
from __future__ import annotations

import logging

from google.genai.types import Content, Part

logger = logging.getLogger(__name__)


def _platform_session_id(platform: str, platform_user_id: str) -> str:
    # Sanitise so it's safe as a session ID key
    safe_uid = platform_user_id.replace(":", "_").replace(" ", "_")[:64]
    return f"{platform}_{safe_uid}"


async def run_agent(
    platform: str,
    platform_user_id: str,
    message: str,
) -> str:
    """
    Run the Hermes agent for a connector message and return the full text reply.

    Args:
        platform: Short platform tag used for session namespacing, e.g. "telegram".
        platform_user_id: Stable user identifier from the platform.
        message: The user's text message.

    Returns:
        The agent's full plain-text response.
    """
    # Import here to avoid circular imports at module load time
    from gateway.main import _runner  # noqa: PLC0415

    if _runner is None:
        return "⚠️ Hermes is not ready yet. Please try again in a moment."

    user_id = _platform_session_id(platform, platform_user_id)
    session_id = user_id  # one persistent session per platform user

    # Ensure the session exists (idempotent — does nothing if already present)
    try:
        await _runner.session_service.create_session(
            app_name=_runner.app_name,
            user_id=user_id,
            session_id=session_id,
        )
    except Exception:  # noqa: BLE001
        pass  # session already exists or service returned a benign error

    user_content = Content(role="user", parts=[Part(text=message)])
    response_parts: list[str] = []

    try:
        async for event in _runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=user_content,
        ):
            if event.is_final_response() and event.content:
                for part in event.content.parts:
                    text = getattr(part, "text", None)
                    if text:
                        response_parts.append(text)
    except Exception:  # noqa: BLE001
        logger.exception("Agent error for %s user %s", platform, platform_user_id)
        return "⚠️ Something went wrong. Please try again."

    return "".join(response_parts) or "I don't have a response for that."
