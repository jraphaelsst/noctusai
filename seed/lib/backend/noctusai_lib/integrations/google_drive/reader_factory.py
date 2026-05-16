"""Factory for `DriveReader` — Fake or Real, by flag.

Mirrors `make_drive_downloader` (download surface) + the canonical
Protocol+Fake+Real+factory shape. Lazy-imports `RealDriveReader` so
the fake path stays importable in slim envs without
`google-api-python-client`.
"""

from __future__ import annotations

from typing import Any

from noctusai_lib.integrations.google_drive.fake_reader import FakeDriveReader
from noctusai_lib.integrations.google_drive.reader_types import DriveReader


def make_drive_reader(
    *,
    use_fake: bool = False,
    api_key: str | None = None,
    oauth_credentials: Any = None,
) -> DriveReader:
    """Build a `DriveReader`.

    - `use_fake=True` → `FakeDriveReader` (seed fixtures with
      `add_file(...)` after construction).
    - `use_fake=False` → `RealDriveReader` with `api_key`
      (anyone-with-link) OR `oauth_credentials` (private / the
      share-with-SA quick-start). At least one required; otherwise
      `RealDriveReader.__init__` raises `ValueError`.
    """
    if use_fake:
        return FakeDriveReader()

    from noctusai_lib.integrations.google_drive.real_reader import RealDriveReader

    return RealDriveReader(api_key=api_key, oauth_credentials=oauth_credentials)


__all__ = ["make_drive_reader"]
