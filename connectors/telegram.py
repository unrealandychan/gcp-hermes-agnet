"""
connectors/telegram.py

Telegram Bot webhook connector for Hermes.

Setup (one-time):
  1. Create a bot via @BotFather → get TELEGRAM_BOT_TOKEN
  2. After deploying to Cloud Run, register the webhook:
       curl "https://api.telegram.org/bot<TOKEN>/setWebhook" \
         -d url="https://<YOUR_GATEWAY_URL>/webhooks/telegram" \
         -d secret_token="<TELEGRAM_WEBHOOK_SECRET>"

Security:
  - Every incoming request is verified via the X-Telegram-Bot-Api-Secret-Token
    header (set when registering the webhook). Requests without a matching
    secret are rejected with HTTP 401.
  - Outbound replies use the bot token only in the URL path (not a header), which
    is the standard Telegram Bot API pattern.
"""
from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Header, HTTPException, Request, status

from config import get_settings
from connectors.runner import run_agent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks/telegram", tags=["telegram"])

_TELEGRAM_API = "https://api.telegram.org"

# Shared outbound client
_http = httpx.AsyncClient(timeout=10.0)


async def _send_message(token: str, chat_id: int | str, text: str) -> None:
    """Send a text reply to a Telegram chat."""
    # Telegram messages have a 4096-char limit — split if needed
    for chunk in _split_text(text, 4096):
        await _http.post(
            f"{_TELEGRAM_API}/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": chunk, "parse_mode": "Markdown"},
        )


def _split_text(text: str, limit: int) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    while text:
        chunks.append(text[:limit])
        text = text[limit:]
    return chunks


@router.post("")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict:
    """
    Receive an Update from Telegram and reply via the Bot API.

    Telegram sends POST requests with a JSON body containing an Update object.
    We only handle message updates (text messages); other update types are ignored.
    """
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise HTTPException(status_code=503, detail="Telegram connector not configured.")

    # ── Auth: verify webhook secret ───────────────────────────────────────────
    if x_telegram_bot_api_secret_token != settings.telegram_webhook_secret:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid secret.")

    body = await request.json()
    message = body.get("message") or body.get("edited_message")
    if not message:
        return {"ok": True}  # ignore non-message updates (polls, reactions, etc.)

    text: str = message.get("text", "").strip()
    if not text:
        return {"ok": True}  # ignore stickers, photos, etc.

    chat_id = message["chat"]["id"]
    from_id = str(message["from"]["id"])

    # Run agent asynchronously — Telegram expects a 200 response within ~5s,
    # but we reply via the API so we can take as long as needed.
    reply = await run_agent(
        platform="telegram",
        platform_user_id=from_id,
        message=text,
    )

    await _send_message(settings.telegram_bot_token, chat_id, reply)
    return {"ok": True}
