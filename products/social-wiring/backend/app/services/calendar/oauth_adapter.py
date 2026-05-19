"""Google Calendar v3 adapter that acts AS the consenting Google user.

Ported from
``whatsapp-google-scheduling/app/services/calendar/oauth_adapter.py``.

The reference repo stored credentials in a dedicated SQLAlchemy
``OAuthCredential`` table. We map onto our existing
``social_wiring.credentials`` table via :class:`CredentialStore`
(same Fernet encryption + org-scoping + UPSERT semantics already used
for the YouTube refresh token). One row per
``(org_id, provider='google_calendar')``.

Unlike the service-account adapter, this one CAN add attendees and
send invite emails because it impersonates a real Google account
via stored OAuth refresh tokens.

Each ``_get_service()`` call:

1. Loads the credential row for ``(org_id, provider='google_calendar')``.
2. If the access token is expired, exchanges the refresh token for a
   new access token and persists it back.
3. Builds an authenticated ``googleapiclient`` Resource.

Bootstrap flow (one-time, requires user intervention):

1. Operator hits ``GET /api/calendar/oauth/start`` → server returns the
   Google consent URL with the configured scopes + redirect URI.
2. User completes consent in browser → Google redirects to
   ``GET /api/calendar/oauth/callback?code=...&state=<org_id>``.
3. Server exchanges the code for refresh + access tokens, encrypts +
   persists via ``CredentialStore.upsert(provider='google_calendar')``.

Subsequent calls hit step 1 of ``_get_service()`` and reuse the stored
refresh token.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import UUID

from app.services.calendar import _google_api
from app.services.calendar.google_adapter import CALENDAR_SCOPES
from app.services.calendar.mappers import event_to_google_body, google_body_to_created_event
from app.services.calendar.types import CreatedEvent, EventInput
from noctusai_lib.security.oauth import GoogleProvider
from app.services.credential_vault import CredentialStore

if TYPE_CHECKING:
    from googleapiclient.discovery import Resource


GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"
CALENDAR_PROVIDER = "google_calendar"


class GoogleCalendarOAuthAdapter:
    """OAuth-user-backed Google Calendar adapter.

    Constructor takes ``client_id`` / ``client_secret`` (the OAuth-client
    credentials from Google Cloud Console) + a :class:`CredentialStore`
    instance + the ``org_id`` whose stored credential we should use.
    """

    supports_attendees = True

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
                "No Google Calendar OAuth credential stored for this org. "
                "Visit /api/calendar/oauth/start to consent."
            )

        tokens = stored.tokens
        credentials = Credentials(
            token=tokens.get("access_token"),
            refresh_token=tokens.get("refresh_token"),
            token_uri=GOOGLE_TOKEN_URI,
            client_id=self._client_id,
            client_secret=self._client_secret,
            scopes=CALENDAR_SCOPES,
            expiry=_strip_tz(tokens.get("expiry")),
        )

        if not credentials.valid:
            # OAuth refresh lifecycle delegated to the seed GoogleProvider
            # (replaces the hand-rolled google.oauth2.credentials.refresh).
            # The googleapiclient Credentials object is rebuilt with the
            # fresh access token so the Phase-5-bound API client is
            # unchanged.
            refresh_token = tokens.get("refresh_token")
            if not refresh_token:
                raise RuntimeError(
                    "Stored Google Calendar credential has no refresh_token; "
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
                    "scopes": stored.metadata.get("scopes", [])
                    or list(CALENDAR_SCOPES),
                },
            )
            credentials = Credentials(
                token=token_set.access_token,
                refresh_token=refresh_token,
                token_uri=GOOGLE_TOKEN_URI,
                client_id=self._client_id,
                client_secret=self._client_secret,
                scopes=CALENDAR_SCOPES,
                expiry=_strip_tz(new_tokens.get("expiry")),
            )

        return build("calendar", "v3", credentials=credentials, cache_discovery=False)

    def create_event(self, calendar_id: str, event: EventInput) -> CreatedEvent:
        response = _google_api.insert_event(
            self._get_service(), calendar_id, event_to_google_body(event)
        )
        return google_body_to_created_event(response)

    def get_event(self, calendar_id: str, event_id: str) -> CreatedEvent | None:
        body = _google_api.get_event(self._get_service(), calendar_id, event_id)
        return google_body_to_created_event(body) if body else None

    def list_events(
        self,
        calendar_id: str,
        time_min: datetime,
        time_max: datetime,
    ) -> list[CreatedEvent]:
        items = _google_api.list_events(
            self._get_service(), calendar_id, time_min, time_max
        )
        return [google_body_to_created_event(item) for item in items]

    def delete_event(self, calendar_id: str, event_id: str) -> None:
        _google_api.delete_event(self._get_service(), calendar_id, event_id)


def _strip_tz(value):
    """``google.oauth2.credentials.Credentials`` requires a naive datetime
    for ``expiry``. Accept either a datetime or an ISO string from the
    stored credential bundle; convert to UTC and drop tzinfo."""
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
    """Drive a seed-provider coroutine from a sync caller.

    The calendar adapter methods are sync (called from sync FastAPI
    handlers in a threadpool with no running loop), so ``asyncio.run``
    is the simplest correct bridge to the async seed ``GoogleProvider``.
    """
    import asyncio

    return asyncio.run(awaitable)
