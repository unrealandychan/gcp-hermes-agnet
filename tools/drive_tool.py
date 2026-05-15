"""
tools/drive_tool.py

Google Workspace Drive tools for the Hermes agent.

Allows agents to search, read, and list files on Google Drive using
domain-wide delegation.

Setup required
──────────────
Same service account + domain-wide delegation as gmail_tool.py.
Additional OAuth scopes:
  https://www.googleapis.com/auth/drive.readonly
"""
from __future__ import annotations

import logging
from functools import lru_cache

from google.adk.tools import FunctionTool

from config import get_settings

logger = logging.getLogger(__name__)

_DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

# MIME types that can be exported as plain text via the Export API
_EXPORTABLE_MIME_TEXT = {
    "application/vnd.google-apps.document": "text/plain",
    "application/vnd.google-apps.spreadsheet": "text/csv",
    "application/vnd.google-apps.presentation": "text/plain",
}

# Maximum text content characters to return (avoids context overflow)
_MAX_CONTENT_CHARS = 8000


@lru_cache(maxsize=8)
def _drive_service(impersonate_email: str):
    """Return a cached Drive API service for the given impersonated user."""
    from google.oauth2 import service_account  # noqa: PLC0415
    from googleapiclient.discovery import build  # noqa: PLC0415

    settings = get_settings()
    creds = service_account.Credentials.from_service_account_file(
        settings.workspace_credentials_path,
        scopes=_DRIVE_SCOPES,
    ).with_subject(impersonate_email)
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _get_service():
    settings = get_settings()
    email = settings.workspace_admin_email
    if not email:
        raise RuntimeError("WORKSPACE_ADMIN_EMAIL is not set.")
    if not settings.workspace_credentials_path:
        raise RuntimeError("WORKSPACE_CREDENTIALS_PATH is not set.")
    return _drive_service(email)


# ── Tool functions ─────────────────────────────────────────────────────────────


def search_drive_files(query: str, max_results: int = 10) -> dict:
    """
    Search for files in Google Drive.

    Args:
        query: Full-text or metadata query using Drive query syntax.
            Examples:
              "name contains 'Q3 report'"
              "mimeType='application/vnd.google-apps.document'"
              "fullText contains 'onboarding' and trashed=false"
              "'team-folder-id' in parents"
        max_results: Maximum number of results to return (1-50). Defaults to 10.

    Returns:
        dict with key "files": list of {id, name, mime_type, modified_time, web_link}
    """
    try:
        service = _get_service()
        max_results = max(1, min(50, max_results))
        resp = service.files().list(
            q=query,
            pageSize=max_results,
            fields="files(id,name,mimeType,modifiedTime,webViewLink,size)",
            orderBy="modifiedTime desc",
        ).execute()

        files = [
            {
                "id": f.get("id"),
                "name": f.get("name"),
                "mime_type": f.get("mimeType"),
                "modified_time": f.get("modifiedTime"),
                "web_link": f.get("webViewLink"),
                "size_bytes": f.get("size"),
            }
            for f in resp.get("files", [])
        ]
        return {"files": files, "count": len(files)}
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to search Drive files.")
        return {"files": [], "error": str(exc)}


def read_drive_file(file_id: str) -> dict:
    """
    Read the text content of a Google Drive file.

    Supports Google Docs, Sheets (as CSV), Slides (as text), and plain-text files.
    Returns the first 8,000 characters of content.

    Args:
        file_id: The Drive file ID (from search_drive_files results).

    Returns:
        dict with keys: id, name, mime_type, content (text), truncated (bool)
    """
    try:
        service = _get_service()
        meta = service.files().get(
            fileId=file_id, fields="id,name,mimeType"
        ).execute()
        mime = meta.get("mimeType", "")
        name = meta.get("name", file_id)

        if mime in _EXPORTABLE_MIME_TEXT:
            export_mime = _EXPORTABLE_MIME_TEXT[mime]
            raw = service.files().export(
                fileId=file_id, mimeType=export_mime
            ).execute()
            content = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
        elif mime.startswith("text/"):
            # Plain text files: download directly
            raw = service.files().get_media(fileId=file_id).execute()
            content = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
        else:
            return {
                "id": file_id,
                "name": name,
                "mime_type": mime,
                "content": None,
                "message": f"File type '{mime}' is not readable as text.",
            }

        truncated = len(content) > _MAX_CONTENT_CHARS
        return {
            "id": file_id,
            "name": name,
            "mime_type": mime,
            "content": content[:_MAX_CONTENT_CHARS],
            "truncated": truncated,
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to read Drive file %s.", file_id)
        return {"error": str(exc)}


def list_drive_folder(folder_id: str, max_results: int = 20) -> dict:
    """
    List the files inside a Google Drive folder.

    Args:
        folder_id: The Drive folder ID. Use "root" for My Drive.
        max_results: Maximum number of files to return (1-50). Defaults to 20.

    Returns:
        dict with key "files": list of {id, name, mime_type, modified_time, web_link}
    """
    try:
        service = _get_service()
        max_results = max(1, min(50, max_results))
        resp = service.files().list(
            q=f"'{folder_id}' in parents and trashed=false",
            pageSize=max_results,
            fields="files(id,name,mimeType,modifiedTime,webViewLink,size)",
            orderBy="name",
        ).execute()

        files = [
            {
                "id": f.get("id"),
                "name": f.get("name"),
                "mime_type": f.get("mimeType"),
                "modified_time": f.get("modifiedTime"),
                "web_link": f.get("webViewLink"),
                "size_bytes": f.get("size"),
            }
            for f in resp.get("files", [])
        ]
        return {"files": files, "count": len(files), "folder_id": folder_id}
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to list Drive folder %s.", folder_id)
        return {"files": [], "error": str(exc)}


# ── ADK FunctionTool wrappers ──────────────────────────────────────────────────

search_drive_tool = FunctionTool(search_drive_files)
read_drive_tool = FunctionTool(read_drive_file)
list_drive_folder_tool = FunctionTool(list_drive_folder)
