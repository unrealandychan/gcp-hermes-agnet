"""
tools/model_armor.py

Google Cloud Model Armor integration.
https://cloud.google.com/model-armor/docs

Screens user prompts and model responses for:
  • Prompt injection / jailbreak attacks
  • PII / sensitive-data leakage
  • Toxic or harmful content (Safe Search)
  • CSAM detection

Usage in gateway:
    from tools.model_armor import screen_prompt, screen_response, ArmorResult

    result = await screen_prompt(user_message)
    if result.blocked:
        raise HTTPException(status_code=400, detail=result.reason)

Configuration (.env):
    MODEL_ARMOR_TEMPLATE_ID=hermes-default   # leave blank to disable
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

import google.auth
import google.auth.transport.requests
import httpx

from config import get_settings

logger = logging.getLogger(__name__)

# Regional Model Armor REST endpoint
_ENDPOINT_TMPL = "https://modelarmor.{location}.rep.googleapis.com/v1"


@dataclass
class ArmorResult:
    blocked: bool
    reason: str = ""
    triggered_filters: list[str] = field(default_factory=list)


def _get_access_token() -> str:
    credentials, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    credentials.refresh(google.auth.transport.requests.Request())
    return credentials.token  # type: ignore[attr-defined]


async def _call_armor(operation: str, payload: dict) -> dict:
    """
    POST to a Model Armor sanitize operation.
    Returns {} (allow-through) if the template is not configured, the
    service is unreachable, or any transient error occurs.
    """
    settings = get_settings()
    template_id = settings.model_armor_template_id
    if not template_id:
        return {}  # feature disabled

    base = _ENDPOINT_TMPL.format(location=settings.gcp_location)
    template_path = (
        f"projects/{settings.gcp_project_id}"
        f"/locations/{settings.gcp_location}"
        f"/templates/{template_id}"
    )
    url = f"{base}/{template_path}:{operation}"

    try:
        token = await asyncio.to_thread(_get_access_token)
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
            )
        if resp.status_code == 404:
            logger.warning(
                "Model Armor template '%s' not found — skipping screening.", template_id
            )
            return {}
        resp.raise_for_status()
        return resp.json()
    except httpx.TimeoutException:
        logger.warning("Model Armor request timed out — allowing through.")
        return {}
    except Exception:  # noqa: BLE001
        logger.exception("Model Armor call failed — allowing through.")
        return {}


def _parse(response: dict) -> ArmorResult:
    if not response:
        return ArmorResult(blocked=False)

    result = response.get("sanitizationResult", {})
    if result.get("filterMatchState") != "MATCH_FOUND":
        return ArmorResult(blocked=False)

    triggered = [
        name
        for name, data in result.get("filterResults", {}).items()
        if data.get("matchState") == "MATCH_FOUND"
    ]
    reason = (
        f"Blocked by Model Armor: {', '.join(triggered)}"
        if triggered
        else "Blocked by Model Armor policy"
    )
    return ArmorResult(blocked=True, reason=reason, triggered_filters=triggered)


async def screen_prompt(text: str) -> ArmorResult:
    """
    Screen a user prompt before sending to the agent.
    Catches prompt injections, jailbreaks, and PII in the user's message.
    """
    response = await _call_armor(
        "sanitizeUserPrompt",
        {"userPromptData": {"text": text}},
    )
    return _parse(response)


async def screen_response(text: str) -> ArmorResult:
    """
    Screen a model response before returning it to the user.
    Catches accidental PII leakage or toxic content in agent output.
    """
    response = await _call_armor(
        "sanitizeModelResponse",
        {"modelResponseData": {"text": text}},
    )
    return _parse(response)
