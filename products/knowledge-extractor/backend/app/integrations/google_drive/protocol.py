"""Drive download contract.

Mirrors `noctusai_lib.integrations.google_drive.DriveDownloader` and extends it
with `download_folder` — the one operation gdown gives us for free that the seed
splits across `DriveReader.list` + `DriveDownloader.download`. On absorption,
`download_folder` becomes "list the folder via DriveReader, then download each
file via DriveDownloader" (documented in /CLAUDE.md §3).
"""
from __future__ import annotations

from pathlib import Path
from typing import Protocol

from app.integrations.google_drive.types import DownloadedFile, DriveFile


class DriveDownloader(Protocol):
    """Auth-agnostic Drive download contract."""

    async def get_metadata(self, file_id: str) -> DriveFile | None:
        """Fetch a file's metadata, or None if missing/inaccessible."""
        ...

    async def download(self, file_id: str, dest: Path) -> DriveFile:
        """Download one file's bytes to `dest`; return its metadata."""
        ...

    async def download_folder(
        self, folder_url_or_id: str, dest_dir: Path
    ) -> list[DownloadedFile]:
        """Download every file in a shared folder into `dest_dir`."""
        ...

    async def list_folder(self, folder_url_or_id: str) -> list[DriveFile]:
        """List files in a shared folder (recursive) WITHOUT downloading.

        A reachability probe — confirms credentials can see the folder. Adapters
        that can't list without downloading raise NotImplementedError.
        """
        ...

    # ── write (publish back to Drive) ────────────────────────────────────
    # Optional capability. Read-only adapters (gdown) raise NotImplementedError.
    # On absorption these map onto the seed's write surface; documented as an
    # absorption note in /CLAUDE.md §3 (the noc seam is download-oriented today).

    async def list_children(self, folder_id: str) -> list[DriveFile]:
        """List the direct children (files + folders) of one folder, non-recursive."""
        ...

    async def create_folder(self, name: str, parent_id: str) -> DriveFile:
        """Create a subfolder named `name` under `parent_id`; return its metadata."""
        ...

    async def upload_file(
        self,
        local_path: Path,
        parent_id: str,
        *,
        name: str | None = None,
        mime_type: str | None = None,
    ) -> DriveFile:
        """Upload `local_path` into `parent_id`; return the created file's metadata."""
        ...


__all__ = ["DriveDownloader"]
