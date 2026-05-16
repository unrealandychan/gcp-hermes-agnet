#!/usr/bin/env python3
"""
scripts/demo/e2e_test.py

End-to-end async test suite for the Hermes Agent PoC.

Tests every major feature:
  ✓ Health check
  ✓ Chat SSE stream — HR, IT, Developer, Analytics agents
  ✓ Multi-turn conversation (session continuity)
  ✓ Long-running task: submit → poll → done
  ✓ Task cancellation
  ✓ Self-scheduling: create → list → delete scheduled jobs
  ✓ Google Workspace: Gmail search, Calendar create, Drive search
  ✓ BigQuery analytics via chat

Usage:
    cd hermes-gcp
    pip install httpx
    python scripts/demo/e2e_test.py

Environment variables:
    GATEWAY_URL   — default http://localhost:8080
    GOOGLE_ID_TOKEN — pre-fetched token (falls back to gcloud auth)
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Any

import httpx

GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://localhost:8080").rstrip("/")
TIMEOUT_TASK_POLL = int(os.environ.get("TIMEOUT_TASK_POLL", "120"))  # seconds
TIMEOUT_CHAT = int(os.environ.get("TIMEOUT_CHAT", "60"))  # seconds


# ── Token ──────────────────────────────────────────────────────────────────────

def get_token() -> str:
    if tok := os.environ.get("GOOGLE_ID_TOKEN"):
        return tok
    try:
        result = subprocess.run(
            ["gcloud", "auth", "print-identity-token"],
            capture_output=True, text=True, timeout=10, check=True,
        )
        return result.stdout.strip()
    except Exception:  # noqa: BLE001
        return "DUMMY_TOKEN_FOR_LOCAL_DEV"


TOKEN = get_token()
AUTH_HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
}


# ── Result tracking ────────────────────────────────────────────────────────────

@dataclass
class TestResult:
    name: str
    passed: bool
    duration_s: float
    detail: str = ""


results: list[TestResult] = []


def record(name: str, passed: bool, duration_s: float, detail: str = "") -> TestResult:
    r = TestResult(name=name, passed=passed, duration_s=duration_s, detail=detail)
    results.append(r)
    status = "✓" if passed else "✗"
    color = "\033[0;32m" if passed else "\033[0;31m"
    reset = "\033[0m"
    print(f"  {color}{status}{reset}  [{duration_s:.1f}s] {name}" + (f" — {detail}" if detail else ""))
    return r


# ── HTTP helpers ───────────────────────────────────────────────────────────────

async def chat_sse(
    client: httpx.AsyncClient,
    message: str,
    session_id: str | None = None,
) -> tuple[str, str | None]:
    """
    Send a chat message via SSE stream.
    Returns (response_text, new_session_id).
    """
    body: dict[str, Any] = {"message": message}
    if session_id:
        body["session_id"] = session_id

    chunks: list[str] = []
    new_session_id: str | None = None

    async with client.stream(
        "POST",
        f"{GATEWAY_URL}/chat",
        json=body,
        headers=AUTH_HEADERS,
        timeout=TIMEOUT_CHAT,
    ) as response:
        if response.status_code != 200:
            return f"HTTP {response.status_code}", None

        async for line in response.aiter_lines():
            if not line.startswith("data:"):
                continue
            raw = line[5:].strip()
            if not raw:
                continue
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                continue

            ev_type = event.get("type", "")
            if ev_type == "text" and event.get("content"):
                chunks.append(event["content"])
            elif ev_type == "done":
                new_session_id = event.get("session_id")
                break

    return "".join(chunks), new_session_id


async def submit_task(client: httpx.AsyncClient, task: str, context: dict | None = None) -> str:
    """Submit a long-running task and return the task_id."""
    resp = await client.post(
        f"{GATEWAY_URL}/tasks",
        json={"task": task, "context": context or {}},
        headers=AUTH_HEADERS,
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["task_id"]


async def get_task(client: httpx.AsyncClient, task_id: str) -> dict:
    resp = await client.get(
        f"{GATEWAY_URL}/tasks/{task_id}",
        headers=AUTH_HEADERS,
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


async def cancel_task(client: httpx.AsyncClient, task_id: str) -> dict:
    resp = await client.delete(
        f"{GATEWAY_URL}/tasks/{task_id}",
        headers=AUTH_HEADERS,
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


async def list_tasks(client: httpx.AsyncClient) -> list[dict]:
    resp = await client.get(
        f"{GATEWAY_URL}/tasks",
        headers=AUTH_HEADERS,
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


async def poll_until_done(
    client: httpx.AsyncClient,
    task_id: str,
    timeout_s: int = TIMEOUT_TASK_POLL,
    interval_s: int = 5,
) -> dict:
    """Poll a task until it reaches a terminal state or timeout."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        data = await get_task(client, task_id)
        if data.get("status") in ("done", "failed", "cancelled"):
            return data
        await asyncio.sleep(interval_s)
    return await get_task(client, task_id)


