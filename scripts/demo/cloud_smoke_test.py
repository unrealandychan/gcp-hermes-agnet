#!/usr/bin/env python3
"""
Read-only cloud smoke test for deployed Hermes endpoints.

Modes:
- gateway: call deployed HTTP gateway /chat and parse SSE response
- sdk: fetch existing Reasoning Engine by resource name and issue query
- auto: choose gateway when GATEWAY_URL is set, otherwise sdk

This script never creates or updates cloud resources.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from typing import Any, Callable

import httpx
import vertexai
from vertexai import agent_engines


@dataclass
class SmokeResult:
    ok: bool
    mode: str
    detail: str


def _auth_headers(bearer_token: str, api_key: str) -> dict[str, str]:
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"
    elif api_key:
        headers["Authorization"] = f"Bearer {api_key}"
        headers["X-API-Key"] = api_key
    return headers


def probe_gateway(
    gateway_url: str,
    message: str,
    bearer_token: str,
    api_key: str,
    timeout_s: int,
) -> SmokeResult:
    url = gateway_url.rstrip("/") + "/chat"
    headers = _auth_headers(bearer_token=bearer_token, api_key=api_key)

    try:
        with httpx.Client(timeout=timeout_s) as client:
            resp = client.post(url, headers=headers, json={"message": message})
    except Exception as exc:  # noqa: BLE001
        return SmokeResult(False, "gateway", f"request failed: {exc}")

    if resp.status_code >= 400:
        body_preview = resp.text[:300]
        return SmokeResult(
            False,
            "gateway",
            f"HTTP {resp.status_code} from {url}: {body_preview}",
        )

    had_done = False
    had_error = False
    last_text = ""
    for line in resp.text.splitlines():
        if not line.startswith("data: "):
            continue
        payload = line.removeprefix("data: ").strip()
        if not payload:
            continue
        try:
            event = json.loads(payload)
        except json.JSONDecodeError:
            continue

        event_type = event.get("type")
        if event_type == "error":
            had_error = True
            last_text = str(event.get("content", ""))
        elif event_type == "text":
            last_text = str(event.get("content", ""))
        elif event_type == "done":
            had_done = True

    if had_error:
        return SmokeResult(False, "gateway", f"SSE error event: {last_text[:300]}")
    if not had_done:
        return SmokeResult(False, "gateway", "SSE stream did not complete (missing done event)")

    preview = (last_text or "<empty>").strip().replace("\n", " ")[:240]
    return SmokeResult(True, "gateway", f"gateway chat ok: {preview}")


def _extract_text(response: Any) -> str:
    if response is None:
        return ""
    if isinstance(response, str):
        return response
    if isinstance(response, dict):
        return str(response.get("text") or response.get("output_text") or response)
    text = getattr(response, "text", None)
    if text:
        return str(text)
    return str(response)


def probe_sdk(
    project_id: str,
    location: str,
    reasoning_engine_resource_name: str,
    user_id: str,
    message: str,
    client_factory: Callable[[], Any] | None = None,
) -> SmokeResult:
    if not project_id or not location or not reasoning_engine_resource_name:
        return SmokeResult(
            False,
            "sdk",
            "missing required config: GCP_PROJECT_ID, GCP_LOCATION, REASONING_ENGINE_RESOURCE_NAME",
        )

    try:
        vertexai.init(project=project_id, location=location)
        client = client_factory() if client_factory else agent_engines.AgentEngineClient()
        remote_agent = client.get_reasoning_engine(name=reasoning_engine_resource_name)
        response = remote_agent.query(user_id=user_id, message=message)
        preview = _extract_text(response).strip().replace("\n", " ")[:240] or "<empty>"
        return SmokeResult(True, "sdk", f"sdk query ok: {preview}")
    except Exception as exc:  # noqa: BLE001
        return SmokeResult(False, "sdk", f"sdk probe failed: {exc}")


def _detect_mode(requested_mode: str, gateway_url: str) -> str:
    if requested_mode != "auto":
        return requested_mode
    return "gateway" if gateway_url else "sdk"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only smoke test for deployed Hermes cloud runtime")
    parser.add_argument("--mode", choices=["auto", "gateway", "sdk"], default="auto")
    parser.add_argument("--gateway-url", default=os.environ.get("GATEWAY_URL", ""))
    parser.add_argument("--token", default=os.environ.get("GOOGLE_ID_TOKEN", ""))
    parser.add_argument("--api-key", default=os.environ.get("AGENT_GATEWAY_API_KEY", ""))
    parser.add_argument("--project-id", default=os.environ.get("GCP_PROJECT_ID", ""))
    parser.add_argument("--location", default=os.environ.get("GCP_LOCATION", ""))
    parser.add_argument(
        "--reasoning-engine",
        default=os.environ.get("REASONING_ENGINE_RESOURCE_NAME", ""),
        help="projects/.../locations/.../reasoningEngines/...",
    )
    parser.add_argument("--user-id", default=os.environ.get("SMOKE_USER_ID", "smoke-test-user"))
    parser.add_argument("--message", default=os.environ.get("SMOKE_MESSAGE", "Reply with 'ok'."))
    parser.add_argument("--timeout", type=int, default=int(os.environ.get("SMOKE_TIMEOUT", "30")))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    mode = _detect_mode(args.mode, args.gateway_url)

    if mode == "gateway":
        if not args.gateway_url:
            print("❌ FAIL [gateway] missing GATEWAY_URL", file=sys.stderr)
            return 1
        result = probe_gateway(
            gateway_url=args.gateway_url,
            message=args.message,
            bearer_token=args.token,
            api_key=args.api_key,
            timeout_s=args.timeout,
        )
    else:
        result = probe_sdk(
            project_id=args.project_id,
            location=args.location,
            reasoning_engine_resource_name=args.reasoning_engine,
            user_id=args.user_id,
            message=args.message,
        )

    if result.ok:
        print(f"✅ PASS [{result.mode}] {result.detail}")
        return 0

    print(f"❌ FAIL [{result.mode}] {result.detail}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
