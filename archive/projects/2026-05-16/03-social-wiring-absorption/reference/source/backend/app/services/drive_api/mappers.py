"""Drive API v3 response body → DriveFile mapper.

Centralized so service-account + OAuth-user adapters return
identical dataclasses regardless of which Google client built them.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.services.drive_api.types import DriveFile


FOLDER_MIME = "application/vnd.google-apps.folder"

# Standard fields we ask for from drive.files.list and files.get. Keeps
# request size predictable and matches the DriveFile schema.
FILE_FIELDS = (
    "id,name,mimeType,size,modifiedTime,webViewLink,iconLink,parents,"
    "owners(emailAddress,displayName),trashed"
)
LIST_FIELDS = f"nextPageToken,files({FILE_FIELDS})"


def file_body_to_drive_file(body: dict[str, Any]) -> DriveFile:
    mime_type = body.get("mimeType", "")
    return DriveFile(
        file_id=body["id"],
        name=body.get("name", ""),
        mime_type=mime_type,
        size_bytes=_parse_int(body.get("size")),
        modified_at=_parse_iso(body.get("modifiedTime")),
        web_view_link=body.get("webViewLink"),
        icon_link=body.get("iconLink"),
        parents=list(body.get("parents", []) or []),
        owners=[
            (o.get("emailAddress") or o.get("displayName") or "")
            for o in (body.get("owners") or [])
        ],
        is_folder=mime_type == FOLDER_MIME,
        raw=body,
    )


def _parse_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_iso(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def build_search_query(
    *,
    query: str | None,
    mime_type: str | None,
    folder_id: str | None,
    include_trashed: bool = False,
) -> str:
    """Compose a Drive ``q`` parameter from the chatbot's high-level
    inputs. Drive's query language is a small DSL — see
    https://developers.google.com/drive/api/guides/search-files.
    """
    parts: list[str] = []
    if not include_trashed:
        parts.append("trashed = false")
    if mime_type:
        # Match exact mime type. Folders use a special mime.
        parts.append(f"mimeType = '{_escape(mime_type)}'")
    if folder_id:
        parts.append(f"'{_escape(folder_id)}' in parents")
    if query:
        # Use both name CONTAINS + fullText CONTAINS so the chatbot's
        # "search for X" matches filenames AND document body content.
        # Drive does an OR if we group them — but the API doesn't
        # support grouping inside a single clause, so we use the
        # most-common combination.
        escaped = _escape(query)
        parts.append(f"(name contains '{escaped}' or fullText contains '{escaped}')")
    return " and ".join(parts) if parts else ""


def _escape(value: str) -> str:
    """Drive's query language uses single-quote string literals; the
    only escape needed is a doubled single quote for embedded quotes."""
    return value.replace("'", "\\'")


# ─── Content rendering helpers ───────────────────────────────────────

GOOGLE_NATIVE_PREFIX = "application/vnd.google-apps."
SHEETS_MIME = "application/vnd.google-apps.spreadsheet"
DOC_MIME = "application/vnd.google-apps.document"
SLIDES_MIME = "application/vnd.google-apps.presentation"

# How to export each Google-native mime to a text-readable format.
EXPORT_MIME = {
    SHEETS_MIME: "text/csv",
    DOC_MIME: "text/plain",
    SLIDES_MIME: "text/plain",
}

# Mime types we can render natively if we get the raw bytes.
TEXTUAL_MIMES = {
    "text/plain",
    "text/csv",
    "text/markdown",
    "application/json",
    "application/xml",
    "text/xml",
}


def rendered_label_for_mime(mime: str) -> str:
    if mime == SHEETS_MIME:
        return "csv"
    if mime in {DOC_MIME, SLIDES_MIME}:
        return "text"
    if mime == "application/pdf":
        return "pdf-text"
    if mime in TEXTUAL_MIMES:
        return "text"
    return "binary"


def render_bytes(raw: bytes, *, mime: str, max_bytes: int) -> tuple[str, bool]:
    """Convert raw bytes (already exported / downloaded) into a text
    representation the chatbot can reason about.

    Returns (text, is_truncated).
    """
    if mime == "application/pdf":
        try:
            from app.services.media_service import _extract_pdf_text

            text = _extract_pdf_text(raw) or ""
        except Exception:
            text = ""
    elif mime in TEXTUAL_MIMES or mime == SHEETS_MIME or mime in {DOC_MIME, SLIDES_MIME}:
        try:
            text = raw.decode("utf-8", errors="replace")
        except Exception:
            text = ""
    else:
        # Binary / unsupported — return an empty text but the caller can
        # surface size/mime to the user.
        return ("", False)
    if len(text) > max_bytes:
        return (text[:max_bytes], True)
    return (text, False)