# =============================================================================
# TEST CASES
# =============================================================================

async def test_health(client: httpx.AsyncClient) -> None:
    t0 = time.monotonic()
    try:
        resp = await client.get(f"{GATEWAY_URL}/health", timeout=10)
        passed = resp.status_code == 200
        record("Health check", passed, time.monotonic() - t0,
               f"status={resp.status_code}")
    except Exception as exc:
        record("Health check", False, time.monotonic() - t0, str(exc))


async def test_chat_hr_pto(client: httpx.AsyncClient) -> None:
    t0 = time.monotonic()
    try:
        response, _ = await chat_sse(client, "How many PTO days do employees get per year at Acme?")
        passed = len(response) > 20 and any(
            kw in response.lower() for kw in ("pto", "vacation", "day", "annual")
        )
        record("Chat — HR PTO policy", passed, time.monotonic() - t0,
               response[:80].replace("\n", " ") + "…")
    except Exception as exc:
        record("Chat — HR PTO policy", False, time.monotonic() - t0, str(exc))


async def test_chat_hr_benefits(client: httpx.AsyncClient) -> None:
    t0 = time.monotonic()
    try:
        response, _ = await chat_sse(client, "What health insurance options does Acme offer?")
        passed = len(response) > 20 and any(
            kw in response.lower() for kw in ("health", "insurance", "aetna", "benefit", "plan")
        )
        record("Chat — HR benefits", passed, time.monotonic() - t0,
               response[:80].replace("\n", " ") + "…")
    except Exception as exc:
        record("Chat — HR benefits", False, time.monotonic() - t0, str(exc))


async def test_chat_it_vpn(client: httpx.AsyncClient) -> None:
    t0 = time.monotonic()
    try:
        response, _ = await chat_sse(client, "How do I install and configure Cisco AnyConnect VPN on macOS?")
        passed = len(response) > 20 and any(
            kw in response.lower() for kw in ("anyconnect", "vpn", "cisco", "download", "install")
        )
        record("Chat — IT VPN setup", passed, time.monotonic() - t0,
               response[:80].replace("\n", " ") + "…")
    except Exception as exc:
        record("Chat — IT VPN setup", False, time.monotonic() - t0, str(exc))


async def test_chat_it_incident(client: httpx.AsyncClient) -> None:
    t0 = time.monotonic()
    try:
        response, _ = await chat_sse(
            client,
            "The production API is completely down. What is the P0 incident response procedure?"
        )
        passed = len(response) > 20 and any(
            kw in response.lower() for kw in ("p0", "incident", "escalat", "on-call", "response")
        )
        record("Chat — IT P0 incident", passed, time.monotonic() - t0,
               response[:80].replace("\n", " ") + "…")
    except Exception as exc:
        record("Chat — IT P0 incident", False, time.monotonic() - t0, str(exc))


