"""Real Drive downloader backed by `gdown` (public "anyone-with-link" files).

This is the step-1 adapter. It satisfies the same `DriveDownloader` Protocol as
the seed's `RealDriveDownloader`, so the pipeline is unaffected when noc swaps in
the Drive v3 API path (the user already has a Google API key for that upgrade).

`gdown` is lazy-imported so tests / the `--fake` path don't require it.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from app.integrations.google_drive.mappers import parse_drive_url
from app.integrations.google_drive.types import DownloadedFile, DriveFile
from app.logging_config import get_logger

logger = get_logger(__name__)


class GdownDriveDownloader:
    """Download public Drive files/folders via gdown."""

    async def get_metadata(self, file_id: str) -> DriveFile | None:
        # gdown has no metadata-only call; the seed's Drive v3 adapter does.
        # Returning None is honest — callers that need metadata use download().
        return None

    async def download(self, file_id: str, dest: Path) -> DriveFile:
        import gdown  # lazy

        dest.parent.mkdir(parents=True, exist_ok=True)
        url = f"https://drive.google.com/uc?id={file_id}"
        logger.info("gdown download %s → %s", file_id, dest)
        out = await asyncio.to_thread(
            gdown.download, url, str(dest), quiet=False, fuzzy=True
        )
        if out is None or not dest.exists():
            raise FileNotFoundError(
                f"gdown failed for {file_id} — is the file shared 'anyone with the link'?"
            )
        return _meta_from_disk(dest, file_id)

    async def download_folder(
        self, folder_url_or_id: str, dest_dir: Path
    ) -> list[DownloadedFile]:
        import gdown  # lazy

        dest_dir.mkdir(parents=True, exist_ok=True)
        folder_id = parse_drive_url(folder_url_or_id)
        url = f"https://drive.google.com/drive/folders/{folder_id}"
        logger.info("gdown download_folder %s → %s", folder_id, dest_dir)
        paths = await asyncio.to_thread(
            gdown.download_folder,
            url,
            output=str(dest_dir),
            quiet=False,
            use_cookies=False,
        )
        if not paths:
            raise FileNotFoundError(
                f"gdown returned no files for folder {folder_id} — "
                "check the share setting is 'anyone with the link'."
            )
        return [
            DownloadedFile(path=Path(p), file=_meta_from_disk(Path(p), folder_id))
            for p in paths
        ]

    async def list_folder(self, folder_url_or_id: str) -> list[DriveFile]:
        raise NotImplementedError(
            "gdown cannot list a folder without downloading it. "
            "Set DRIVE_BACKEND=api or DRIVE_BACKEND=oauth to use Drive v3 listing."
        )

    # gdown is download-only; the write surface needs the Drive v3 OAuth backend.
    async def list_children(self, folder_id: str) -> list[DriveFile]:
        raise NotImplementedError("gdown is read-only; use DRIVE_BACKEND=oauth.")

    async def create_folder(self, name: str, parent_id: str) -> DriveFile:
        raise NotImplementedError("gdown is read-only; use DRIVE_BACKEND=oauth.")

    async def upload_file(
        self,
        local_path: Path,
        parent_id: str,
        *,
        name: str | None = None,
        mime_type: str | None = None,
    ) -> DriveFile:
        raise NotImplementedError("gdown is read-only; use DRIVE_BACKEND=oauth.")


def _meta_from_disk(path: Path, source_id: str) -> DriveFile:
    """Build DriveFile metadata from an on-disk file (gdown gives us no Drive id)."""
    return DriveFile(
        id=source_id,
        name=path.name,
        size_bytes=path.stat().st_size if path.exists() else None,
    )


__all__ = ["GdownDriveDownloader"]
