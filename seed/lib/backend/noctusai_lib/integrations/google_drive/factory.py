"""Factory for `DriveDownloader` — Fake or Real, by flag.

Mirrors the canonical Protocol+Fake+Real+factory shape established by
`integrations/google_calendar` + `google_maps` + `youtube`. The factory
is the single seam consumers reach for: pass `use_fake=True` for
tests / dev, or supply real credentials for production.
"""

from __future__ import annotations

from typing import Any

from noctusai_lib.integrations.google_drive.fake import FakeDriveDownloader
from noctusai_lib.integrations.google_drive.protocol import DriveDownloader


def make_drive_downloader(
    *,
    use_fake: bool = False,
    api_key: str | None = None,
    oauth_credentials: Any = None,
    fake_seed_data: dict[str, Any] | None = None,
) -> DriveDownloader:
    """Build a `DriveDownloader`.

    - `use_fake=True` → returns `FakeDriveDownloader`, optionally
      pre-populated by `fake_seed_data["files"]` (a dict of
      `file_id → (DriveFile, bytes)`). Tests typically call
      `add_fake_file(...)` after construction instead.
    - `use_fake=False` → returns `RealDriveDownloader` configured with
      `api_key` (anyone-with-link public files) OR `oauth_credentials`
      (any `google.oauth2.credentials.Credentials`-shaped object — for
      private files). At least one must be supplied; otherwise
      `RealDriveDownloader.__init__` raises `ValueError`.

    Lazy import of `RealDriveDownloader` keeps the fake path importable
    in slim environments that don't ship `google-api-python-client`."""
    if use_fake:
        seed = (fake_seed_data or {}).get("files")
        return FakeDriveDownloader(files=seed)

    from noctusai_lib.integrations.google_drive.real import RealDriveDownloader

    return RealDriveDownloader(api_key=api_key, oauth_credentials=oauth_credentials)


__all__ = ["make_drive_downloader"]
