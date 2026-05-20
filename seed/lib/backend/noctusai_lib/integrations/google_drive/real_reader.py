"""Real Google Drive v3 read/inspection client.

Wraps `googleapiclient.discovery.build("drive", "v3", ...)`. Mirrors
the workspace `drive_api/google_adapter.py` + `oauth_adapter.py`
(`SESSION-NOTES_drive-api-2026-05-13.md`). Sync googleapiclient calls
run in `asyncio.to_thread(...)` to satisfy the async Protocol without
blocking the loop. API errors are logged at WARN before re-raising
(no-silent-errors rule). 404 → `None` (Drive returns 404 for both
non-existent AND inaccessible — by design, to avoid leaking
existence).

Google-native exports (Drive `files.export`):
- Sheets → `text/csv`        → `rendered_as="text/csv"`
- Docs   → `text/plain`      → `rendered_as="text/plain"`
- Slides → `text/plain`      → `rendered_as="text/plain"`
Binary/other types stream via `files.get_media`:
- TXT/CSV/JSON               → `rendered_as="passthrough"`
- PDF/DOCX/image/video       → `rendered_as="binary"` (defer
  extraction to the `media` seam — this module stays PyMuPDF-free).

Enriched (2026-05-19, `social-wiring-google-seed-consume` Phase 6a-drive):
list/get field projections now include `parents`, `owners`,
`iconLink`; `_row_to_hit` flattens owners to a `list[str]` of
emails-or-display-names and preserves the full Drive row body in
`DriveSearchHit.raw` (forward-compat escape hatch for consumers
needing fields the seed Protocol doesn't yet surface).
`include_team_drives=True` adds `includeItemsFromAllDrives` /
`supportsAllDrives` / `corpora=allDrives` (the absorbed product's
default — shared-drive members expect their files to be searchable).
`DriveFileContent.raw_mime` is set explicitly so consumers don't have
to derive it.
"""

from __future__ import annotations

import asyncio
import io
import logging
from typing import Any

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

from noctusai_lib.integrations.google_drive.reader_types import (
    DriveFileContent,
    DriveSearchHit,
    DriveSearchResult,
)

logger = logging.getLogger(__name__)

_LIST_FIELDS = (
    "nextPageToken,files(id,name,mimeType,modifiedTime,size,"
    "webViewLink,iconLink,parents,"
    "owners(emailAddress,displayName),"
    "capabilities)"
)
_GET_FIELDS = (
    "id,name,mimeType,modifiedTime,size,webViewLink,iconLink,parents,"
    "owners(emailAddress,displayName),capabilities"
)

# Google-native MIME → (export MIME, rendered_as)
_EXPORT_MIME: dict[str, tuple[str, str]] = {
    "application/vnd.google-apps.spreadsheet": ("text/csv", "text/csv"),
    "application/vnd.google-apps.document": ("text/plain", "text/plain"),
    "application/vnd.google-apps.presentation": ("text/plain", "text/plain"),
}
# Non-native MIME prefixes that are safe to treat as UTF-8 passthrough.
_TEXT_PASSTHROUGH = (
    "text/",
    "application/json",
    "application/csv",
)


def _flatten_owners(owners_raw: Any) -> list[str]:
    """Flatten Drive `owners[]` to a list of email-or-displayname strings.

    Drive returns each owner as `{"emailAddress": "...", "displayName": "..."}`;
    we prefer email (more stable / dedup-able), fall back to display
    name, drop empties. Anyone-with-link API-key auth doesn't return
    owners — empty list."""
    out: list[str] = []
    if not owners_raw:
        return out
    for owner in owners_raw:
        if not isinstance(owner, dict):
            continue
        label = owner.get("emailAddress") or owner.get("displayName") or ""
        if label:
            out.append(label)
    return out


def _row_to_hit(row: dict[str, Any]) -> DriveSearchHit:
    size_raw = row.get("size")
    try:
        size_bytes = int(size_raw) if size_raw is not None else None
    except (TypeError, ValueError):
        size_bytes = None
    return DriveSearchHit(
        id=row["id"],
        name=row.get("name", ""),
        mime_type=row.get("mimeType", ""),
        modified_time=row.get("modifiedTime"),
        size_bytes=size_bytes,
        web_view_link=row.get("webViewLink"),
        capabilities=row.get("capabilities", {}) or {},
        parents=list(row.get("parents", []) or []),
        owners=_flatten_owners(row.get("owners")),
        icon_link=row.get("iconLink"),
        raw=dict(row),
    )


