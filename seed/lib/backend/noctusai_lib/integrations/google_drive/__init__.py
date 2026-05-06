"""Google Drive v3 download client — canonical Protocol+Fake+Real+factory.

Lifted 2026-05-06 by `youtube-crawler-build` Phase 0 from the original
plan's product-side `gdrive_downloader.py`. youtube-crawler is the N=1
consumer; the user explicitly authorized seed-lift for "spread it
throughout soon" — the seed lands ahead of the second consumer rather
than after.

**What ships:**
- `DriveFile` value object (id / name / size_bytes / mime_type / md5_checksum).
- `DriveDownloader` Protocol — `get_metadata(file_id)` + `download(file_id, dest)`.
- `FakeDriveDownloader` — deterministic in-memory; `add_fake_file(...)` helper
  pre-populates fixtures; `download(...)` writes the seeded bytes to disk.
- `RealDriveDownloader(api_key=..., oauth_credentials=...)` — wraps
  `googleapiclient.discovery.build("drive", "v3", ...)`. Streams via
  `MediaIoBaseDownload`. Logs HTTP errors at WARN before re-raising.
- `make_drive_downloader(use_fake=False, api_key=None, oauth_credentials=None,
  fake_seed_data=None)` — factory.
- `parse_drive_url(url_or_id)` — pure mapper. Accepts file/d/{id}/...,
  open?id={id}, uc?id={id}, uc?export=download&id={id}, and bare ids.

**Shared-link reach.** "Anyone with the link can view" files require
either an `api_key` (cheaper, no consent flow) OR `oauth_credentials`
with `drive.readonly` scope. Private files require OAuth. The Protocol
is auth-agnostic; the factory routes.

**Consumer pattern (youtube-crawler upload pipeline):**

    drive = make_drive_downloader(api_key=settings.google_api_key)
    file_id = parse_drive_url(user_supplied_url)
    meta = await drive.download(file_id, dest=tmp_path / file_id)
    # ... then hand `dest` to youtube_orchestrator.upload(...)
"""

from noctusai_lib.integrations.google_drive.factory import make_drive_downloader
from noctusai_lib.integrations.google_drive.fake import FakeDriveDownloader
from noctusai_lib.integrations.google_drive.mappers import parse_drive_url
from noctusai_lib.integrations.google_drive.protocol import DriveDownloader
from noctusai_lib.integrations.google_drive.types import DriveFile

__all__ = [
    "DriveDownloader",
    "DriveFile",
    "FakeDriveDownloader",
    "make_drive_downloader",
    "parse_drive_url",
]
