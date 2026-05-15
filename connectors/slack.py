"""
connectors/slack.py

Slack Events API connector for Hermes.

Setup:
  1. Create a Slack App at https://api.slack.com/apps
  2. Enable "Event Subscriptions" → Request URL: https://<GATEWAY>/webhooks/slack
  3. Subscribe to bot events: message.im, app_mention
  4. Install the app to your workspace → copy Bot User OAuth Token (xoxb-...)
  5. Copy the Signing Secret from Basic Information

Security:
  - Every request is verified with HMAC-SHA256 using the Slack signing secret
    and the raw request body. Requests with invalid or missing signatures are
    rejected with HTTP 401.
  - Replaying old requests is blocked by checking the X-Slack-Request-Timestamp
    header (rejected if >5 minutes old).
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import time

from fastapi import APIRouter, HTTPException, Request, status
from slack_sdk.web.async_client import AsyncWebClient

from config import get_settings
from connectors.runner import run_agent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks/slack", tags=["slack"])

_MAX_TIMESTAMP_DELTA = 300  # 5 minutes — reject replayed requests


def _get_slack_client(token: str) -> AsyncWebClient:
    return AsyncWebClient(token=token)


def _verify_slack_signature(
    signing_secret: str,
    timestamp: str,
    raw_body: bytes,
    signature: str,
) -> bool:
    """Verify Slack's HMAC-SHA256 request signature."""
    try:
        ts = int(timestamp)
    except (ValueError, TypeError):
        return False

    # Reject requests older than 5 minutes (replay attack prevention)
    if abs(time.time() - ts) > _MAX_TIMESTAMP_DELTA:
        return False

    base = f"v0:{timestamp}:{raw_body.decode()}"
    expected = "v0=" + hmac.new(
        signing_secret.encode(), base.encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.post("")
async def slack_webhook(request: Request) -> dict:
    """
    Receive a Slack Events API payload.

    Handles:
      - url_verification challenge (required during app setup)
      - message events (DMs and app mentions)
    """
    settings = get_settings()
    if not settings.slack_bot_token or not settings.slack_signing_secret:
        raise HTTPException(status_code=503, detail="Slack connector not configured.")

    raw_body = await request.body()

    # ── Auth: verify Slack signature ──────────────────────────────────────────
    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    signature = request.headers.get("X-Slack-Signature", "")
    if not _verify_slack_signature(
        settings.slack_signing_secret, timestamp, raw_body, signature
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Slack signature.",
        )

    body = await request.json()
    event_type = body.get("type")

    # ── URL verification challenge (one-time during app setup) ────────────────
    if event_type == "url_verification":
        return {"challenge": body.get("challenge")}

    if event_type != "event_callback":
        return {"ok": True}

    event = body.get("event", {})
    msg_type = event.get("type")

    # Handle DMs (message.im) and app mentions (@Hermes in a channel)
    if msg_type not in ("message", "app_mention"):
        return {"ok": True}

    # Ignore bot messages to prevent loops
    if event.get("bot_id") or event.get("subtype"):
        return {"ok": True}

    text: str = event.get("text", "").strip()
    # Strip the bot mention prefix for app_mention events
    if msg_type == "app_mention":
        # text looks like "<@U012AB3CD> your question here"
        parts = text.split(">", 1)
        text = parts[1].strip() if len(parts) > 1 else text

    if not text:
        return {"ok": True}

    user_id = event.get("user", "unknown")
    channel = event.get("channel", "")

    # Slack expects a 200 response within 3 seconds.
    # We respond 200 immediately and process the agent call asynchronously.
    import asyncio  # noqa: PLC0415

    async def _reply() -> None:
        reply = await run_agent(
            platform="slack",
            platform_user_id=user_id,
            message=text,
        )
        client = _get_slack_client(settings.slack_bot_token)
        # Slack message length limit: 40 000 chars per block
        for chunk in _split_text(reply, 3000):
            await client.chat_postMessage(channel=channel, text=chunk, mrkdwn=True)

    asyncio.create_task(_reply())
    return {"ok": True}


def _split_text(text: str, limit: int) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    while text:
        chunks.append(text[:limit])
        text = text[limit:]
    return chunks
