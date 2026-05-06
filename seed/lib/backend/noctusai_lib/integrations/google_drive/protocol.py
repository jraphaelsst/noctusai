"""Google Drive v3 client Protocol.

The seed contract covers the two operations every consumer needs: fetch
metadata (so we can size-check / mime-check before committing to a
download) and stream bytes to disk. Drive supports many more endpoints
(create / update / list / share); they're explicitly out of scope until
the second consumer arrives — add to the Protocol then, with the same
canonical shape.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from noctusai_lib.integrations.google_drive.types import DriveFile


class DriveDownloader(Protocol):
    """Google Drive v3 download contract.

    Two concrete implementations ship in the seed:
    - `FakeDriveDownloader` — deterministic in-memory dev/test default.
      `add_fake_file(...)` seeds fixtures; `download(...)` writes the
      seeded bytes to the destination path.
    - `RealDriveDownloader` — wraps `googleapiclient.discovery.build`.
      Streams via `MediaIoBaseDownload`. Logs API errors at WARN before
      re-raising.

    Build via `make_drive_downloader(...)`. The factory routes based on
    `use_fake` flag — see `factory.py`.

    **Auth:** the Real adapter accepts either an `api_key` (works for
    anyone-with-link public files) OR `oauth_credentials` with
    `drive.readonly` (or higher) scope (required for private files).
    The Protocol is auth-agnostic.
    """

    async def get_metadata(self, file_id: str) -> DriveFile | None:
        """Fetch a file's metadata.

        Returns `None` when the file doesn't exist OR the caller's
        credentials don't have access (Drive returns 404 for both
        non-existent and inaccessible — by design, to avoid leaking
        existence)."""
        ...

    async def download(self, file_id: str, dest: Path) -> DriveFile:
        """Download a file's bytes to `dest`.

        Creates parent directories as needed. Overwrites `dest` if it
        already exists. Returns the file's `DriveFile` metadata so
        callers can verify size / md5 after writing.

        Raises `FileNotFoundError` when the file doesn't exist or is
        inaccessible. Raises `googleapiclient.errors.HttpError` for
        other API errors (rate limit, server error) after logging."""
        ...


__all__ = ["DriveDownloader"]
