"""Deterministic in-memory Drive downloader for dev/tests.

Mirrors `noctusai_lib.integrations.google_drive.FakeDriveDownloader`:
`add_fake_file(...)` seeds fixtures; `download(...)` writes seeded bytes to disk.
"""
from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

from app.integrations.google_drive.drive_v3_adapter import FOLDER_MIME
from app.integrations.google_drive.types import DownloadedFile, DriveFile


class FakeDriveDownloader:
    """In-memory Drive downloader. No network, no credentials."""

    def __init__(self) -> None:
        self._files: dict[str, tuple[DriveFile, bytes]] = {}
        # write surface: a folder tree keyed by parent id, plus an upload log.
        self._children: dict[str, list[DriveFile]] = {}
        self._uploaded: dict[str, bytes] = {}  # file_id -> bytes
        self.uploads: list[tuple[str, str]] = []  # (parent_id, name), in call order
        self._next = 0

    def add_fake_file(
        self,
        file_id: str,
        name: str,
        content: bytes,
        *,
        mime_type: str | None = None,
    ) -> DriveFile:
        """Seed a fixture file; returns its metadata."""
        meta = DriveFile(
            id=file_id,
            name=name,
            size_bytes=len(content),
            mime_type=mime_type,
            md5_checksum=hashlib.md5(content).hexdigest(),  # noqa: S324 (Drive uses md5)
        )
        self._files[file_id] = (meta, content)
        return meta

    async def get_metadata(self, file_id: str) -> DriveFile | None:
        await asyncio.sleep(0)
        entry = self._files.get(file_id)
        return entry[0] if entry else None

    async def download(self, file_id: str, dest: Path) -> DriveFile:
        await asyncio.sleep(0)
        entry = self._files.get(file_id)
        if entry is None:
            raise FileNotFoundError(f"Fake file not found: {file_id}")
        meta, content = entry
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)
        return meta

    async def download_folder(
        self, folder_url_or_id: str, dest_dir: Path
    ) -> list[DownloadedFile]:
        await asyncio.sleep(0)
        dest_dir.mkdir(parents=True, exist_ok=True)
        out: list[DownloadedFile] = []
        for meta, content in self._files.values():
            path = dest_dir / meta.name
            path.write_bytes(content)
            out.append(DownloadedFile(path=path, file=meta))
        return out

    async def list_folder(self, folder_url_or_id: str) -> list[DriveFile]:
        await asyncio.sleep(0)
        return [meta for meta, _ in self._files.values()]

    # ── write surface ────────────────────────────────────────────────
    def add_folder(self, folder_id: str, name: str, parent_id: str) -> DriveFile:
        """Seed an existing Drive folder into the in-memory tree."""
        meta = DriveFile(id=folder_id, name=name, mime_type=FOLDER_MIME)
        self._children.setdefault(parent_id, []).append(meta)
        return meta

    def _new_id(self, prefix: str) -> str:
        self._next += 1
        return f"{prefix}-{self._next}"

    async def list_children(self, folder_id: str) -> list[DriveFile]:
        await asyncio.sleep(0)
        return list(self._children.get(folder_id, []))

    async def create_folder(self, name: str, parent_id: str) -> DriveFile:
        await asyncio.sleep(0)
        meta = DriveFile(id=self._new_id("folder"), name=name, mime_type=FOLDER_MIME)
        self._children.setdefault(parent_id, []).append(meta)
        return meta

    async def upload_file(
        self,
        local_path: Path,
        parent_id: str,
        *,
        name: str | None = None,
        mime_type: str | None = None,
    ) -> DriveFile:
        await asyncio.sleep(0)
        content = local_path.read_bytes()
        meta = DriveFile(
            id=self._new_id("file"),
            name=name or local_path.name,
            size_bytes=len(content),
            mime_type=mime_type,
        )
        self._children.setdefault(parent_id, []).append(meta)
        self._uploaded[meta.id] = content
        self.uploads.append((parent_id, meta.name))
        return meta


__all__ = ["FakeDriveDownloader"]
