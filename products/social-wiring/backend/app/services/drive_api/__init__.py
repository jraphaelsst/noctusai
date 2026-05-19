"""Drive API package factory.

**Phase 5 status: KEPT product-local on a thin product seam interim
because the seed ``DriveReader`` Protocol projects a strictly narrower
field set than the chatbot UI consumes** — same shape of decision
Phase 4 made for the YouTube projection-enrichment gap. The retained
seam re-uses the seed ``GoogleProvider`` for OAuth refresh
(Phase 3b) and the seed ``CALENDAR_PROVIDER`` constant; the
``googleapiclient.discovery.build("drive", "v3", ...)`` API layer
stays local until the seed Protocol/value-objects can absorb the
projection without breaking consumers.

Projection mismatch (verified 2026-05-19, seed ``DriveReader`` at
``noctusai_lib.integrations.google_drive.reader_types``):

- ``DriveSearchHit`` (seed) vs ``DriveFile`` (product): seed lacks
  ``parents``, ``owners``, ``icon_link``, ``is_folder`` (derivable),
  ``raw`` (the full Drive response body); ``id`` vs ``file_id`` rename;
  ``modified_time: str`` vs ``modified_at: datetime``.
- ``DriveFileContent`` (seed) vs same (product): seed returns raw
  ``data: bytes``, product returns decoded ``text: str`` + ``bytes_read``
  + ``raw_mime``; ``rendered_as`` vocabulary differs
  (``"text/csv"``/``"text/plain"``/``"passthrough"`` vs
  ``"csv"``/``"text"``/``"pdf-text"`` — and the product surface owns
  PDF-text extraction via ``_extract_pdf_text``).
- ``DriveReader`` is async-only; product surface is sync (called from
  sync FastAPI routes inside ``asyncio.to_thread``).

The follow-up project ``seed-google-drive-projection-enrichment``
enriches the seed Protocol/value-objects with the missing fields,
adds a sync facade or absorbs the ``asyncio.to_thread`` bridge, and
then this module collapses to a re-export the way ``calendar/``
already does. Until then this seam stays product-local — silently
degrading the chatbot UI (dropping owner/parent/folder context) is
explicitly forbidden by the projection-mismatch methodology.

Resolution order (preserved verbatim):

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
from app.services.calendar import CALENDAR_PROVIDER
from app.services.drive_api.fake_adapter import FakeDriveAdapter
from app.services.drive_api.google_adapter import GoogleDriveAdapter
from app.services.drive_api.oauth_adapter import GoogleDriveOAuthAdapter
from app.services.drive_api.types import DriveAdapter, DriveFile, DriveSearchResult

if TYPE_CHECKING:
    from app.services.credential_vault import CredentialStore

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
        return store.get(str(org_id), CALENDAR_PROVIDER) is not None
    except Exception:
        logger.exception("OAuth credential lookup failed; skipping OAuth path")
        return False
