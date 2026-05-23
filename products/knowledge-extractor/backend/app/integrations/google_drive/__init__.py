"""Google Drive seam — Protocol + Fake + gdown Real + factory.

Mirrors `noctusai_lib.integrations.google_drive`. See /CLAUDE.md §3 for the
absorption map. Step-1 access is gdown (public "anyone-with-link" folders).
"""
from app.integrations.google_drive.drive_v3_adapter import (
    DriveError,
    DriveNotConfigured,
    DriveV3Downloader,
)
from app.integrations.google_drive.factory import make_drive_downloader
from app.integrations.google_drive.fake import FakeDriveDownloader
from app.integrations.google_drive.gdown_adapter import GdownDriveDownloader
from app.integrations.google_drive.mappers import is_folder_url, parse_drive_url
from app.integrations.google_drive.oauth import (
    SCOPES,
    WRITE_SCOPES,
    get_oauth_credentials,
    oauth_configured,
)
from app.integrations.google_drive.protocol import DriveDownloader
from app.integrations.google_drive.types import DownloadedFile, DriveFile

__all__ = [
    "DriveDownloader",
    "DriveFile",
    "DownloadedFile",
    "FakeDriveDownloader",
    "GdownDriveDownloader",
    "DriveV3Downloader",
    "DriveError",
    "DriveNotConfigured",
    "make_drive_downloader",
    "get_oauth_credentials",
    "oauth_configured",
    "SCOPES",
    "WRITE_SCOPES",
    "parse_drive_url",
    "is_folder_url",
]
