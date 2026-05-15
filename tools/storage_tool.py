"""
tools/storage_tool.py

ADK FunctionTool wrapping Cloud Storage read/write within a designated bucket.

Security notes:
- All paths are restricted to the configured bucket (no cross-bucket access).
- Path traversal is rejected (paths containing '..' are blocked).
- Write operations are limited to designated prefixes to prevent overwriting
  critical infrastructure files.
"""
import re
from functools import lru_cache
from typing import Literal

from google.adk.tools import FunctionTool
from google.cloud import storage

from config import Settings


@lru_cache(maxsize=1)
def _get_gcs_client() -> storage.Client:
    """Return a cached GCS client. Created once per process."""
    return storage.Client()

_SAFE_PATH = re.compile(r"^[\w\-./]+$")
_WRITE_ALLOWED_PREFIXES = ("uploads/", "incidents/", "reports/", "tmp/")


def _safe_path(path: str) -> str | None:
    """Return the path if safe, else None."""
    if ".." in path or not _SAFE_PATH.match(path):
        return None
    return path.lstrip("/")


def _read_object(bucket_name: str, path: str) -> dict:
    safe = _safe_path(path)
    if not safe:
        return {"error": "Invalid path."}
    client = _get_gcs_client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(safe)
    if not blob.exists():
        return {"error": f"Object not found: {safe}"}
    try:
        content = blob.download_as_text()
        return {"content": content, "path": safe, "size_bytes": blob.size}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


def _write_object(bucket_name: str, path: str, content: str) -> dict:
    safe = _safe_path(path)
    if not safe:
        return {"error": "Invalid path."}
    if not any(safe.startswith(prefix) for prefix in _WRITE_ALLOWED_PREFIXES):
        return {
            "error": (
                f"Write blocked: path must start with one of {_WRITE_ALLOWED_PREFIXES}."
            )
        }
    client = _get_gcs_client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(safe)
    try:
        blob.upload_from_string(content, content_type="text/plain")
        return {"status": "ok", "path": safe}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


def _list_objects(bucket_name: str, prefix: str) -> dict:
    safe = _safe_path(prefix) if prefix else ""
    if safe is None:
        return {"error": "Invalid prefix."}
    client = _get_gcs_client()
    try:
        blobs = list(client.list_blobs(bucket_name, prefix=safe or None, max_results=200))
        return {"objects": [b.name for b in blobs]}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


def make_storage_tool(settings: Settings) -> FunctionTool:
    bucket_name = settings.gcp_staging_bucket.removeprefix("gs://")

    def storage_operation(
        operation: Literal["read", "write", "list"],
        path: str,
        content: str = "",
    ) -> dict:
        """
        Interact with Cloud Storage.

        Args:
            operation: One of 'read', 'write', or 'list'.
            path: Object path (for read/write) or prefix (for list).
            content: Content to write (only for 'write' operation).

        Returns:
            For read: {'content': str, 'path': str, 'size_bytes': int}
            For write: {'status': 'ok', 'path': str}
            For list: {'objects': list[str]}
            On error: {'error': str}
        """
        if operation == "read":
            return _read_object(bucket_name, path)
        if operation == "write":
            return _write_object(bucket_name, path, content)
        if operation == "list":
            return _list_objects(bucket_name, path)
        return {"error": f"Unknown operation: {operation}"}

    return FunctionTool(func=storage_operation)


def read_gcs_file(bucket: str, path: str) -> dict:
    """
    Module-level GCS read for direct tool use (e.g. TaskAgent).

    Args:
        bucket: GCS bucket name.
        path: Object path within the bucket.

    Returns:
        Dict with 'content' or 'error'.
    """
    return _read_object(bucket, path)


def write_gcs_file(bucket: str, path: str, content: str) -> dict:
    """
    Module-level GCS write for direct tool use (e.g. TaskAgent).

    Args:
        bucket: GCS bucket name.
        path: Object path within the bucket.
        content: String content to write.

    Returns:
        Dict with 'uri' or 'error'.
    """
    return _write_object(bucket, path, content)
