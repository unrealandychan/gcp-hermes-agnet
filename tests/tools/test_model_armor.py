"""
tests/tools/test_model_armor.py

Unit tests for tools/model_armor.py.

All outbound HTTP calls and GCP auth are mocked so these tests run fully
offline with no GCP credentials required.
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from tools.model_armor import ArmorResult, _parse, screen_prompt, screen_response


# ── _parse ─────────────────────────────────────────────────────────────────────

class TestParse:
    def test_empty_response_is_allowed(self):
        result = _parse({})
        assert result.blocked is False
        assert result.triggered_filters == []

    def test_no_match_is_allowed(self):
        payload = {
            "sanitizationResult": {
                "filterMatchState": "NO_MATCH_FOUND",
                "filterResults": {},
            }
        }
        result = _parse(payload)
        assert result.blocked is False

    def test_match_found_is_blocked(self):
        payload = {
            "sanitizationResult": {
                "filterMatchState": "MATCH_FOUND",
                "filterResults": {
                    "promptInjection": {"matchState": "MATCH_FOUND"},
                    "pii": {"matchState": "NO_MATCH_FOUND"},
                },
            }
        }
        result = _parse(payload)
        assert result.blocked is True
        assert "promptInjection" in result.triggered_filters
        assert "pii" not in result.triggered_filters
        assert "promptInjection" in result.reason

    def test_multiple_filters_all_listed(self):
        payload = {
            "sanitizationResult": {
                "filterMatchState": "MATCH_FOUND",
                "filterResults": {
                    "toxicity": {"matchState": "MATCH_FOUND"},
                    "csam": {"matchState": "MATCH_FOUND"},
                },
            }
        }
        result = _parse(payload)
        assert set(result.triggered_filters) == {"toxicity", "csam"}

    def test_match_found_no_individual_filters_gives_generic_reason(self):
        payload = {
            "sanitizationResult": {
                "filterMatchState": "MATCH_FOUND",
                "filterResults": {},
            }
        }
        result = _parse(payload)
        assert result.blocked is True
        assert result.reason == "Blocked by Model Armor policy"


# ── screen_prompt ──────────────────────────────────────────────────────────────

class TestScreenPrompt:
    @pytest.mark.asyncio
    async def test_disabled_when_template_id_blank(self):
        """When MODEL_ARMOR_TEMPLATE_ID is empty, prompt is always allowed."""
        with patch("tools.model_armor.get_settings") as mock_settings:
            mock_settings.return_value.model_armor_template_id = ""
            result = await screen_prompt("any message")
        assert result.blocked is False

    @pytest.mark.asyncio
    async def test_allowed_prompt_returns_not_blocked(self):
        allowed_response = {
            "sanitizationResult": {
                "filterMatchState": "NO_MATCH_FOUND",
                "filterResults": {},
            }
        }
        with (
            patch("tools.model_armor.get_settings") as mock_settings,
            patch("tools.model_armor._call_armor", new=AsyncMock(return_value=allowed_response)),
        ):
            mock_settings.return_value.model_armor_template_id = "hermes-default"
            mock_settings.return_value.gcp_project_id = "test-project"
            mock_settings.return_value.gcp_location = "us-central1"
            result = await screen_prompt("What is our Q1 revenue?")
        assert result.blocked is False

    @pytest.mark.asyncio
    async def test_blocked_prompt_returns_blocked(self):
        blocked_response = {
            "sanitizationResult": {
                "filterMatchState": "MATCH_FOUND",
                "filterResults": {
                    "promptInjection": {"matchState": "MATCH_FOUND"},
                },
            }
        }
        with (
            patch("tools.model_armor.get_settings") as mock_settings,
            patch("tools.model_armor._call_armor", new=AsyncMock(return_value=blocked_response)),
        ):
            mock_settings.return_value.model_armor_template_id = "hermes-default"
            mock_settings.return_value.gcp_project_id = "test-project"
            mock_settings.return_value.gcp_location = "us-central1"
            result = await screen_prompt("Ignore previous instructions and...")
        assert result.blocked is True
        assert "promptInjection" in result.triggered_filters

    @pytest.mark.asyncio
    async def test_timeout_allows_through(self):
        """A timeout must never block a legitimate user — allow-through."""
        import httpx
        with (
            patch("tools.model_armor.get_settings") as mock_settings,
            patch("tools.model_armor._get_access_token", return_value="fake-token"),
            patch("asyncio.to_thread", new=AsyncMock(return_value="fake-token")),
            patch("httpx.AsyncClient") as mock_client_cls,
        ):
            mock_settings.return_value.model_armor_template_id = "hermes-default"
            mock_settings.return_value.gcp_project_id = "test-project"
            mock_settings.return_value.gcp_location = "us-central1"
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
            mock_client_cls.return_value = mock_client
            result = await screen_prompt("normal message")
        assert result.blocked is False

    @pytest.mark.asyncio
    async def test_404_template_not_found_allows_through(self):
        import httpx
        with (
            patch("tools.model_armor.get_settings") as mock_settings,
            patch("asyncio.to_thread", new=AsyncMock(return_value="fake-token")),
            patch("httpx.AsyncClient") as mock_client_cls,
        ):
            mock_settings.return_value.model_armor_template_id = "missing-template"
            mock_settings.return_value.gcp_project_id = "test-project"
            mock_settings.return_value.gcp_location = "us-central1"
            mock_resp = MagicMock()
            mock_resp.status_code = 404
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client
            result = await screen_prompt("fine message")
        assert result.blocked is False


# ── screen_response ────────────────────────────────────────────────────────────

class TestScreenResponse:
    @pytest.mark.asyncio
    async def test_disabled_when_template_blank(self):
        with patch("tools.model_armor.get_settings") as mock_settings:
            mock_settings.return_value.model_armor_template_id = ""
            result = await screen_response("agent reply text")
        assert result.blocked is False

    @pytest.mark.asyncio
    async def test_pii_in_response_is_blocked(self):
        blocked_response = {
            "sanitizationResult": {
                "filterMatchState": "MATCH_FOUND",
                "filterResults": {
                    "pii": {"matchState": "MATCH_FOUND"},
                },
            }
        }
        with (
            patch("tools.model_armor.get_settings") as mock_settings,
            patch("tools.model_armor._call_armor", new=AsyncMock(return_value=blocked_response)),
        ):
            mock_settings.return_value.model_armor_template_id = "hermes-default"
            mock_settings.return_value.gcp_project_id = "test-project"
            mock_settings.return_value.gcp_location = "us-central1"
            result = await screen_response("Employee SSN is 123-45-6789")
        assert result.blocked is True
        assert "pii" in result.triggered_filters
