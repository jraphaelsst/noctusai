"""Drive API package factory.

Same resolution as the calendar factory:

1. OAuth path — when GOOGLE_OAUTH_CLIENT_ID/SECRET are configured AND
   the org has a stored credential (same row Calendar uses; Drive
   scope is bundled into the Calendar consent).
2. Service-account path — when GOOGLE_SERVICE_ACCOUNT_FILE points at
   a readable JSON. NOTE: the SA can ONLY access files explicitly
   shared with its email.
3. Fallback — :class:`FakeDriveAdapter`. Local dev + tests.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

from app.config import settings as default_settings
from app.services.calendar.oauth_adapter import CALENDAR_PROVIDER
from app.services.drive_api.fake_adapter import FakeDriveAdapter
from app.services.drive_api.google_adapter import GoogleDriveAdapter
from app.services.drive_api.oauth_adapter import GoogleDriveOAuthAdapter
from app.services.drive_api.types import DriveAdapter, DriveFile, DriveSearchResult

if TYPE_CHECKING:
    from app.services.credential_store import CredentialStore

logger = logging.getLogger(__name__)

__all__ = [
    "DriveAdapter",
    "DriveFile",
    "DriveSearchResult",
    "FakeDriveAdapter",
    "GoogleDriveAdapter",
    "GoogleDriveOAuthAdapter",
    "get_drive_adapter",
]


def get_drive_adapter(
    *,
    org_id: UUID | None = None,
    credential_store: "CredentialStore | None" = None,
    settings=None,
) -> DriveAdapter:
    settings = settings or default_settings

    if (
        org_id is not None
        and credential_store is not None
        and settings.google_oauth_client_id
        and settings.google_oauth_client_secret
        and _has_oauth_credential(credential_store, org_id)
    ):
        logger.info("Drive adapter: GoogleDriveOAuthAdapter (org %s)", org_id)
        return GoogleDriveOAuthAdapter(
            client_id=settings.google_oauth_client_id,
            client_secret=settings.google_oauth_client_secret,
            credential_store=credential_store,
            org_id=org_id,
        )

    sa_file = settings.google_service_account_file
    if sa_file and Path(sa_file).is_file():
        logger.info("Drive adapter: GoogleDriveAdapter (service account)")
        return GoogleDriveAdapter(sa_file)

    return FakeDriveAdapter()


def _has_oauth_credential(store: "CredentialStore", org_id: UUID) -> bool:
    try:
        return store.get(org_id=org_id, provider=CALENDAR_PROVIDER) is not None
    except Exception:
        logger.exception("OAuth credential lookup failed; skipping OAuth path")
        return False
