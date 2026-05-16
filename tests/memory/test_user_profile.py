"""
tests/memory/test_user_profile.py

Unit tests for memory.user_profile — fully offline, Firestore mocked.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_doc(exists: bool, data: dict | None = None):
    doc = MagicMock()
    doc.exists = exists
    doc.to_dict.return_value = data or {}
    return doc


class TestUserProfileModel:
    def test_to_prompt_summary_full(self):
        from memory.user_profile import UserProfile
        p = UserProfile(
            user_id="u1",
            name="Alice",
            role="Engineer",
            department="Platform",
            preferences={"style": "concise"},
        )
        summary = p.to_prompt_summary()
        assert "Alice" in summary
        assert "Engineer" in summary
        assert "Platform" in summary
        assert "concise" in summary

    def test_to_prompt_summary_minimal(self):
        from memory.user_profile import UserProfile
        p = UserProfile(user_id="u1")
        summary = p.to_prompt_summary()
        assert "u1" in summary

    def test_token_estimate_positive(self):
        from memory.user_profile import UserProfile
        p = UserProfile(user_id="u1", name="Alice", role="Engineer")
        assert p.prompt_token_estimate > 0


class TestGetOrCreateProfile:
    @pytest.mark.asyncio
    async def test_returns_existing_profile(self):
        mock_doc = _make_doc(True, {"name": "Alice", "role": "Engineer"})
        mock_col = MagicMock()
        mock_col.document.return_value.get = AsyncMock(return_value=mock_doc)
        mock_db = MagicMock()
        mock_db.collection.return_value = mock_col

        with patch("memory.user_profile._get_firestore_client", return_value=mock_db):
            from memory.user_profile import get_or_create_profile
            profile = await get_or_create_profile("u1")

        assert profile.user_id == "u1"
        assert profile.name == "Alice"
        assert profile.role == "Engineer"

    @pytest.mark.asyncio
    async def test_creates_minimal_profile_when_not_found(self):
        mock_doc = _make_doc(False)
        mock_col = MagicMock()
        mock_col.document.return_value.get = AsyncMock(return_value=mock_doc)
        mock_db = MagicMock()
        mock_db.collection.return_value = mock_col

        with patch("memory.user_profile._get_firestore_client", return_value=mock_db):
            from memory.user_profile import get_or_create_profile
            profile = await get_or_create_profile("new_user")

        assert profile.user_id == "new_user"
        assert profile.name == ""

    @pytest.mark.asyncio
    async def test_returns_minimal_profile_on_firestore_error(self):
        with patch("memory.user_profile._get_firestore_client", side_effect=Exception("Firestore down")):
            from memory.user_profile import get_or_create_profile
            profile = await get_or_create_profile("u1")

        assert profile.user_id == "u1"
        assert profile.name == ""


class TestUpdateProfile:
    @pytest.mark.asyncio
    async def test_calls_firestore_set_with_merge(self):
        mock_col = MagicMock()
        mock_col.document.return_value.set = AsyncMock()
        mock_db = MagicMock()
        mock_db.collection.return_value = mock_col

        with patch("memory.user_profile._get_firestore_client", return_value=mock_db):
            from memory.user_profile import update_profile
            await update_profile("u1", {"name": "Bob"})

        mock_col.document.return_value.set.assert_called_once()
        call_kwargs = mock_col.document.return_value.set.call_args
        assert call_kwargs.kwargs.get("merge") is True or call_kwargs.args[1] is True

    @pytest.mark.asyncio
    async def test_does_not_raise_on_firestore_error(self):
        with patch("memory.user_profile._get_firestore_client", side_effect=Exception("network error")):
            from memory.user_profile import update_profile
            # Should not raise
            await update_profile("u1", {"name": "Bob"})
