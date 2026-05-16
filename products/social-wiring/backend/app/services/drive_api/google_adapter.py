"""Google Drive v3 adapter using service-account auth.

Service accounts can ONLY access files/folders that have been
EXPLICITLY shared with the SA's email. This is a Google constraint,
not ours — for a personal-Gmail Drive, the user has to right-click
the folder → Share → add the SA email.

The Drive API surface is read-only here (search/list/get). Writes
happen via the existing upload pipeline (gdrive_service +
upload_service), not via this adapter.

Reference: https://developers.google.com/drive/api/v3/reference
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from app.services.drive_api import _drive_api
from app.services.drive_api.mappers import (
    EXPORT_MIME,
    GOOGLE_NATIVE_PREFIX,
    build_search_query,
    file_body_to_drive_file,
    render_bytes,
    rendered_label_for_mime,
)
from app.services.drive_api.types import DriveFile, DriveFileContent, DriveSearchResult

if TYPE_CHECKING:
    from googleapiclient.discovery import Resource


# Read-only scope is enough — the chatbot never writes via this
# adapter. If/when write tools land, add drive.file (per-file) or
# drive (full).
DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


class GoogleDriveAdapter:
    """Service-account Drive adapter (read-only)."""

    supports_full_user_drive = False

    def __init__(self, service_account_file: str):
        self._service_account_file = service_account_file
        self._service: "Resource | None" = None

    def _get_service(self) -> "Resource":
        if self._service is None:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build

            credentials = service_account.Credentials.from_service_account_file(
                self._service_account_file,
                scopes=DRIVE_SCOPES,
            )
            self._service = build(
                "drive",
                "v3",
                credentials=credentials,
                cache_discovery=False,
            )
        return self._service

    def search(
        self,
        *,
        query: str | None = None,
        mime_type: str | None = None,
        folder_id: str | None = None,
        page_size: int = 20,
        order_by: str = "modifiedTime desc",
    ) -> DriveSearchResult:
        q = build_search_query(query=query, mime_type=mime_type, folder_id=folder_id)
        response = _drive_api.files_list(
            self._get_service(),
            q=q,
            page_size=page_size,
            order_by=order_by,
        )
        files = [file_body_to_drive_file(b) for b in response.get("files", [])]
        return DriveSearchResult(
            files=files,
            next_page_token=response.get("nextPageToken"),
            query_used=q,
        )

    def get_file(self, file_id: str) -> DriveFile | None:
        body = _drive_api.files_get(self._get_service(), file_id)
        return file_body_to_drive_file(body) if body else None

    def list_recent(self, *, page_size: int = 10) -> DriveSearchResult:
        return self.search(page_size=page_size)

    def read_content(
        self,
        file_id: str,
        *,
        max_bytes: int = 200_000,
    ) -> DriveFileContent | None:
        return _read_content_via(self._get_service(), file_id, max_bytes=max_bytes)


def _read_content_via(
    service,
    file_id: str,
    *,
    max_bytes: int,
) -> DriveFileContent | None:
    """Shared `read_content` implementation used by both
    GoogleDriveAdapter (service-account) and GoogleDriveOAuthAdapter
    (user). Picks export vs. get_media based on the file's mime type.
    """
    meta = _drive_api.files_get(service, file_id)
    if not meta:
        return None
    mime = meta.get("mimeType", "")
    name = meta.get("name", "")

    # Google-native types must use export; raw binary types use get_media.
    if mime in EXPORT_MIME:
        target = EXPORT_MIME[mime]
        raw = _drive_api.files_export(service, file_id, mime_type=target)
        text, truncated = render_bytes(raw, mime=mime, max_bytes=max_bytes)
        return DriveFileContent(
            file_id=file_id,
            name=name,
            mime_type=mime,
            rendered_as=rendered_label_for_mime(mime),
            text=text,
            bytes_read=len(raw),
            is_truncated=truncated,
            raw_mime=target,
        )
    if mime.startswith(GOOGLE_NATIVE_PREFIX):
        # Google-native type without an export mapping (Forms, Maps, etc.)
        return DriveFileContent(
            file_id=file_id,
            name=name,
            mime_type=mime,
            rendered_as="binary",
            text="",
            bytes_read=0,
            is_truncated=False,
            raw_mime=mime,
        )
    # Non-native — download bytes and render per mime.
    raw = _drive_api.files_get_media(service, file_id)
    text, truncated = render_bytes(raw, mime=mime, max_bytes=max_bytes)
    return DriveFileContent(
        file_id=file_id,
        name=name,
        mime_type=mime,
        rendered_as=rendered_label_for_mime(mime),
        text=text,
        bytes_read=len(raw),
        is_truncated=truncated,
        raw_mime=mime,
    )