async def test_chat_developer_deploy(client: httpx.AsyncClient) -> None:
    t0 = time.monotonic()
    try:
        response, _ = await chat_sse(client, "How do I deploy to production using the CI/CD pipeline?")
        passed = len(response) > 20 and any(
            kw in response.lower() for kw in ("deploy", "pipeline", "cloud run", "github", "ci")
        )
        record("Chat — Developer deploy", passed, time.monotonic() - t0,
               response[:80].replace("\n", " ") + "…")
    except Exception as exc:
        record("Chat — Developer deploy", False, time.monotonic() - t0, str(exc))


async def test_chat_analytics_bigquery(client: httpx.AsyncClient) -> None:
    t0 = time.monotonic()
    try:
        response, _ = await chat_sse(
            client,
            "How many employees are in each department? Query hermes_demo.employees."
        )
        passed = len(response) > 20 and any(
            kw in response.lower() for kw in ("engineering", "sales", "department", "employee", "count")
        )
        record("Chat — Analytics headcount", passed, time.monotonic() - t0,
               response[:80].replace("\n", " ") + "…")
    except Exception as exc:
        record("Chat — Analytics headcount", False, time.monotonic() - t0, str(exc))


async def test_chat_analytics_sales(client: httpx.AsyncClient) -> None:
    t0 = time.monotonic()
    try:
        response, _ = await chat_sse(
            client,
            "What was the total revenue by region for Q1 2025? Use hermes_demo.sales_performance."
        )
        passed = len(response) > 20 and any(
            kw in response.lower()
            for kw in ("north america", "emea", "apac", "revenue", "region")
        )
        record("Chat — Analytics sales Q1", passed, time.monotonic() - t0,
               response[:80].replace("\n", " ") + "…")
    except Exception as exc:
        record("Chat — Analytics sales Q1", False, time.monotonic() - t0, str(exc))


async def test_multiturn_session(client: httpx.AsyncClient) -> None:
    t0 = time.monotonic()
    try:
        _, session_id = await chat_sse(
            client,
            "My name is Alice Chen and I'm in Engineering."
        )
        if not session_id:
            record("Multi-turn session", False, time.monotonic() - t0, "No session_id returned")
            return

        response2, _ = await chat_sse(
            client,
            "Based on our conversation, which department do I work in?",
            session_id=session_id,
        )
        passed = "engineering" in response2.lower() or "alice" in response2.lower()
        record("Multi-turn session", passed, time.monotonic() - t0,
               f"session={session_id[:16]}… response: {response2[:60].replace(chr(10), ' ')}")
    except Exception as exc:
        record("Multi-turn session", False, time.monotonic() - t0, str(exc))


async def test_long_running_task(client: httpx.AsyncClient) -> None:
    t0 = time.monotonic()
    try:
        task_id = await submit_task(
            client,
            "Count the total number of employees in hermes_demo.employees and the total number of approved PTO requests in hermes_demo.pto_requests. Return a one-sentence summary with both numbers.",
            context={"demo": True},
        )
        initial = await get_task(client, task_id)
        if initial.get("status") not in ("pending", "running", "done"):
            record("Long-running task: submit", False, time.monotonic() - t0,
                   f"unexpected status: {initial.get('status')}")
            return
        record("Long-running task: submit", True, time.monotonic() - t0,
               f"task_id={task_id}")

        # Poll
        t_poll = time.monotonic()
        final = await poll_until_done(client, task_id, timeout_s=TIMEOUT_TASK_POLL)
        passed = final.get("status") == "done"
        result_snippet = str(final.get("result", ""))[:80].replace("\n", " ")
        record("Long-running task: poll→done", passed, time.monotonic() - t_poll,
               f"status={final.get('status')} result={result_snippet}")
    except Exception as exc:
        record("Long-running task", False, time.monotonic() - t0, str(exc))


