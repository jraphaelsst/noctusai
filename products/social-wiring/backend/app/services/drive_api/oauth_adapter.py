"""Google Drive v3 adapter that acts AS the consenting Google user.

Same pattern the absorbed ``calendar/oauth_adapter.py`` used (Phase 5
of ``social-wiring-google-seed-consume`` retired that module for the
seed adapter; this Drive module stays product-local because the seed
``DriveReader`` Protocol has a strictly narrower projection — see
``app/services/drive_api/__init__.py`` module docstring + the
``seed-google-drive-projection-enrichment`` follow-up). It loads the
encrypted credential bundle from :class:`CredentialStore`
(``provider="google_calendar"`` — same row, the Calendar consent
includes Drive scope when ``GOOGLE_OAUTH_SCOPES`` is configured that
way), refreshes via the seed ``GoogleProvider`` (Phase 3b), and builds
an authenticated Drive Resource.

This adapter can see the user's ENTIRE Drive (subject to whatever
scopes they consented to), unlike the service-account adapter
which is restricted to explicitly-shared files.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import UUID

from app.services.calendar import CALENDAR_PROVIDER
from noctusai_lib.security.oauth import GoogleProvider
from app.services.credential_vault import CredentialStore
from app.services.drive_api import _drive_api
from app.services.drive_api.google_adapter import DRIVE_SCOPES, _read_content_via
from app.services.drive_api.mappers import build_search_query, file_body_to_drive_file
from app.services.drive_api.types import DriveFile, DriveFileContent, DriveSearchResult


def _strip_tz(value):
    """``google.oauth2.credentials.Credentials`` requires a naive datetime
    for ``expiry``. Accept either a datetime or an ISO string from the
    stored credential bundle; convert to UTC and drop tzinfo. Lifted
    from the retired ``calendar/oauth_adapter.py`` when Phase 5
    migrated calendar to the seed adapter."""
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _run_oauth_sync(awaitable):
    """Drive a seed-provider coroutine from a sync caller. The drive
    adapter methods are sync (called from sync FastAPI handlers in a
    threadpool with no running loop), so ``asyncio.run`` is the simplest
    correct bridge to the async seed ``GoogleProvider``."""
    import asyncio

    return asyncio.run(awaitable)

if TYPE_CHECKING:
    from googleapiclient.discovery import Resource


GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"


class GoogleDriveOAuthAdapter:
    """OAuth-user Drive adapter (read-only)."""

    supports_full_user_drive = True

    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        credential_store: CredentialStore,
        org_id: UUID,
    ):
        self._client_id = client_id
        self._client_secret = client_secret
        self._store = credential_store
        self._org_id = org_id
    def _get_service(self) -> "Resource":
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        stored = self._store.get(str(self._org_id), CALENDAR_PROVIDER)
        if stored is None:
            raise RuntimeError(
                "No Google OAuth credential stored for this org. "
                "Visit /api/calendar/oauth/start to consent — Drive "
                "scope is bundled with the Calendar consent."
            )

        tokens = stored.tokens
        # Combine Drive + Calendar scopes so the same credential row
        # works for both. The token issued by Google carries the union
        # of all consented scopes regardless of what we ask for here.
        scopes = (stored.metadata.get("scopes", []) or []) + DRIVE_SCOPES
        credentials = Credentials(
            token=tokens.get("access_token"),
            refresh_token=tokens.get("refresh_token"),
            token_uri=GOOGLE_TOKEN_URI,
            client_id=self._client_id,
            client_secret=self._client_secret,
            scopes=scopes,
            expiry=_strip_tz(tokens.get("expiry")),
        )

        if not credentials.valid:
            # OAuth refresh lifecycle delegated to the seed GoogleProvider
            # (replaces the hand-rolled google.oauth2.credentials.refresh).
            refresh_token = tokens.get("refresh_token")
            if not refresh_token:
                raise RuntimeError(
                    "Stored Google credential has no refresh_token; "
                    "re-consent at /api/calendar/oauth/start."
                )
            provider = GoogleProvider(
                client_id=self._client_id,
                client_secret=self._client_secret,
            )
            token_set = _run_oauth_sync(provider.refresh(refresh_token))
            new_tokens = dict(tokens)
            new_tokens["access_token"] = token_set.access_token
            expires_at = token_set.expires_at
            if expires_at is not None:
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=timezone.utc)
                new_tokens["expiry"] = expires_at.astimezone(
                    timezone.utc
                ).isoformat()
            self._store.put(
                str(self._org_id),
                CALENDAR_PROVIDER,
                new_tokens,
                metadata={
                    "channel_id": stored.metadata.get("channel_id"),
                    "channel_title": stored.metadata.get("channel_title"),
                    "scopes": stored.metadata.get("scopes", []),
                },
            )
            credentials = Credentials(
                token=token_set.access_token,
                refresh_token=refresh_token,
                token_uri=GOOGLE_TOKEN_URI,
                client_id=self._client_id,
                client_secret=self._client_secret,
                scopes=scopes,
                expiry=_strip_tz(new_tokens.get("expiry")),
            )

        return build("drive", "v3", credentials=credentials, cache_discovery=False)

    def search(
        self,
        *,
        query: str | None = None,
        mime_type: str | None = None,
        folder_id: str | None = None,
        page_size: int = 20,
        order_by: str = "modifiedTime desc",
    ) -> DriveSearchResult:
        q = build_search_query(query=query, mime_type=mime_type, folder_id=folder_id)
        response = _drive_api.files_list(
            self._get_service(),
            q=q,
            page_size=page_size,
            order_by=order_by,
        )
        files = [file_body_to_drive_file(b) for b in response.get("files", [])]
        return DriveSearchResult(
            files=files,
            next_page_token=response.get("nextPageToken"),
            query_used=q,
        )

    def get_file(self, file_id: str) -> DriveFile | None:
        body = _drive_api.files_get(self._get_service(), file_id)
        return file_body_to_drive_file(body) if body else None

    def list_recent(self, *, page_size: int = 10) -> DriveSearchResult:
        return self.search(page_size=page_size)

    def read_content(
        self,
        file_id: str,
        *,
        max_bytes: int = 200_000,
    ) -> DriveFileContent | None:
        return _read_content_via(self._get_service(), file_id, max_bytes=max_bytes)
