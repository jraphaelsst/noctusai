"""Real Google Drive v3 download client.

Wraps `googleapiclient.discovery.build("drive", "v3", ...)`. Streams
bytes via `MediaIoBaseDownload`, which chunks transparently — works for
small files (single chunk) and multi-GB files (many chunks) without
buffering the whole payload in memory.

API errors are logged at WARN before re-raising (no-silent-errors rule).
Sync googleapiclient calls are wrapped in `asyncio.to_thread(...)` so
this adapter satisfies the async Protocol contract without blocking the
event loop on network IO.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

from noctusai_lib.integrations.google_drive.types import DriveFile

logger = logging.getLogger(__name__)

_METADATA_FIELDS = "id,name,size,mimeType,md5Checksum"


class RealDriveDownloader:
    """googleapiclient-backed `DriveDownloader`.

    Pass either `api_key` (anyone-with-link public files) or
    `oauth_credentials` (a `google.oauth2.credentials.Credentials`-shaped
    object — required for private files). At least one is required."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        oauth_credentials: Any = None,
    ) -> None:
        if not api_key and oauth_credentials is None:
            raise ValueError(
                "RealDriveDownloader requires either api_key or oauth_credentials"
            )
        self._api_key = api_key
        self._creds = oauth_credentials

    def _build_service(self) -> Any:
        if self._creds is not None:
            return build(
                "drive", "v3", credentials=self._creds, cache_discovery=False
            )
        return build(
            "drive", "v3", developerKey=self._api_key, cache_discovery=False
        )

    async def get_metadata(self, file_id: str) -> DriveFile | None:
        return await asyncio.to_thread(self._get_metadata_sync, file_id)

    def _get_metadata_sync(self, file_id: str) -> DriveFile | None:
        try:
            service = self._build_service()
            res = (
                service.files()
                .get(fileId=file_id, fields=_METADATA_FIELDS)
                .execute()
            )
        except HttpError as e:
            if getattr(e, "resp", None) is not None and e.resp.status == 404:
                return None
            logger.warning(
                "google_drive.get_metadata_failed file_id=%s status=%s",
                file_id,
                getattr(e.resp, "status", "?"),
            )
            raise
        size_raw = res.get("size", "0")
        try:
            size_bytes = int(size_raw)
        except (TypeError, ValueError):
            logger.warning(
                "google_drive.size_parse_failed file_id=%s size=%r — defaulting to 0",
                file_id,
                size_raw,
            )
            size_bytes = 0
        return DriveFile(
            id=res["id"],
            name=res.get("name", ""),
            size_bytes=size_bytes,
            mime_type=res.get("mimeType", ""),
            md5_checksum=res.get("md5Checksum"),
        )

    async def download(self, file_id: str, dest: Path) -> DriveFile:
        return await asyncio.to_thread(self._download_sync, file_id, dest)

    def _download_sync(self, file_id: str, dest: Path) -> DriveFile:
        meta = self._get_metadata_sync(file_id)
        if meta is None:
            raise FileNotFoundError(
                f"drive file {file_id!r} not found or not accessible"
            )
        dest.parent.mkdir(parents=True, exist_ok=True)
        service = self._build_service()
        request = service.files().get_media(fileId=file_id)
        with dest.open("wb") as fh:
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            try:
                while not done:
                    _status, done = downloader.next_chunk()
            except HttpError as e:
                logger.warning(
                    "google_drive.download_failed file_id=%s status=%s",
                    file_id,
                    getattr(e.resp, "status", "?"),
                )
                raise
        return meta


__all__ = ["RealDriveDownloader"]
