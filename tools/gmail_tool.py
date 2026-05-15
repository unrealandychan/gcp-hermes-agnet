"""
tools/gmail_tool.py

Google Workspace Gmail tools for the Hermes agent.

Allows agents to send, search, and read Gmail messages on behalf of a
Google Workspace user via domain-wide delegation.

Setup required
──────────────
1. Create a service account in GCP with domain-wide delegation enabled.
2. In Google Workspace Admin → Security → API Controls → Domain-wide Delegation,
   add the service account client ID with the following OAuth scopes:
     https://www.googleapis.com/auth/gmail.readonly
     https://www.googleapis.com/auth/gmail.send
3. Set WORKSPACE_ADMIN_EMAIL and WORKSPACE_CREDENTIALS_PATH in .env.

The service account credentials JSON file path is set via WORKSPACE_CREDENTIALS_PATH.
"""
from __future__ import annotations

import base64
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from functools import lru_cache

from google.adk.tools import FunctionTool

from config import get_settings

logger = logging.getLogger(__name__)

_GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]


@lru_cache(maxsize=8)
def _gmail_service(impersonate_email: str):
    """Return a cached Gmail API service for the given impersonated user."""
    from google.oauth2 import service_account  # noqa: PLC0415
    from googleapiclient.discovery import build  # noqa: PLC0415

    settings = get_settings()
    creds = service_account.Credentials.from_service_account_file(
        settings.workspace_credentials_path,
        scopes=_GMAIL_SCOPES,
    ).with_subject(impersonate_email)
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def _get_service():
    settings = get_settings()
    email = settings.workspace_admin_email
    if not email:
        raise RuntimeError("WORKSPACE_ADMIN_EMAIL is not set.")
    if not settings.workspace_credentials_path:
        raise RuntimeError("WORKSPACE_CREDENTIALS_PATH is not set.")
    return _gmail_service(email)


# ── Tool functions ─────────────────────────────────────────────────────────────


def send_email(
    to: str,
    subject: str,
    body: str,
    cc: str = "",
    body_type: str = "plain",
) -> dict:
    """
    Send an email on behalf of the configured Workspace admin user.

    Args:
        to: Recipient email address (or comma-separated list).
        subject: Email subject line.
        body: Email body text.
        cc: Optional CC addresses (comma-separated).
        body_type: "plain" or "html". Defaults to "plain".

    Returns:
        dict with keys: status, message_id, message
    """
    try:
        service = _get_service()
        msg = MIMEMultipart("alternative")
        msg["To"] = to
        msg["Subject"] = subject
        if cc:
            msg["Cc"] = cc
        msg.attach(MIMEText(body, body_type))

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        result = service.users().messages().send(
            userId="me", body={"raw": raw}
        ).execute()
        return {
            "status": "sent",
            "message_id": result.get("id"),
            "message": f"Email sent to {to}: '{subject}'",
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to send email to %s", to)
        return {"status": "error", "message": str(exc)}


def search_emails(query: str, max_results: int = 10) -> dict:
    """
    Search emails in the Gmail inbox.

    Args:
        query: Gmail search query string (same syntax as Gmail search bar).
            Examples:
              "from:boss@company.com subject:report"
              "is:unread label:inbox newer_than:3d"
              "has:attachment filename:pdf"
        max_results: Maximum number of emails to return (1-50). Defaults to 10.

    Returns:
        dict with key "emails": list of {id, from, to, subject, date, snippet}
    """
    try:
        service = _get_service()
        max_results = max(1, min(50, max_results))
        resp = service.users().messages().list(
            userId="me", q=query, maxResults=max_results
        ).execute()

        messages = resp.get("messages", [])
        emails = []
        for m in messages:
            detail = service.users().messages().get(
                userId="me", id=m["id"], format="metadata",
                metadataHeaders=["From", "To", "Subject", "Date"],
            ).execute()
            headers = {h["name"]: h["value"] for h in detail.get("payload", {}).get("headers", [])}
            emails.append({
                "id": m["id"],
                "from": headers.get("From", ""),
                "to": headers.get("To", ""),
                "subject": headers.get("Subject", ""),
                "date": headers.get("Date", ""),
                "snippet": detail.get("snippet", ""),
            })
        return {"emails": emails, "count": len(emails)}
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to search emails.")
        return {"emails": [], "error": str(exc)}


def get_email(message_id: str) -> dict:
    """
    Read the full content of a specific email by its ID.

    Args:
        message_id: The Gmail message ID (from search_emails results).

    Returns:
        dict with keys: id, from, to, subject, date, body, attachments
    """
    try:
        service = _get_service()
        detail = service.users().messages().get(
            userId="me", id=message_id, format="full"
        ).execute()

        headers = {
            h["name"]: h["value"]
            for h in detail.get("payload", {}).get("headers", [])
        }

        body_text = ""
        attachments = []
        payload = detail.get("payload", {})

        def _extract_body(part):
            nonlocal body_text
            mime = part.get("mimeType", "")
            if mime == "text/plain" and "data" in part.get("body", {}):
                body_text += base64.urlsafe_b64decode(
                    part["body"]["data"] + "=="
                ).decode("utf-8", errors="replace")
            elif part.get("filename"):
                attachments.append({
                    "filename": part["filename"],
                    "mime_type": mime,
                    "attachment_id": part.get("body", {}).get("attachmentId", ""),
                })
            for sub in part.get("parts", []):
                _extract_body(sub)

        _extract_body(payload)

        return {
            "id": message_id,
            "from": headers.get("From", ""),
            "to": headers.get("To", ""),
            "subject": headers.get("Subject", ""),
            "date": headers.get("Date", ""),
            "body": body_text[:4000],  # cap to avoid context overflow
            "attachments": attachments,
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to get email %s", message_id)
        return {"error": str(exc)}


# ── ADK FunctionTool wrappers ──────────────────────────────────────────────────

send_email_tool = FunctionTool(send_email)
search_emails_tool = FunctionTool(search_emails)
get_email_tool = FunctionTool(get_email)
