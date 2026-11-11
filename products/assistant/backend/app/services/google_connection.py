"""The Assistant's Google connection (D50): one OAuth grant per org, stored encrypted in `assistant.oauth_credentials`.

Everything vendor-shaped comes from the seed: `GoogleProvider` (PKCE), `OAuthStateStore` (server-bound single-use state
carrying the PKCE verifier), `CredentialStore` (Fernet at rest) and the calendar / drive adapters through their
credential resolvers. This module only decides the Assistant's policy: WHICH scopes (least privilege), WHERE the grant
is stored, and what "connected" means.

Scopes (D37 first consent screen, least privilege):
  openid + userinfo.email  the connected account's address (shown in the UI);
  calendar.events          read the calendar and create a confirmed event (NOT the full `calendar` scope);
  drive.readonly           read Drive files + export Sheets / Docs;
  drive.file               create/edit only the files this app creates.
No Gmail, no `drive` (full), no `calendar` (full), no Sheets/Docs write scopes.
"""
from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from noctusai_lib.config.product_urls import resolve_product_url
from noctusai_lib.integrations.credential_resolvers import CALENDAR_PROVIDER, CredentialStoreCalendarResolver, CredentialStoreDriveResolver
from noctusai_lib.integrations.google_calendar import get_calendar_adapter
from noctusai_lib.integrations.google_drive.reader_factory import make_drive_reader
from noctusai_lib.integrations.google_scopes import GOOGLE_KITCHEN_SINK_SCOPES
from noctusai_lib.primitives.not_configured import IntegrationNotConfigured
from noctusai_lib.security.api_keys import require_fernet
from noctusai_lib.security.oauth import GoogleProvider, TokenSet, make_oauth_state_store
from noctusai_lib.security.token_store import make_credential_store

from app.config import settings
from app.dependencies import _db

logger = logging.getLogger(__name__)

_G = "https://www.googleapis.com/auth"
SCOPE_CALENDAR = f"{_G}/calendar.events"
SCOPE_DRIVE_READ = f"{_G}/drive.readonly"
SCOPE_DRIVE_FILE = f"{_G}/drive.file"
ASSISTANT_GOOGLE_SCOPES: list[str] = ["openid", f"{_G}/userinfo.email", SCOPE_CALENDAR, SCOPE_DRIVE_READ, SCOPE_DRIVE_FILE]
#: Without these two the connection is useless to the Assistant: the UI offers "reconectar" instead of pretending.
REQUIRED_SCOPES: tuple[str, ...] = (SCOPE_CALENDAR, SCOPE_DRIVE_READ)
# Single source of truth: the seed kitchen-sink. A literal that drifts from it fails the boot, not the consent screen.
_stray = [s for s in ASSISTANT_GOOGLE_SCOPES if s not in GOOGLE_KITCHEN_SINK_SCOPES]
if _stray:
    raise AssertionError(f"Assistant Google scopes not in the seed kitchen-sink: {_stray}")

OAUTH_PROVIDER = "google"          # path / state-store provider name
STORE_PROVIDER = CALENDAR_PROVIDER  # the seed resolvers read this row for BOTH the calendar and the drive adapters
CALLBACK_PATH = "/api/google/oauth/callback"
#: The browser binding of a flow (login-CSRF / account-linking defence): host-only (`__Host-`: Secure, Path=/, no
#: Domain), HttpOnly, SameSite=Lax (a top-level GET from Google still carries it; a cross-site subresource does not).
COOKIE_NAME = "__Host-ast_goauth"
COOKIE_MAX_AGE = 600
STATES_TABLE = "oauth_states"
CREDENTIALS_TABLE = "oauth_credentials"


class GoogleNotConfigured(RuntimeError, IntegrationNotConfigured):
    """A deploy gap (client id/secret, ENCRYPTION_KEY, product URL) -- the routes map it to a 503, never a fallback."""


class NoRefreshToken(ValueError):
    """Google returned no refresh token: the connection could never outlive an hour, so it is refused."""


class NotConnected(RuntimeError):
    """This org has no usable Google grant."""


def require_app_identity() -> tuple[str, str]:
    if not settings.google_oauth_client_id or not settings.google_oauth_client_secret:
        raise GoogleNotConfigured("GOOGLE_OAUTH_CLIENT_ID / GOOGLE_OAUTH_CLIENT_SECRET não configurados.")
    return settings.google_oauth_client_id, settings.google_oauth_client_secret


def redirect_uri() -> str:
    if settings.google_oauth_redirect_uri:
        return settings.google_oauth_redirect_uri
    try:
        return resolve_product_url("assistant") + CALLBACK_PATH
    except ValueError as exc:
        raise GoogleNotConfigured("URL pública do Assistant não configurada.") from exc


def frontend_url(path: str) -> str:
    """The page the callback sends the browser back to: same origin as the registered redirect URI."""
    uri = redirect_uri()
    return uri[: -len(CALLBACK_PATH)] + path if uri.endswith(CALLBACK_PATH) else path


# NOC-REMEDIATE[encryption-key-rotation]: one ENCRYPTION_KEY encrypts every Fernet column of this product (WAHA api key,
# Google grants, PKCE verifiers); rotation needs the seed MultiKeyDecryptor wired through the stores. Destination: a
# seed-level key-ring seam for the credential stores -- 2026-11-10
def fernet_key() -> bytes:
    from noctusai_lib.security.api_keys import EncryptionNotConfigured

    try:
        require_fernet(settings.encryption_key)
    except EncryptionNotConfigured as exc:
        raise GoogleNotConfigured("ENCRYPTION_KEY não configurada.") from exc
    return settings.encryption_key.encode("utf-8")


