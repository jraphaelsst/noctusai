"""Shared HTTP plumbing for Google Drive v3 calls.

Both ``GoogleDriveAdapter`` (service-account) and
``GoogleDriveOAuthAdapter`` (user-consent) call these helpers,
passing in their authenticated ``service`` instance.
"""
from __future__ import annotations

from typing import Any

from app.services.drive_api.mappers import FILE_FIELDS, LIST_FIELDS


def files_list(
    service: Any,
    *,
    q: str,
    page_size: int,
    order_by: str,
    page_token: str | None = None,
    include_team_drives: bool = True,
) -> dict[str, Any]:
    kwargs = {
        "q": q,
        "pageSize": page_size,
        "orderBy": order_by,
        "fields": LIST_FIELDS,
        "spaces": "drive",
    }
    if page_token:
        kwargs["pageToken"] = page_token
    if include_team_drives:
        kwargs["includeItemsFromAllDrives"] = True
        kwargs["supportsAllDrives"] = True
        kwargs["corpora"] = "allDrives"
    return service.files().list(**kwargs).execute()


def files_get(service: Any, file_id: str) -> dict[str, Any] | None:
    from googleapiclient.errors import HttpError

    try:
        return (
            service.files()
            .get(fileId=file_id, fields=FILE_FIELDS, supportsAllDrives=True)
            .execute()
        )
    except HttpError as exc:
        if exc.resp.status == 404:
            return None
        raise


def files_export(service: Any, file_id: str, *, mime_type: str) -> bytes:
    """Export a Google-native file (Sheets/Docs/Slides) to a downloadable
    format. Use ``text/csv`` for Sheets, ``text/plain`` for Docs/Slides.
    """
    return service.files().export(fileId=file_id, mimeType=mime_type).execute()


def files_get_media(service: Any, file_id: str) -> bytes:
    """Download the raw bytes of a non-Google-native file (PDF, plain
    text, XLSX, etc.). Google-native files (Sheets/Docs/Slides) can't
    be downloaded this way — use ``files_export`` instead.
    """
    from googleapiclient.http import MediaIoBaseDownload
    from io import BytesIO

    request = service.files().get_media(fileId=file_id, supportsAllDrives=True)
    buffer = BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        _status, done = downloader.next_chunk()
    return buffer.getvalue()
