"""Drive API package — **thin seed-consume seam**.

Phase 6a-drive of ``projects/social-wiring-google-seed-consume/``
retired the hand-rolled googleapiclient + ``_get_service`` Credentials
machinery in favour of
``noctusai_lib.integrations.google_drive`` (the canonical Protocol +
Fake + Real + factory the seed ships) once the seed `DriveReader`
projection was enriched to absorb the chatbot's full field set
(`parents` / `owners` / `icon_link` / `is_folder` / `raw`; `file_id`
alias; `modified_at: datetime` derived property; `DriveFileContent.text`
with lazy PDF extraction via the `media` seam). The architecture now
mirrors `calendar/`'s post-migration shape (a thin seam selecting
OAuth / service-account / Fake).

Resolution order (preserved verbatim from the absorbed product):

1. OAuth path — when ``GOOGLE_OAUTH_CLIENT_ID`` / ``..._SECRET`` are
   configured AND the org has a stored credential row
   (``CALENDAR_PROVIDER`` — same row, Drive scope bundled into the
   Calendar consent), use the seed `RealDriveReader` wired with a
   `Credentials` from `CredentialStoreDriveResolver`.
2. Service-account path — when ``GOOGLE_SERVICE_ACCOUNT_FILE`` points
   at a readable JSON file, load `service_account.Credentials` with
   `drive.readonly` scope + wire into `RealDriveReader`. NOTE: the SA
   can ONLY access files explicitly shared with its email.
3. Fallback — seed `FakeDriveReader` (wrapped in `SyncDriveReader`).
   Local dev + tests.

The returned object is a `SyncDriveReader` (the seed's sync facade
over the async `DriveReader` Protocol). Consumer code calls
`adapter.search(...)` etc. sync — the boilerplate
`asyncio.to_thread(adapter.search, ...)` the absorbed product used
becomes unnecessary, but is still safe because `SyncDriveReader`
detects a running loop and delegates to a worker thread.

`OAUTH_BACKED_ATTR` is set on the OAuth-backed result so consumers
(e.g. the WhatsApp intake "scope_note" branch) can distinguish OAuth
from service-account / Fake without an `isinstance` check on a
private adapter class. The historic `isinstance(adapter,
GoogleDriveOAuthAdapter)` is replaced by `is_oauth_backed(adapter)`.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

from noctusai_lib.integrations.credential_resolvers import (
    CALENDAR_PROVIDER,
    CredentialStoreDriveResolver,
)
from noctusai_lib.integrations.google_drive import (
    DriveFileContent,
    DriveSearchHit,
    DriveSearchResult,
    FakeDriveReader,
    SyncDriveReader,
    make_sync_drive_reader,
)

from app.config import settings as default_settings

if TYPE_CHECKING:
    from app.services.credential_vault import CredentialStore

logger = logging.getLogger(__name__)

# Read-only scope is enough — the chatbot never writes via this
# adapter. If/when write tools land, switch to `drive.file` or `drive`.
DRIVE_SCOPES = ("https://www.googleapis.com/auth/drive.readonly",)

OAUTH_BACKED_ATTR = "_sw_drive_is_oauth"
"""Attribute set on the returned `SyncDriveReader` when the OAuth path
was chosen. `is_oauth_backed(adapter)` is the public predicate the
WhatsApp intake uses for its `scope_note` branch (replaces the
`isinstance(adapter, GoogleDriveOAuthAdapter)` check that the
absorbed product used)."""

# Back-compat aliases for the legacy product class names. Existing
# consumer code that imported these from `app.services.drive_api`
# continues to compile; the seed value objects expose every field the
# legacy classes exposed (via properties).
DriveFile = DriveSearchHit
"""Alias: the seed `DriveSearchHit` exposes `.file_id` / `.is_folder`
/ `.modified_at` etc. via derived properties — drop-in for the
legacy `DriveFile` dataclass the absorbed product defined."""

__all__ = [
    "CALENDAR_PROVIDER",
    "DRIVE_SCOPES",
    "DriveFile",
    "DriveFileContent",
    "DriveSearchHit",
    "DriveSearchResult",
    "OAUTH_BACKED_ATTR",
    "get_drive_adapter",
    "is_oauth_backed",
]


def is_oauth_backed(adapter: SyncDriveReader) -> bool:
    """True iff the adapter was built from an OAuth credential row
    (replaces `isinstance(adapter, GoogleDriveOAuthAdapter)`)."""
    return bool(getattr(adapter, OAUTH_BACKED_ATTR, False))


def get_drive_adapter(
    *,
    org_id: UUID | None = None,
    credential_store: "CredentialStore | None" = None,
    settings=None,
) -> SyncDriveReader:
    """Return a `SyncDriveReader` for the given org.

    Resolution order: OAuth → service-account → Fake. Mirrors the
    absorbed `get_drive_adapter` shape so call sites don't change."""
    settings = settings or default_settings

    # 1. OAuth — only when client id + secret are configured AND the
    # org has a stored credential row (under CALENDAR_PROVIDER, the
    # bundle Drive scope rides in).
    if (
        org_id is not None
        and credential_store is not None
        and settings.google_oauth_client_id
        and settings.google_oauth_client_secret
        and _has_oauth_credential(credential_store, org_id)
    ):
        logger.info("Drive adapter: OAuth (org %s)", org_id)
        resolver = CredentialStoreDriveResolver(
            credential_store,
            client_id=settings.google_oauth_client_id,
            client_secret=settings.google_oauth_client_secret,
        )
        creds = resolver.get_credentials(str(org_id))
        if creds is not None:
            sync = make_sync_drive_reader(oauth_credentials=creds)
            setattr(sync, OAUTH_BACKED_ATTR, True)
            return sync
        logger.warning(
            "OAuth path selected for org %s but resolver returned None; "
            "falling through to service-account / Fake",
            org_id,
        )

    # 2. Service account
    sa_file = settings.google_service_account_file
    if sa_file and Path(sa_file).is_file():
        sa_creds = _load_service_account_credentials(sa_file)
        if sa_creds is not None:
            logger.info("Drive adapter: service account")
            sync = make_sync_drive_reader(oauth_credentials=sa_creds)
            return sync

    # 3. Fake — dev / no credentials yet
    logger.info("Drive adapter: Fake (no credentials configured)")
    return SyncDriveReader(FakeDriveReader())


def _has_oauth_credential(store: "CredentialStore", org_id: UUID) -> bool:
    try:
        return store.get(str(org_id), CALENDAR_PROVIDER) is not None
    except Exception:
        logger.exception("OAuth credential lookup failed; skipping OAuth path")
        return False


def _load_service_account_credentials(sa_file: str):
    """Load `service_account.Credentials` with the Drive read-only
    scope. Returns `None` on any IO / parsing / `google-auth` error
    so the caller falls through to the Fake (no silent crash)."""
    try:
        info = json.loads(Path(sa_file).read_text())
    except (OSError, ValueError):
        logger.exception(
            "Failed to load service-account file %r; falling back",
            sa_file,
        )
        return None
    try:
        from google.oauth2 import service_account
    except ImportError:
        logger.exception(
            "google-auth not installed; falling back from service-account path"
        )
        return None
    try:
        return service_account.Credentials.from_service_account_info(
            info, scopes=list(DRIVE_SCOPES)
        )
    except Exception:
        logger.exception("Failed to build service-account Credentials")
        return None