def build_provider():
    client_id, client_secret = require_app_identity()
    # PKCE on; incremental auth off: a token carries EXACTLY these scopes (Google refuses some merged combinations).
    return GoogleProvider(client_id, client_secret, use_pkce=True, include_granted_scopes=False)


def build_state_store(admin_client):
    return make_oauth_state_store(client=admin_client, fernet_key=fernet_key(), table=STATES_TABLE)


def build_credential_store(admin_client):
    return make_credential_store(client=admin_client, fernet_key=fernet_key(), table=CREDENTIALS_TABLE)


def account_email_from_id_token(raw: dict) -> Optional[str]:
    """The `email` claim of the `id_token` Google returned DIRECTLY from the token endpoint over TLS (OIDC Core
    3.1.3.7: that response needs no signature check). None when absent; never raises."""
    token = (raw or {}).get("id_token")
    if not isinstance(token, str) or token.count(".") != 2:
        return None
    try:
        payload = token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except (ValueError, TypeError):
        return None
    email = claims.get("email")
    return email if isinstance(email, str) and email else None


def persist_tokens(store, *, org_id: str, user_id: str, tokens: TokenSet) -> dict:
    """Write the grant. Refuses a grant without a refresh token (the connection could never outlive an hour)."""
    if not tokens.refresh_token:
        raise NoRefreshToken("sem_refresh_token")
    granted = list(tokens.scope or [])
    store.put(
        org_id,
        STORE_PROVIDER,
        {
            "access_token": tokens.access_token,
            "refresh_token": tokens.refresh_token,
            "expiry": tokens.expires_at.isoformat() if tokens.expires_at else None,
            "scope": granted,
        },
        metadata={
            "scopes": granted,
            "account_email": account_email_from_id_token(tokens.raw),
            "connected_by": user_id,
            "connected_at": datetime.now(timezone.utc).isoformat(),
            "needs_reconnection": False,
        },
    )
    return {"scopes": granted}


def user_is_org_admin(user_id: str, org_id: str) -> bool:
    """Is `user_id` an admin of `org_id` RIGHT NOW (trusted `noctus_users` row, the seed membership resolver)? Raises on
    a DB error: the caller fails closed."""
    from noctusai_lib.api.auth.session.scopes import ADMIN_ORG_ROLES, resolve_org_membership

    membership = resolve_org_membership(_db.get_core_client(), user_id)
    return (
        membership is not None
        and str(membership.get("org_id")) == str(org_id)
        and membership.get("org_role") in ADMIN_ORG_ROLES
    )


def remove_grant(admin_client, org_id: str, actor_id: str) -> None:
    """Delete the org's grant through `assistant.google_desconectar` (one transaction: the delete and its `disconnect`
    event, which names the actor)."""
    admin_client.rpc("google_desconectar", {"p_org_id": org_id, "p_provider": STORE_PROVIDER, "p_actor_id": actor_id}).execute()


@dataclass(frozen=True)
class ConnectionStatus:
    connected: bool
    account_email: Optional[str] = None
    scopes: tuple[str, ...] = ()
    missing_scopes: tuple[str, ...] = ()
    connected_at: Optional[str] = None
    needs_reconnection: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "connected": self.connected,
            "account_email": self.account_email,
            "scopes": list(self.scopes),
            "missing_scopes": list(self.missing_scopes),
            "connected_at": self.connected_at,
            "needs_reconnection": self.needs_reconnection,
            "app_scopes": ASSISTANT_GOOGLE_SCOPES,
        }


def read_status(store, org_id: str) -> ConnectionStatus:
    """Never exposes a token: only the non-secret facts (account, granted scopes, when)."""
    stored = store.get(org_id, STORE_PROVIDER)
    if stored is None or not stored.tokens.get("refresh_token"):
        return ConnectionStatus(connected=False)
    meta = stored.metadata or {}
    granted = tuple(meta.get("scopes") or stored.tokens.get("scope") or ())
    return ConnectionStatus(
        connected=True,
        account_email=meta.get("account_email"),
        scopes=granted,
        missing_scopes=tuple(s for s in REQUIRED_SCOPES if s not in granted),
        connected_at=meta.get("connected_at"),
        needs_reconnection=bool(meta.get("needs_reconnection")),
    )


def mark_needs_reconnection(store, org_id: str) -> None:
    """Token death is a state, not a 500: the grant stays (so the UI can say which account) but is flagged."""
    stored = store.get(org_id, STORE_PROVIDER)
    if stored is None:
        return
    store.put(org_id, STORE_PROVIDER, stored.tokens, metadata={**(stored.metadata or {}), "needs_reconnection": True})


class GoogleClients:
    """The two Google reads the proof endpoint needs, built from the org's stored grant through the SEED factories.
    A missing grant raises `NotConnected` (the factories would otherwise hand back a Fake -- never in a real deploy)."""

    def __init__(self, store) -> None:
        self._store = store

    def _credentials_present(self, org_id: str) -> None:
        if read_status(self._store, org_id).connected is False:
            raise NotConnected(org_id)

    def calendar(self, org_id: str):
        self._credentials_present(org_id)
        client_id, client_secret = require_app_identity()
        resolver = CredentialStoreCalendarResolver(self._store, client_id=client_id, client_secret=client_secret)
        return get_calendar_adapter(resolver, tenant_id=org_id)

    def drive(self, org_id: str):
        self._credentials_present(org_id)
        client_id, client_secret = require_app_identity()
        creds = CredentialStoreDriveResolver(self._store, client_id=client_id, client_secret=client_secret).get_credentials(org_id)
        if creds is None:
            raise NotConnected(org_id)
        return make_drive_reader(oauth_credentials=creds)
