"""
tools/calendar_tool.py

Google Workspace Calendar tools for the Hermes agent.

Allows agents to create events, list upcoming events, and check attendee
availability via Google Calendar API using domain-wide delegation.

Setup required
──────────────
Same service account + domain-wide delegation as gmail_tool.py.
Additional OAuth scope:
  https://www.googleapis.com/auth/calendar
"""
from __future__ import annotations

import logging
from functools import lru_cache

from google.adk.tools import FunctionTool

from config import get_settings

logger = logging.getLogger(__name__)

_CALENDAR_SCOPES = ["https://www.googleapis.com/auth/calendar"]


@lru_cache(maxsize=8)
def _calendar_service(impersonate_email: str):
    """Return a cached Calendar API service for the given impersonated user."""
    from google.oauth2 import service_account  # noqa: PLC0415
    from googleapiclient.discovery import build  # noqa: PLC0415

    settings = get_settings()
    creds = service_account.Credentials.from_service_account_file(
        settings.workspace_credentials_path,
        scopes=_CALENDAR_SCOPES,
    ).with_subject(impersonate_email)
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def _get_service():
    settings = get_settings()
    email = settings.workspace_admin_email
    if not email:
        raise RuntimeError("WORKSPACE_ADMIN_EMAIL is not set.")
    if not settings.workspace_credentials_path:
        raise RuntimeError("WORKSPACE_CREDENTIALS_PATH is not set.")
    return _calendar_service(email)


# ── Tool functions ─────────────────────────────────────────────────────────────


def create_calendar_event(
    summary: str,
    start_datetime: str,
    end_datetime: str,
    attendees: str,
    description: str = "",
    location: str = "",
    timezone: str = "UTC",
) -> dict:
    """
    Create a Google Calendar event and invite attendees.

    Args:
        summary: Event title.
        start_datetime: Start time in ISO 8601 format: "2025-08-15T10:00:00".
        end_datetime: End time in ISO 8601 format:   "2025-08-15T11:00:00".
        attendees: Comma-separated list of attendee email addresses.
        description: Optional description / agenda for the event.
        location: Optional meeting location or video link.
        timezone: IANA timezone for the event. Defaults to "UTC".
            Examples: "America/New_York", "Asia/Bangkok", "Europe/London"

    Returns:
        dict with keys: status, event_id, event_link, message
    """
    try:
        service = _get_service()
        attendee_list = [
            {"email": e.strip()} for e in attendees.split(",") if e.strip()
        ]
        event_body = {
            "summary": summary,
            "description": description,
            "location": location,
            "start": {"dateTime": start_datetime, "timeZone": timezone},
            "end": {"dateTime": end_datetime, "timeZone": timezone},
            "attendees": attendee_list,
            "reminders": {"useDefault": True},
        }
        result = service.events().insert(
            calendarId="primary",
            body=event_body,
            sendUpdates="all",
        ).execute()
        return {
            "status": "created",
            "event_id": result.get("id"),
            "event_link": result.get("htmlLink"),
            "message": f"Event '{summary}' created from {start_datetime} to {end_datetime} ({timezone}).",
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to create calendar event '%s'.", summary)
        return {"status": "error", "message": str(exc)}


def list_calendar_events(
    start_date: str,
    end_date: str,
    max_results: int = 10,
) -> dict:
    """
    List calendar events in a date range.

    Args:
        start_date: Start of range in ISO 8601 date format: "2025-08-01".
        end_date: End of range in ISO 8601 date format: "2025-08-31".
        max_results: Maximum number of events to return (1-50). Defaults to 10.

    Returns:
        dict with key "events": list of {id, summary, start, end, attendees, location}
    """
    try:
        service = _get_service()
        max_results = max(1, min(50, max_results))
        resp = service.events().list(
            calendarId="primary",
            timeMin=f"{start_date}T00:00:00Z",
            timeMax=f"{end_date}T23:59:59Z",
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime",
        ).execute()

        events = []
        for e in resp.get("items", []):
            events.append({
                "id": e.get("id"),
                "summary": e.get("summary", ""),
                "start": e.get("start", {}).get("dateTime") or e.get("start", {}).get("date"),
                "end": e.get("end", {}).get("dateTime") or e.get("end", {}).get("date"),
                "location": e.get("location", ""),
                "attendees": [a.get("email") for a in e.get("attendees", [])],
            })
        return {"events": events, "count": len(events)}
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to list calendar events.")
        return {"events": [], "error": str(exc)}


def check_availability(
    attendees: str,
    start_datetime: str,
    end_datetime: str,
    timezone: str = "UTC",
) -> dict:
    """
    Check whether a set of attendees are free during a time slot.

    Args:
        attendees: Comma-separated list of attendee email addresses.
        start_datetime: Proposed start time: "2025-08-15T10:00:00".
        end_datetime: Proposed end time: "2025-08-15T11:00:00".
        timezone: IANA timezone for the window. Defaults to "UTC".

    Returns:
        dict with key "availability": list of {email, busy_periods, is_free}
    """
    try:
        service = _get_service()
        emails = [e.strip() for e in attendees.split(",") if e.strip()]
        body = {
            "timeMin": f"{start_datetime}+00:00" if "+" not in start_datetime else start_datetime,
            "timeMax": f"{end_datetime}+00:00" if "+" not in end_datetime else end_datetime,
            "timeZone": timezone,
            "items": [{"id": email} for email in emails],
        }
        resp = service.freebusy().query(body=body).execute()

        availability = []
        for email in emails:
            calendar_data = resp.get("calendars", {}).get(email, {})
            busy = calendar_data.get("busy", [])
            availability.append({
                "email": email,
                "busy_periods": busy,
                "is_free": len(busy) == 0,
            })
        return {"availability": availability, "time_slot": f"{start_datetime} — {end_datetime} ({timezone})"}
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to check availability.")
        return {"availability": [], "error": str(exc)}


# ── ADK FunctionTool wrappers ──────────────────────────────────────────────────

create_event_tool = FunctionTool(create_calendar_event)
list_events_tool = FunctionTool(list_calendar_events)
check_availability_tool = FunctionTool(check_availability)
