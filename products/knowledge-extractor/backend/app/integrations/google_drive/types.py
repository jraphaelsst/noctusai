"""Drive value objects.

Mirrors `noctusai_lib.integrations.google_drive.DriveFile`.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DriveFile:
    """Metadata for a file fetched from Drive.

    Field names match the seed's `DriveFile` so callers port unchanged.
    """

    id: str
    name: str
    size_bytes: int | None = None
    mime_type: str | None = None
    md5_checksum: str | None = None


@dataclass(frozen=True)
class DownloadedFile:
    """A file downloaded to disk: its on-disk path + Drive metadata."""

    path: Path
    file: DriveFile


__all__ = ["DriveFile", "DownloadedFile"]
