"""
connectors/teams.py

Microsoft Teams Bot Framework connector for Hermes.

Setup:
  1. Register an Azure Bot at https://portal.azure.com
       → "Azure Bot" resource → Messaging endpoint: https://<GATEWAY>/webhooks/teams
  2. Note the App ID and generate an App Password (client secret)
  3. In Teams → Apps, install the bot to your org

Security:
  - Every request is authenticated by validating the Bearer JWT token in the
    Authorization header against Microsoft's Bot Framework token endpoint
    (https://login.botframework.com/v1/.well-known/openidconfiguration).
  - Token audience, issuer, and expiry are all validated.
  - We use httpx to fetch the JWKS and cache the public keys for 24 hours.
"""
from __future__ import annotations

import logging
import time
from functools import lru_cache

import httpx
from fastapi import APIRouter, HTTPException, Request, status
from jose import JWTError, jwk, jwt

from config import get_settings
from connectors.runner import run_agent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks/teams", tags=["teams"])

_TEAMS_OPENID_URL = (
    "https://login.botframework.com/v1/.well-known/openidconfiguration"
)
_TEAMS_BOT_FRAMEWORK_AUDIENCE = "https://api.botframework.com"
_TEAMS_ISSUER = "https://api.botframework.com"

_http = httpx.AsyncClient(timeout=10.0)

# ── JWKS cache ────────────────────────────────────────────────────────────────
# Keys are fetched once and cached for 24 h to avoid hammering Microsoft's endpoint.
_jwks_cache: dict = {}
_jwks_fetched_at: float = 0.0
_JWKS_TTL = 86400  # 24 hours


async def _get_jwks() -> list[dict]:
    global _jwks_cache, _jwks_fetched_at  # noqa: PLW0603
    if time.time() - _jwks_fetched_at < _JWKS_TTL and _jwks_cache:
        return _jwks_cache.get("keys", [])

    oidc_resp = await _http.get(_TEAMS_OPENID_URL)
    oidc_resp.raise_for_status()
    jwks_uri = oidc_resp.json()["jwks_uri"]

    jwks_resp = await _http.get(jwks_uri)
    jwks_resp.raise_for_status()
    _jwks_cache = jwks_resp.json()
    _jwks_fetched_at = time.time()
    return _jwks_cache.get("keys", [])


async def _verify_teams_token(token: str, app_id: str) -> bool:
    """Verify the Bot Framework JWT. Returns True if valid."""
    try:
        keys = await _get_jwks()
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        matching_key = next((k for k in keys if k.get("kid") == kid), None)
        if not matching_key:
            return False

        public_key = jwk.construct(matching_key)
        jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            audience=app_id,
            issuer=_TEAMS_ISSUER,
        )
        return True
    except JWTError:
        return False
    except Exception:  # noqa: BLE001
        logger.exception("Teams token verification error.")
        return False


@router.post("")
async def teams_webhook(request: Request) -> dict:
    """
    Receive a Bot Framework Activity from Microsoft Teams and reply.

    Handles Activity type 'message'; all other types are acknowledged silently.
    """
    settings = get_settings()
    if not settings.teams_app_id or not settings.teams_app_password:
        raise HTTPException(status_code=503, detail="Teams connector not configured.")

    # ── Auth: verify Bot Framework JWT ────────────────────────────────────────
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Bearer token.",
        )
    token = auth_header.removeprefix("Bearer ").strip()
    if not await _verify_teams_token(token, settings.teams_app_id):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Teams Bot Framework token.",
        )

    activity = await request.json()

    if activity.get("type") != "message":
        return {}  # acknowledge non-message activities silently

    text: str = (activity.get("text") or "").strip()
    if not text:
        return {}

    from_id: str = activity.get("from", {}).get("id", "unknown")
    service_url: str = activity.get("serviceUrl", "")
    conversation_id: str = activity.get("conversation", {}).get("id", "")
    activity_id: str = activity.get("id", "")

    reply = await run_agent(
        platform="teams",
        platform_user_id=from_id,
        message=text,
    )

    # ── Send reply via Bot Framework REST API ─────────────────────────────────
    if service_url and conversation_id:
        await _send_teams_reply(
            settings=settings,
            service_url=service_url,
            conversation_id=conversation_id,
            reply_to_id=activity_id,
            text=reply,
        )

    return {}


async def _send_teams_reply(
    settings,
    service_url: str,
    conversation_id: str,
    reply_to_id: str,
    text: str,
) -> None:
    """Obtain a Bot Framework access token and post a reply activity."""
    # ── Get Bot Framework access token ────────────────────────────────────────
    token_resp = await _http.post(
        "https://login.microsoftonline.com/botframework.com/oauth2/v2.0/token",
        data={
            "grant_type": "client_credentials",
            "client_id": settings.teams_app_id,
            "client_secret": settings.teams_app_password,
            "scope": "https://api.botframework.com/.default",
        },
    )
    token_resp.raise_for_status()
    access_token = token_resp.json()["access_token"]

    # ── Post reply activity ───────────────────────────────────────────────────
    reply_url = (
        f"{service_url.rstrip('/')}/v3/conversations"
        f"/{conversation_id}/activities/{reply_to_id}"
    )
    await _http.post(
        reply_url,
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "type": "message",
            "text": text,
            "textFormat": "markdown",
            "replyToId": reply_to_id,
        },
    )