async def test_task_cancellation(client: httpx.AsyncClient) -> None:
    t0 = time.monotonic()
    try:
        # Submit a very long task we will immediately cancel
        task_id = await submit_task(
            client,
            "Run a comprehensive audit of all 12 months of sales data for all 4 regions and all 3 products, building detailed charts. This will take a while.",
        )
        await asyncio.sleep(1)  # let it start
        result = await cancel_task(client, task_id)
        passed = result.get("status") in ("cancelled", "cancelling")
        record("Task cancellation", passed, time.monotonic() - t0,
               f"task_id={task_id} status={result.get('status')}")
    except Exception as exc:
        record("Task cancellation", False, time.monotonic() - t0, str(exc))


async def test_task_list(client: httpx.AsyncClient) -> None:
    t0 = time.monotonic()
    try:
        tasks = await list_tasks(client)
        passed = isinstance(tasks, list)
        record("List tasks", passed, time.monotonic() - t0,
               f"{len(tasks)} tasks returned")
    except Exception as exc:
        record("List tasks", False, time.monotonic() - t0, str(exc))


async def test_self_scheduling(client: httpx.AsyncClient) -> None:
    """Test the self-scheduling feature via chat."""
    t0 = time.monotonic()
    try:
        response, _ = await chat_sse(
            client,
            "Schedule a Cloud Scheduler job called e2e-test-job to run every day at 8 AM UTC with the task: send a health check email."
        )
        passed = len(response) > 10 and any(
            kw in response.lower()
            for kw in ("schedule", "job", "created", "cloud scheduler", "e2e-test-job", "8 am", "cron")
        )
        record("Self-scheduling: create job", passed, time.monotonic() - t0,
               response[:80].replace("\n", " ") + "…")

        # List jobs
        t2 = time.monotonic()
        list_response, _ = await chat_sse(client, "List all currently scheduled Cloud Scheduler jobs.")
        list_passed = len(list_response) > 10
        record("Self-scheduling: list jobs", list_passed, time.monotonic() - t2,
               list_response[:80].replace("\n", " ") + "…")

        # Delete test job
        t3 = time.monotonic()
        del_response, _ = await chat_sse(
            client,
            "Delete the scheduled job named e2e-test-job."
        )
        del_passed = len(del_response) > 10 and any(
            kw in del_response.lower()
            for kw in ("deleted", "removed", "e2e-test-job", "success")
        )
        record("Self-scheduling: delete job", del_passed, time.monotonic() - t3,
               del_response[:80].replace("\n", " ") + "…")

    except Exception as exc:
        record("Self-scheduling", False, time.monotonic() - t0, str(exc))


async def test_workspace_gmail(client: httpx.AsyncClient) -> None:
    t0 = time.monotonic()
    try:
        response, _ = await chat_sse(
            client,
            "Search Gmail for emails from noah.anderson@acmecorp.com in the last 7 days."
        )
        passed = len(response) > 10
        record("Workspace — Gmail search", passed, time.monotonic() - t0,
               response[:80].replace("\n", " ") + "…")
    except Exception as exc:
        record("Workspace — Gmail search", False, time.monotonic() - t0, str(exc))


async def test_workspace_calendar(client: httpx.AsyncClient) -> None:
    t0 = time.monotonic()
    try:
        response, _ = await chat_sse(
            client,
            "Create a calendar event: E2E Test Meeting, May 19 2026 at 3 PM UTC for 30 minutes, invite alice.chen@acmecorp.com."
        )
        passed = len(response) > 10 and any(
            kw in response.lower()
            for kw in ("calendar", "event", "created", "meeting", "scheduled", "invite")
        )
        record("Workspace — Calendar create", passed, time.monotonic() - t0,
               response[:80].replace("\n", " ") + "…")
    except Exception as exc:
        record("Workspace — Calendar create", False, time.monotonic() - t0, str(exc))