class RealDriveReader:
    """googleapiclient-backed `DriveReader`.

    Pass either `api_key` (anyone-with-link public files) OR
    `oauth_credentials` (a `google.oauth2.credentials.Credentials`- or
    `service_account.Credentials`-shaped object — for private files /
    the share-with-SA path). At least one is required."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        oauth_credentials: Any = None,
        include_team_drives: bool = True,
    ) -> None:
        if not api_key and oauth_credentials is None:
            raise ValueError(
                "RealDriveReader requires either api_key or oauth_credentials"
            )
        self._api_key = api_key
        self._creds = oauth_credentials
        self._include_team_drives = include_team_drives

    def _service(self) -> Any:
        if self._creds is not None:
            return build(
                "drive", "v3", credentials=self._creds, cache_discovery=False
            )
        return build(
            "drive", "v3", developerKey=self._api_key, cache_discovery=False
        )

    # ─── search / list ────────────────────────────────────────────────

    async def search(
        self,
        query: str,
        *,
        mime_type: str | None = None,
        folder_id: str | None = None,
        page_size: int = 20,
    ) -> DriveSearchResult:
        return await asyncio.to_thread(
            self._search_sync, query, mime_type, folder_id, page_size
        )

    def _build_q(
        self, query: str, mime_type: str | None, folder_id: str | None
    ) -> str:
        clauses: list[str] = ["trashed = false"]
        if query:
            safe = query.replace("'", "\\'")
            clauses.append(f"(name contains '{safe}' or fullText contains '{safe}')")
        if mime_type:
            clauses.append(f"mimeType = '{mime_type}'")
        if folder_id:
            clauses.append(f"'{folder_id}' in parents")
        return " and ".join(clauses)

    def _list_kwargs(
        self, query: str, mime_type: str | None, folder_id: str | None, page_size: int
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "q": self._build_q(query, mime_type, folder_id),
            "pageSize": page_size,
            "fields": _LIST_FIELDS,
            "orderBy": "modifiedTime desc",
        }
        if self._include_team_drives:
            kwargs["includeItemsFromAllDrives"] = True
            kwargs["supportsAllDrives"] = True
            kwargs["corpora"] = "allDrives"
            kwargs["spaces"] = "drive"
        return kwargs

    def _search_sync(
        self,
        query: str,
        mime_type: str | None,
        folder_id: str | None,
        page_size: int,
    ) -> DriveSearchResult:
        try:
            res = (
                self._service()
                .files()
                .list(**self._list_kwargs(query, mime_type, folder_id, page_size))
                .execute()
            )
        except HttpError as e:
            logger.warning(
                "google_drive.search_failed status=%s",
                getattr(getattr(e, "resp", None), "status", "?"),
            )
            raise
        hits = [_row_to_hit(r) for r in res.get("files", [])]
        return DriveSearchResult(
            hits=hits, next_page_token=res.get("nextPageToken")
        )

    async def list_recent(self, *, page_size: int = 20) -> DriveSearchResult:
        return await asyncio.to_thread(self._search_sync, "", None, None, page_size)

    # ─── get_file ─────────────────────────────────────────────────────

    async def get_file(self, file_id: str) -> DriveSearchHit | None:
        return await asyncio.to_thread(self._get_file_sync, file_id)

    def _get_file_sync(self, file_id: str) -> DriveSearchHit | None:
        try:
            row = (
                self._service()
                .files()
                .get(
                    fileId=file_id,
                    fields=_GET_FIELDS,
                    supportsAllDrives=self._include_team_drives,
                )
                .execute()
            )
        except HttpError as e:
            if getattr(getattr(e, "resp", None), "status", None) == 404:
                return None
            logger.warning(
                "google_drive.get_file_failed file_id=%s status=%s",
                file_id,
                getattr(getattr(e, "resp", None), "status", "?"),
            )
            raise
        return _row_to_hit(row)

    # ─── read_file ────────────────────────────────────────────────────

    async def read_file(
        self, file_id: str, *, max_bytes: int = 200_000
    ) -> DriveFileContent | None:
        return await asyncio.to_thread(self._read_file_sync, file_id, max_bytes)

    def _read_file_sync(
        self, file_id: str, max_bytes: int
    ) -> DriveFileContent | None:
        meta = self._get_file_sync(file_id)
        if meta is None:
            return None
        service = self._service()
        export = _EXPORT_MIME.get(meta.mime_type)
        raw_mime: str
        try:
            if export is not None:
                export_mime, rendered_as = export
                raw_mime = export_mime
                request = service.files().export_media(
                    fileId=file_id, mimeType=export_mime
                )
            else:
                rendered_as = (
                    "passthrough"
                    if meta.mime_type.startswith(_TEXT_PASSTHROUGH)
                    else "binary"
                )
                raw_mime = meta.mime_type
                request = service.files().get_media(fileId=file_id)
            buf = io.BytesIO()
            downloader = MediaIoBaseDownload(buf, request)
            done = False
            while not done:
                _status, done = downloader.next_chunk()
        except HttpError as e:
            logger.warning(
                "google_drive.read_file_failed file_id=%s status=%s",
                file_id,
                getattr(getattr(e, "resp", None), "status", "?"),
            )
            raise
        raw = buf.getvalue()
        truncated = len(raw) > max_bytes
        return DriveFileContent(
            file_id=file_id,
            name=meta.name,
            mime_type=meta.mime_type,
            rendered_as=rendered_as,
            data=raw[:max_bytes],
            truncated=truncated,
            raw_mime=raw_mime,
        )


__all__ = ["RealDriveReader"]
