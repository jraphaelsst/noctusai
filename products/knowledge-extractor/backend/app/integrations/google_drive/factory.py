"""Drive downloader factory.

Mirrors `noctusai_lib.integrations.google_drive.make_drive_downloader`: routes to
the Fake or a Real adapter. Two Real adapters ship behind the seam:

  - `DriveV3Downloader` — the Google Drive v3 API (api_key OR OAuth). Primary.
  - `GdownDriveDownloader` — public-link download. Fallback / no-key path.

Routing is controlled by `settings.drive_backend`:
  - "auto"  (default): OAuth if configured (handles private/third-party shares),
                       else API key (public links), else gdown.
  - "oauth": Drive v3 via OAuth (runs the consent flow if needed).
  - "api"  : Drive v3 via API key (errors loudly if GOOGLE_API_KEY is unset).
  - "gdown": public-link download.
"""
from __future__ import annotations

from typing import Any

from app.config import get_settings
from app.integrations.google_drive.drive_v3_adapter import (
    DriveNotConfigured,
    DriveV3Downloader,
)
from app.integrations.google_drive.fake import FakeDriveDownloader
from app.integrations.google_drive.gdown_adapter import GdownDriveDownloader
from app.integrations.google_drive.oauth import get_oauth_credentials, oauth_configured
from app.integrations.google_drive.protocol import DriveDownloader
from app.logging_config import get_logger

logger = get_logger(__name__)


def make_drive_downloader(
    *,
    use_fake: bool = False,
    api_key: str | None = None,
    oauth_credentials: Any = None,
) -> DriveDownloader:
    """Build a Drive downloader per `settings.drive_backend`."""
    if use_fake:
        return FakeDriveDownloader()

    settings = get_settings()
    backend = settings.drive_backend.lower()
    key = api_key if api_key is not None else (settings.google_api_key or None)

    if backend == "gdown":
        logger.info("Drive backend: gdown")
        return GdownDriveDownloader()

    if backend == "oauth":
        creds = oauth_credentials or get_oauth_credentials(settings)
        logger.info("Drive backend: Drive v3 API (OAuth)")
        return DriveV3Downloader(oauth_credentials=creds)

    if backend == "api":
        if not key:
            raise DriveNotConfigured(
                "DRIVE_BACKEND=api but GOOGLE_API_KEY is not set. "
                "Note: an API key only reaches 'anyone-with-link' files — for a "
                "folder shared privately with you, use DRIVE_BACKEND=oauth."
            )
        logger.info("Drive backend: Drive v3 API (API key)")
        return DriveV3Downloader(api_key=key)

    # auto
    if oauth_credentials is not None:
        logger.info("Drive backend: Drive v3 API (OAuth, supplied)")
        return DriveV3Downloader(oauth_credentials=oauth_credentials)
    if oauth_configured(settings):
        logger.info("Drive backend: Drive v3 API (OAuth, auto)")
        return DriveV3Downloader(oauth_credentials=get_oauth_credentials(settings))
    if key:
        logger.info("Drive backend: Drive v3 API (API key, auto)")
        return DriveV3Downloader(api_key=key)
    logger.info("Drive backend: gdown (auto — no Google credentials configured)")
    return GdownDriveDownloader()


__all__ = ["make_drive_downloader"]