async def test_workspace_drive(client: httpx.AsyncClient) -> None:
    t0 = time.monotonic()
    try:
        response, _ = await chat_sse(
            client,
            "Search Google Drive for documents about onboarding or new employee checklist."
        )
        passed = len(response) > 10
        record("Workspace — Drive search", passed, time.monotonic() - t0,
               response[:80].replace("\n", " ") + "…")
    except Exception as exc:
        record("Workspace — Drive search", False, time.monotonic() - t0, str(exc))


async def test_open_incidents(client: httpx.AsyncClient) -> None:
    t0 = time.monotonic()
    try:
        response, _ = await chat_sse(
            client,
            "Query hermes_demo.it_incidents and tell me which incidents are currently Open or In Progress, their severity, and assignee."
        )
        passed = len(response) > 20 and any(
            kw in response.lower()
            for kw in ("inc-013", "inc-014", "inc-015", "open", "in progress", "phishing")
        )
        record("Analytics — open incidents", passed, time.monotonic() - t0,
               response[:80].replace("\n", " ") + "…")
    except Exception as exc:
        record("Analytics — open incidents", False, time.monotonic() - t0, str(exc))


async def test_pending_pto(client: httpx.AsyncClient) -> None:
    t0 = time.monotonic()
    try:
        response, _ = await chat_sse(
            client,
            "List all pending PTO requests from hermes_demo.pto_requests. Who is waiting for approval?"
        )
        passed = len(response) > 20 and any(
            kw in response.lower()
            for kw in ("pending", "pto", "david", "grace", "iris", "tina", "bob", "emma", "liam")
        )
        record("Analytics — pending PTO", passed, time.monotonic() - t0,
               response[:80].replace("\n", " ") + "…")
    except Exception as exc:
        record("Analytics — pending PTO", False, time.monotonic() - t0, str(exc))


# =============================================================================
# RUNNER
# =============================================================================

async def main() -> None:
    print(f"\n\033[1m{'Hermes Agent — E2E Test Suite':^60}\033[0m")
    print(f"Gateway: \033[0;36m{GATEWAY_URL}\033[0m")
    print(f"Token:   \033[0;36m{TOKEN[:25]}…\033[0m")
    print(f"Task poll timeout: {TIMEOUT_TASK_POLL}s\n")

    async with httpx.AsyncClient(timeout=TIMEOUT_CHAT + 5) as client:

        print("\033[1;33m── Core Agent Chat ──\033[0m")
        await test_health(client)
        await test_chat_hr_pto(client)
        await test_chat_hr_benefits(client)
        await test_chat_it_vpn(client)
        await test_chat_it_incident(client)
        await test_chat_developer_deploy(client)
        await test_chat_analytics_bigquery(client)
        await test_chat_analytics_sales(client)

        print("\n\033[1;33m── Session & Memory ──\033[0m")
        await test_multiturn_session(client)

        print("\n\033[1;33m── BigQuery Analytics ──\033[0m")
        await test_open_incidents(client)
        await test_pending_pto(client)

        print("\n\033[1;33m── Long-Running Tasks ──\033[0m")
        await test_long_running_task(client)
        await test_task_cancellation(client)
        await test_task_list(client)

        print("\n\033[1;33m── Self-Scheduling ──\033[0m")
        await test_self_scheduling(client)

        print("\n\033[1;33m── Google Workspace ──\033[0m")
        await test_workspace_gmail(client)
        await test_workspace_calendar(client)
        await test_workspace_drive(client)

    # ── Summary ────────────────────────────────────────────────────────────────
    passed = sum(1 for r in results if r.passed)
    failed = len(results) - passed
    total_time = sum(r.duration_s for r in results)

    print(f"\n{'='*60}")
    print(f"\033[1mResults: {passed}/{len(results)} passed  |  {failed} failed  |  {total_time:.1f}s total\033[0m")

    if failed:
        print("\n\033[0;31mFailed tests:\033[0m")
        for r in results:
            if not r.passed:
                print(f"  ✗  {r.name}: {r.detail}")
    else:
        print("\033[0;32mAll tests passed!\033[0m")

    print()
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    asyncio.run(main())
