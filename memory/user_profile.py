"""
memory/user_profile.py

User profile store — persists stable facts about a user across sessions.

User profiles are distinct from procedural memory (skills):
- User profile: WHO the user is (role, name, preferences, communication style)
- Skills: WHAT the agent has learned to do (procedures, workflows, domain knowledge)

Storage: Firestore (already a project dependency).
Collection: "user_profiles" — one document per user_id.

This separation ensures:
1. Profile facts are always injected with highest priority (smallest token cost).
2. Procedural memory can be trimmed without losing user identity context.
3. Profile is human-editable in the Firestore console for quick corrections.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_COLLECTION = "user_profiles"


class UserProfile(BaseModel):
    """Stable facts about a user, persisted across sessions."""

    user_id: str
    name: str = ""
    role: str = ""
    department: str = ""
    preferences: dict[str, Any] = Field(default_factory=dict)
    # e.g. {"response_style": "concise", "timezone": "Asia/Hong_Kong"}
    last_seen: str = ""  # ISO-8601 UTC

    def to_prompt_summary(self) -> str:
        """Return a compact string suitable for injection into a system prompt."""
        parts = [f"User: {self.user_id}"]
        if self.name:
            parts.append(f"Name: {self.name}")
        if self.role:
            parts.append(f"Role: {self.role}")
        if self.department:
            parts.append(f"Department: {self.department}")
        if self.preferences:
            prefs = "; ".join(f"{k}={v}" for k, v in self.preferences.items())
            parts.append(f"Preferences: {prefs}")
        return " | ".join(parts)

    @property
    def prompt_token_estimate(self) -> int:
        """Rough token estimate (4 chars ≈ 1 token)."""
        return max(1, len(self.to_prompt_summary()) // 4)


def _get_firestore_client():
    """Lazy import — avoids import errors when Firestore is not available."""
    from google.cloud import firestore
    return firestore.AsyncClient()


async def get_or_create_profile(user_id: str) -> UserProfile:
    """
    Fetch the user profile from Firestore, or create a minimal one if absent.

    Never raises — returns a minimal profile on any error so the caller is
    never blocked by a Firestore outage.
    """
    try:
        db = _get_firestore_client()
        doc = await db.collection(_COLLECTION).document(user_id).get()
        if doc.exists:
            data = doc.to_dict() or {}
            data["user_id"] = user_id
            return UserProfile(**{k: v for k, v in data.items() if k in UserProfile.model_fields})
    except Exception:  # noqa: BLE001
        logger.warning("Could not fetch user profile for %s — using minimal profile.", user_id, exc_info=True)

    return UserProfile(user_id=user_id)


async def update_profile(user_id: str, updates: dict[str, Any]) -> None:
    """
    Upsert profile fields for a user.

    Only fields present in updates are modified; other fields are preserved.
    Always stamps last_seen to current UTC time.
    """
    try:
        db = _get_firestore_client()
        updates["last_seen"] = datetime.now(timezone.utc).isoformat()
        await db.collection(_COLLECTION).document(user_id).set(updates, merge=True)
        logger.debug("Updated user profile for %s: %s", user_id, list(updates.keys()))
    except Exception:  # noqa: BLE001
        logger.exception("Failed to update user profile for %s.", user_id)
