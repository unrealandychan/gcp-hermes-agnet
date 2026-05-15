"""
gateway/auth.py

Google OAuth2 JWT validation middleware for the Hermes API Gateway.

Validates Bearer tokens issued by Google Sign-In (ID tokens).

Scale strategy:
- Shared httpx.AsyncClient with connection pooling (no per-request client creation).
- TTLCache keyed by SHA-256 of the token: valid claims are cached for 5 minutes,
  eliminating ~100 ms Google round-trips for repeat requests from the same token.
  Cache capacity: 50 000 entries (well above 10 K concurrent users).
"""
from __future__ import annotations

import hashlib
import logging
from typing import Annotated

import httpx
from cachetools import TTLCache
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config import get_settings

logger = logging.getLogger(__name__)

_GOOGLE_TOKEN_INFO_URL = "https://oauth2.googleapis.com/tokeninfo"

# ── Shared HTTP client — one connection pool for the whole process ─────────────
_http_client = httpx.AsyncClient(
    limits=httpx.Limits(max_connections=200, max_keepalive_connections=50),
    timeout=5.0,
)

# ── Token claim cache — 5-minute TTL, keyed by SHA-256(token) ─────────────────
# Keeps validated claims in memory so we don't hit Google on every request.
# 50K entries × ~500 bytes ≈ 25 MB worst case.
_token_cache: TTLCache = TTLCache(maxsize=50_000, ttl=300)

_bearer = HTTPBearer(auto_error=True)


async def verify_google_token(
    credentials: Annotated[HTTPAuthorizationCredentials, Security(_bearer)],
) -> dict:
    """
    Validate a Google ID token and return the decoded claims.

    Raises HTTP 401 on invalid/expired token.
    Cached for 5 minutes to avoid a Google round-trip on every request.
    """
    token = credentials.credentials
    settings = get_settings()

    # ── Cache look-up (store hash, not raw token) ──────────────────────────────
    cache_key = hashlib.sha256(token.encode()).hexdigest()
    cached = _token_cache.get(cache_key)
    if cached is not None:
        return cached

    resp = await _http_client.get(
        _GOOGLE_TOKEN_INFO_URL,
        params={"id_token": token},
    )

    if resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired Google ID token.",
        )

    claims = resp.json()

    # Validate audience matches our configured client ID
    if settings.google_client_id and claims.get("aud") != settings.google_client_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token audience mismatch.",
        )

    # Validate issuer
    if claims.get("iss") not in (
        "accounts.google.com",
        "https://accounts.google.com",
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token issuer.",
        )

    # ── Store in cache; next request for this token is free ───────────────────
    _token_cache[cache_key] = claims
    return claims


CurrentUser = Annotated[dict, Depends(verify_google_token)]
