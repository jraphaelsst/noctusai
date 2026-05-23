"""Real Drive downloader backed by the Google Drive v3 API.

Mirrors `noctusai_lib.integrations.google_drive.RealDriveDownloader`
(`googleapiclient.discovery.build("drive", "v3", ...)` + `MediaIoBaseDownload`)
and adds `download_folder` — recursive `files.list` traversal that preserves the
folder structure on disk. On absorption this collapses to the seed's `DriveReader`
(list) + `RealDriveDownloader` (download).

**Auth (this matters for your case):** pass `api_key` for "anyone-with-link"
public files, OR `oauth_credentials` for files shared privately with your account
(a third-party folder shared *to you* is NOT reachable by an API key — Drive
returns 404). The Protocol is auth-agnostic; the factory routes.

`googleapiclient` is imported lazily so the fake/gdown paths and tests that inject
a `service` don't require it. Sync SDK calls run in `asyncio.to_thread`.
"""
from __future__ import annotations

import asyncio
import io
from pathlib import Path
from typing import Any, Callable, Optional

from app.integrations.google_drive.mappers import parse_drive_url
from app.integrations.google_drive.types import DownloadedFile, DriveFile
from app.logging_config import get_logger

logger = get_logger(__name__)

FOLDER_MIME = "application/vnd.google-apps.folder"
_GOOGLE_NATIVE_PREFIX = "application/vnd.google-apps."
_METADATA_FIELDS = "id,name,size,mimeType,md5Checksum"


class DriveError(RuntimeError):
    """A Drive operation failed."""


class DriveNotConfigured(DriveError):
    """No usable credentials (api_key / oauth_credentials) were provided."""


