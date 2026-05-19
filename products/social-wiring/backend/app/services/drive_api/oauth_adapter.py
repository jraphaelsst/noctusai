"""Google Drive v3 adapter that acts AS the consenting Google user.

Same pattern as ``calendar/oauth_adapter.py``: load the encrypted
credential bundle from :class:`CredentialStore`
(provider=``google_calendar`` — same row, the Calendar consent
includes Drive scope when GOOGLE_OAUTH_SCOPES is configured that
way), refresh if expired, build an authenticated Drive Resource.

This adapter can see the user's ENTIRE Drive (subject to whatever
scopes they consented to), unlike the service-account adapter
which is restricted to explicitly-shared files.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import UUID

from app.services.calendar.oauth_adapter import CALENDAR_PROVIDER, _strip_tz
from app.services.credential_vault import CredentialStore
from app.services.drive_api import _drive_api
from app.services.drive_api.google_adapter import DRIVE_SCOPES, _read_content_via
from app.services.drive_api.mappers import build_search_query, file_body_to_drive_file
from app.services.drive_api.types import DriveFile, DriveFileContent, DriveSearchResult

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
        from google.auth.transport.requests import Request
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
            credentials.refresh(Request())
            new_tokens = dict(tokens)
            new_tokens["access_token"] = credentials.token
            if credentials.expiry is not None:
                new_tokens["expiry"] = credentials.expiry.replace(
                    tzinfo=timezone.utc
                ).isoformat()
            self._store.put(
                str(self._org_id), CALENDAR_PROVIDER, new_tokens, metadata={"channel_id": stored.metadata.get("channel_id"), "channel_title": stored.metadata.get("channel_title"), "scopes": stored.metadata.get("scopes", [])})

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