class DriveV3Downloader:
    """Google Drive v3 download client.

    `service` and `byte_fetcher` are injectable seams for tests (DI for the
    network boundary — no monkeypatching of our own code).
    """

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        oauth_credentials: Any = None,
        service: Any = None,
        byte_fetcher: Optional[Callable[[str], bytes]] = None,
        media_factory: Optional[Callable[[Path, Optional[str]], Any]] = None,
    ) -> None:
        self._api_key = api_key
        self._creds = oauth_credentials
        self._service = service
        self._byte_fetcher = byte_fetcher
        self._media_factory = media_factory

    # ── service ──────────────────────────────────────────────────────
    def _svc(self) -> Any:
        if self._service is None:
            self._service = self._build_service()
        return self._service

    def _build_service(self) -> Any:
        if not self._api_key and self._creds is None:
            raise DriveNotConfigured(
                "DriveV3Downloader needs api_key or oauth_credentials."
            )
        from googleapiclient.discovery import build  # lazy

        if self._creds is not None:
            return build("drive", "v3", credentials=self._creds, cache_discovery=False)
        return build("drive", "v3", developerKey=self._api_key, cache_discovery=False)

    # ── metadata ─────────────────────────────────────────────────────
    async def get_metadata(self, file_id: str) -> DriveFile | None:
        return await asyncio.to_thread(self._get_metadata_sync, file_id)

    def _get_metadata_sync(self, file_id: str) -> DriveFile | None:
        from googleapiclient.errors import HttpError  # lazy

        try:
            res = (
                self._svc()
                .files()
                .get(fileId=file_id, fields=_METADATA_FIELDS, supportsAllDrives=True)
                .execute()
            )
        except HttpError as e:
            if getattr(e, "resp", None) is not None and e.resp.status == 404:
                return None  # missing OR inaccessible (Drive conflates these)
            logger.warning(
                "drive.get_metadata failed id=%s status=%s",
                file_id, getattr(getattr(e, "resp", None), "status", "?"),
            )
            raise
        return _to_drive_file(res)

    # ── download ─────────────────────────────────────────────────────
    async def download(self, file_id: str, dest: Path) -> DriveFile:
        meta = await self.get_metadata(file_id)
        if meta is None:
            raise FileNotFoundError(f"drive file {file_id!r} not found or not accessible")
        await asyncio.to_thread(self._download_to, file_id, dest)
        return meta

    async def list_folders(
        self, *, parent: str = "root", shared_with_me: bool = False, limit: int = 10
    ) -> list[DriveFile]:
        """List folders at a Drive location (My Drive root, or Shared-with-me)."""
        return await asyncio.to_thread(
            self._list_folders_sync, parent, shared_with_me, limit
        )

    def _list_folders_sync(
        self, parent: str, shared_with_me: bool, limit: int
    ) -> list[DriveFile]:
        clauses = [f"mimeType = '{FOLDER_MIME}'", "trashed = false"]
        if shared_with_me:
            clauses.append("sharedWithMe = true")
        else:
            clauses.append(f"'{parent}' in parents")
        resp = (
            self._svc()
            .files()
            .list(
                q=" and ".join(clauses),
                fields=f"files({_METADATA_FIELDS})",
                pageSize=max(1, min(limit, 1000)),
                orderBy="name",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            )
            .execute()
        )
        return [_to_drive_file(f) for f in resp.get("files", [])]

    async def walk_tree(
        self, folder_url_or_id: str
    ) -> list[tuple[Path, bool, DriveFile]]:
        """Recursively walk a folder; return (relative_path, is_folder, file).

        Includes folders (as branches) and files (as leaves), ordered folders-first
        then alphabetically. Downloads nothing.
        """
        folder_id = parse_drive_url(folder_url_or_id)
        logger.info("drive: walking tree of folder %s", folder_id)
        try:
            return await asyncio.to_thread(self._walk_tree_sync, folder_id, Path())
        except DriveError:
            raise
        except Exception as e:  # enrich + re-raise (never silent)
            raise DriveError(
                f"Could not read Drive folder {folder_id!r}. Confirm it is shared "
                f"with your account and your credentials are valid. Original: {e}"
            ) from e

    def _walk_tree_sync(
        self, folder_id: str, rel: Path
    ) -> list[tuple[Path, bool, DriveFile]]:
        children: list[dict] = []
        token: str | None = None
        while True:
            resp = (
                self._svc()
                .files()
                .list(
                    q=f"'{folder_id}' in parents and trashed=false",
                    fields=f"nextPageToken, files({_METADATA_FIELDS})",
                    pageSize=1000,
                    pageToken=token,
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                )
                .execute()
            )
            children.extend(resp.get("files", []))
            token = resp.get("nextPageToken")
            if not token:
                break

        entries: list[tuple[Path, bool, DriveFile]] = []
        for f in sorted(
            children,
            key=lambda x: (x.get("mimeType") != FOLDER_MIME, x.get("name", "").lower()),
        ):
            df = _to_drive_file(f)
            is_folder = df.mime_type == FOLDER_MIME
            path = rel / df.name
            entries.append((path, is_folder, df))
            if is_folder:
                entries.extend(self._walk_tree_sync(df.id, path))
        return entries

    async def list_folder(self, folder_url_or_id: str) -> list[DriveFile]:
        folder_id = parse_drive_url(folder_url_or_id)
        logger.info("drive: listing folder %s (no download)", folder_id)
        try:
            walked = await asyncio.to_thread(self._walk_sync, folder_id, Path())
        except DriveError:
            raise
        except Exception as e:  # enrich + re-raise (never silent)
            raise DriveError(
                f"Could not list Drive folder {folder_id!r}. Confirm it is shared "
                f"with your account (or 'anyone with the link') and your credentials "
                f"are valid. Original error: {e}"
            ) from e
        return [df for df, _rel in walked]

    async def download_folder(
        self, folder_url_or_id: str, dest_dir: Path
    ) -> list[DownloadedFile]:
        folder_id = parse_drive_url(folder_url_or_id)
        logger.info("drive: listing folder %s", folder_id)
        try:
            walked = await asyncio.to_thread(self._walk_sync, folder_id, Path())
        except DriveError:
            raise
        except Exception as e:  # enrich + re-raise (never silent)
            raise DriveError(
                f"Could not list Drive folder {folder_id!r}. Confirm it is shared "
                f"with your account (or 'anyone with the link') and your credentials "
                f"are valid. Original error: {e}"
            ) from e

        out: list[DownloadedFile] = []
        for df, rel in walked:
            if _is_google_native(df.mime_type):
                logger.info("skip google-native file: %s", df.name)
                continue
            dest = dest_dir / rel / _safe_name(df.name)
            logger.info("drive: downloading %s → %s", df.name, dest)
            await asyncio.to_thread(self._download_to, df.id, dest)
            out.append(DownloadedFile(path=dest, file=df))

        if not out:
            logger.warning("no downloadable files found in folder %s", folder_id)
        return out

    # ── write (publish back to Drive) ────────────────────────────────
    async def list_children(self, folder_id: str) -> list[DriveFile]:
        """Direct children (files + folders) of one folder — non-recursive."""
        return await asyncio.to_thread(self._list_children_sync, parse_drive_url(folder_id))

    def _list_children_sync(self, folder_id: str) -> list[DriveFile]:
        out: list[DriveFile] = []
        token: str | None = None
        while True:
            resp = (
                self._svc()
                .files()
                .list(
                    q=f"'{folder_id}' in parents and trashed=false",
                    fields=f"nextPageToken, files({_METADATA_FIELDS})",
                    pageSize=1000,
                    pageToken=token,
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                )
                .execute()
            )
            out.extend(_to_drive_file(f) for f in resp.get("files", []))
            token = resp.get("nextPageToken")
            if not token:
                break
        return out

    async def create_folder(self, name: str, parent_id: str) -> DriveFile:
        return await asyncio.to_thread(self._create_folder_sync, name, parent_id)

    def _create_folder_sync(self, name: str, parent_id: str) -> DriveFile:
        body = {"name": name, "mimeType": FOLDER_MIME, "parents": [parent_id]}
        res = (
            self._svc()
            .files()
            .create(body=body, fields=_METADATA_FIELDS, supportsAllDrives=True)
            .execute()
        )
        logger.info("drive: created folder %s under %s", name, parent_id)
        return _to_drive_file(res)

    async def upload_file(
        self,
        local_path: Path,
        parent_id: str,
        *,
        name: str | None = None,
        mime_type: str | None = None,
    ) -> DriveFile:
        return await asyncio.to_thread(
            self._upload_file_sync, local_path, parent_id, name or local_path.name, mime_type
        )

    def _upload_file_sync(
        self, local_path: Path, parent_id: str, name: str, mime_type: str | None
    ) -> DriveFile:
        body = {"name": name, "parents": [parent_id]}
        media = self._make_media(local_path, mime_type)
        res = (
            self._svc()
            .files()
            .create(
                body=body,
                media_body=media,
                fields=_METADATA_FIELDS,
                supportsAllDrives=True,
            )
            .execute()
        )
        logger.info("drive: uploaded %s → folder %s", name, parent_id)
        return _to_drive_file(res)

    def _make_media(self, local_path: Path, mime_type: str | None) -> Any:
        if self._media_factory is not None:  # injected boundary for tests
            return self._media_factory(local_path, mime_type)
        from googleapiclient.http import MediaFileUpload  # lazy

        return MediaFileUpload(str(local_path), mimetype=mime_type, resumable=False)

    # ── internals ────────────────────────────────────────────────────
    def _walk_sync(self, folder_id: str, rel: Path) -> list[tuple[DriveFile, Path]]:
        out: list[tuple[DriveFile, Path]] = []
        token: str | None = None
        while True:
            resp = (
                self._svc()
                .files()
                .list(
                    q=f"'{folder_id}' in parents and trashed=false",
                    fields=f"nextPageToken, files({_METADATA_FIELDS})",
                    pageSize=1000,
                    pageToken=token,
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                )
                .execute()
            )
            for f in resp.get("files", []):
                df = _to_drive_file(f)
                if df.mime_type == FOLDER_MIME:
                    out.extend(self._walk_sync(df.id, rel / _safe_name(df.name)))
                else:
                    out.append((df, rel))
            token = resp.get("nextPageToken")
            if not token:
                break
        return out

    def _download_to(self, file_id: str, dest: Path) -> None:
        data = self._fetch_bytes(file_id)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)

    def _fetch_bytes(self, file_id: str) -> bytes:
        if self._byte_fetcher is not None:
            return self._byte_fetcher(file_id)
        from googleapiclient.http import MediaIoBaseDownload  # lazy

        request = self._svc().files().get_media(fileId=file_id, supportsAllDrives=True)
        buf = io.BytesIO()
        downloader = MediaIoBaseDownload(buf, request)
        done = False
        while not done:
            _status, done = downloader.next_chunk()
        return buf.getvalue()


# ── pure helpers ─────────────────────────────────────────────────────
def _to_drive_file(f: dict) -> DriveFile:
    size = f.get("size")
    try:
        size_bytes = int(size) if size is not None else None
    except (TypeError, ValueError):
        size_bytes = None
    return DriveFile(
        id=f["id"],
        name=f.get("name", ""),
        size_bytes=size_bytes,
        mime_type=f.get("mimeType"),
        md5_checksum=f.get("md5Checksum"),
    )


def _is_google_native(mime: str | None) -> bool:
    """Google-native docs (Docs/Sheets/Slides) need export, not get_media — skip."""
    return bool(mime) and mime.startswith(_GOOGLE_NATIVE_PREFIX) and mime != FOLDER_MIME


def _safe_name(name: str) -> str:
    return name.replace("/", "_").replace("\\", "_")


__all__ = ["DriveV3Downloader", "DriveError", "DriveNotConfigured", "FOLDER_MIME"]
