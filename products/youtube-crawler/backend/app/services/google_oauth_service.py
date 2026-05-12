"""Google OAuth orchestration for youtube-crawler.

Phase 1 of `youtube-crawler-domain-implementation` (see PROJECT.md §6 Phase 1).

VERIFY-THE-SEED-SHIPS-IT (read 2026-05-11)
------------------------------------------
- `noctusai_lib.security.oauth` — ships `OAuthProvider` Protocol +
  `GoogleProvider` (Real) + `FakeOAuthProvider` (Fake) + `make_oauth_provider`
  (factory) + `oauth_router` (generic 4-endpoint mount). The seed is
  runtime-ready; this product is N=2 consumer (media-scheduling was N=1).
- `noctusai_lib.security.encrypted_tokens` — ships `encrypt` / `decrypt` /
  `generate_key`. Runtime-ready.

This service is the product-specific persistence + lifecycle wrapper. The
brief specifies endpoints under `/api/credentials/...` (NOT the seed's
`/api/oauth/google/...` path) — operator-facing UI shape — so we wire a
product-scoped router that delegates token-exchange to `GoogleProvider`
and persistence to the `youtube_crawler.google_credentials` table.

SCOPES (locked Q5)
------------------
- `https://www.googleapis.com/auth/youtube.upload` — narrow upload-only.
- `https://www.googleapis.com/auth/drive.readonly` — readonly Drive for the
  drop-folder watcher (Phase 2).

Why not full YouTube? Narrow scopes limit blast radius if creds leak.

STATE / CSRF
------------
The OAuth `state` parameter is a opaque CSRF nonce. We persist it on the
credential row (`state_nonce` + `state_expires_at`) at `initiate` time and
verify on callback. Without this, a malicious site could trick a logged-in
user into binding the attacker's Google account.

LGPD
----
- `email` is plaintext PII (operator's Google account).
- `refresh_token_encrypted` + `access_token_encrypted` are Fernet ciphertexts.
- All writes go through `noctus.dev.lgpd_flag` — see `LGPD-WARNINGS.md`.
"""
from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from noctusai_lib.security.oauth import (
    AuthorizationURL,
    OAuthProvider,
    TokenSet,
    make_oauth_provider,
)

from app.services.credential_vault import VaultService

logger = logging.getLogger(__name__)


# Locked in PROJECT.md §7 Q5 — narrow scopes.
DEFAULT_SCOPES: tuple[str, ...] = (
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/drive.readonly",
)

# State nonce TTL — generous enough for a human consent flow, short enough
# that a leaked nonce stops being useful quickly. 10 minutes matches what
# Google's own examples use.
STATE_TTL = timedelta(minutes=10)


@dataclass(frozen=True)
class ConnectionStatus:
    """Snapshot of the operator's Google connection state.

    Fields are deliberately non-secret — designed to be returned to the
    frontend without decrypting any token. `email` IS PII; the
    credentials_router is RLS-scoped so only the operator's own org sees it.
    """

    connected: bool
    email: str | None
    scopes: list[str]
    connected_at: datetime | None
    revoked_at: datetime | None


class GoogleOAuthService:
    """Orchestrates the Google OAuth dance for one operator at a time.

    The service is stateless w.r.t. user — every method takes
    `(org_id, user_id)` so it can be shared across requests.

    Constructor takes the OAuth provider (real or fake), the vault, and a
    Supabase client factory. The factory shape mirrors the rest of the
    product: a no-arg callable returning the admin client (RLS bypass) so
    we can write encrypted rows under the operator's org without needing
    their JWT at callback time (the callback rides on the URL, not a
    bearer header).

    Args:
        provider: an `OAuthProvider` (GoogleProvider in prod, FakeOAuthProvider
            in tests / FakeMode).
        vault: the `VaultService` for encrypt-at-write / decrypt-at-read.
        get_admin_client: no-arg callable returning the Supabase admin client.
        schema: the product schema name; defaults to "youtube_crawler".
        scopes: the OAuth scope list; defaults to `DEFAULT_SCOPES`.
    """

    def __init__(
        self,
        provider: OAuthProvider,
        vault: VaultService,
        get_admin_client,
        *,
        schema: str = "youtube_crawler",
        scopes: tuple[str, ...] | list[str] = DEFAULT_SCOPES,
    ) -> None:
        self._provider = provider
        self._vault = vault
        self._get_admin_client = get_admin_client
        self._schema = schema
        self._scopes = list(scopes)

    # ─── Initiate (authorize URL) ────────────────────────────────────────────

    async def initiate(
        self,
        *,
        org_id: str,
        user_id: str,
        redirect_uri: str,
    ) -> AuthorizationURL:
        """Generate the Google consent URL + persist the CSRF nonce.

        The nonce rides as the `state` query param; on callback we look it
        up and verify expiry. The row is INSERT-or-UPDATE on `(org_id,
        user_id)` — calling `initiate` twice in a row overwrites the prior
        nonce (the prior dance is abandoned).
        """
        state = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + STATE_TTL

        # Persist the nonce so callback can verify it (CSRF guard). Email +
        # token columns stay NULL/empty until callback completes.
        client = self._get_admin_client()
        existing = (
            client.schema(self._schema)
            .table("google_credentials")
            .select("id")
            .eq("org_id", org_id)
            .eq("user_id", user_id)
            .execute()
        )
        if existing.data:
            (
                client.schema(self._schema)
                .table("google_credentials")
                .update({
                    "state_nonce": state,
                    "state_expires_at": expires_at.isoformat(),
                    "revoked_at": None,  # re-arming a previously-revoked row
                })
                .eq("org_id", org_id)
                .eq("user_id", user_id)
                .execute()
            )
        else:
            (
                client.schema(self._schema)
                .table("google_credentials")
                .insert({
                    "org_id": org_id,
                    "user_id": user_id,
                    "email": "",                     # backfilled at callback
                    "refresh_token_encrypted": "",   # backfilled at callback
                    "scopes": [],
                    "state_nonce": state,
                    "state_expires_at": expires_at.isoformat(),
                })
                .execute()
            )

        logger.info(
            "google_oauth: initiated for org=%s user=%s scopes=%s",
            org_id,
            user_id,
            self._scopes,
        )
        return await self._provider.authorization_url(
            state=state,
            scopes=self._scopes,
            redirect_uri=redirect_uri,
        )

    # ─── Callback (exchange + persist) ───────────────────────────────────────

    async def handle_callback(
        self,
        *,
        code: str,
        state: str,
        redirect_uri: str,
    ) -> tuple[str, str]:
        """Verify state, exchange code, persist encrypted tokens.

        Returns the (org_id, user_id) the row resolved to so the router can
        echo it in the response. Raises `ValueError` on any failure (unknown
        state, expired state, missing refresh_token) so the router maps it
        to a 4xx with a clear reason.
        """
        client = self._get_admin_client()
        row = (
            client.schema(self._schema)
            .table("google_credentials")
            .select("id, org_id, user_id, state_nonce, state_expires_at")
            .eq("state_nonce", state)
            .limit(1)
            .execute()
        )
        if not row.data:
            raise ValueError("unknown or expired state nonce")
        record = row.data[0]
        expires_str = record.get("state_expires_at")
        if expires_str:
            expires_at = _parse_isoformat(expires_str)
            if datetime.now(timezone.utc) > expires_at:
                raise ValueError("state nonce expired; restart the OAuth flow")

        org_id = record["org_id"]
        user_id = record["user_id"]

        # External-service call — patched at the `OAuthProvider` boundary in
        # tests (no monkey-patching of our own code).
        tokens: TokenSet = await self._provider.exchange_code(
            code=code, state=state, redirect_uri=redirect_uri
        )

        if not tokens.refresh_token:
            # Google omits refresh_token on subsequent grants without
            # prompt=consent. GoogleProvider always sets prompt=consent, but
            # if the user previously revoked + reconsented quickly Google
            # sometimes still skips the refresh_token. Surface as a clear
            # error rather than persisting an unusable row.
            raise ValueError(
                "Google did not return a refresh_token. Revoke this app's "
                "access at https://myaccount.google.com/permissions and try "
                "connecting again."
            )

        # Best-effort retrieval of the operator's email from token id_token /
        # raw response. Google attaches `id_token` when `openid` scope is
        # requested; we don't request openid in DEFAULT_SCOPES (narrow-scope
        # rule), so fall back to "" and let a downstream call to the userinfo
        # endpoint backfill it later. For Phase 1 the column accepts ""
        # (NOT NULL but no length constraint).
        email = _email_from_raw(tokens.raw)

        refresh_ct = self._vault.encrypt(tokens.refresh_token)
        access_ct = self._vault.encrypt(tokens.access_token)

        (
            client.schema(self._schema)
            .table("google_credentials")
            .update({
                "email": email,
                "refresh_token_encrypted": refresh_ct,
                "access_token_encrypted": access_ct,
                "access_token_expires_at": tokens.expires_at.isoformat(),
                "scopes": tokens.scope or self._scopes,
                "state_nonce": None,
                "state_expires_at": None,
                "connected_at": datetime.now(timezone.utc).isoformat(),
                "revoked_at": None,
            })
            .eq("org_id", org_id)
            .eq("user_id", user_id)
            .execute()
        )
        logger.info(
            "google_oauth: connected org=%s user=%s scopes=%s",
            org_id,
            user_id,
            tokens.scope,
        )
        return org_id, user_id

    # ─── Disconnect ──────────────────────────────────────────────────────────

    async def disconnect(self, *, org_id: str, user_id: str) -> bool:
        """Revoke the refresh token at Google + mark the row revoked.

        Returns True if a row was found and marked revoked, False if no
        active connection exists (idempotent: calling disconnect on an
        already-disconnected user returns False but does not raise).
        """
        client = self._get_admin_client()
        row = (
            client.schema(self._schema)
            .table("google_credentials")
            .select("id, refresh_token_encrypted, revoked_at")
            .eq("org_id", org_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        if not row.data:
            return False
        record = row.data[0]
        if record.get("revoked_at"):
            return False

        ciphertext = record.get("refresh_token_encrypted") or ""
        if ciphertext:
            try:
                refresh_token = self._vault.decrypt(ciphertext)
                await self._provider.revoke(refresh_token)
            except Exception as exc:  # noqa: BLE001 — revoke best-effort
                # Revocation failure at the provider is not fatal — we still
                # mark the row revoked so the operator's product state is
                # truthful. The provider will eventually expire the token.
                logger.warning(
                    "google_oauth: revoke at provider failed (continuing to mark "
                    "row revoked locally): %s",
                    exc,
                )

        (
            client.schema(self._schema)
            .table("google_credentials")
            .update({
                "revoked_at": datetime.now(timezone.utc).isoformat(),
                "refresh_token_encrypted": "",
                "access_token_encrypted": None,
                "access_token_expires_at": None,
                "state_nonce": None,
                "state_expires_at": None,
            })
            .eq("org_id", org_id)
            .eq("user_id", user_id)
            .execute()
        )
        logger.info("google_oauth: disconnected org=%s user=%s", org_id, user_id)
        return True

    # ─── Status ──────────────────────────────────────────────────────────────

    async def status(self, *, org_id: str, user_id: str) -> ConnectionStatus:
        """Return a non-secret snapshot of the operator's connection."""
        client = self._get_admin_client()
        row = (
            client.schema(self._schema)
            .table("google_credentials")
            .select("email, scopes, connected_at, revoked_at, refresh_token_encrypted")
            .eq("org_id", org_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        if not row.data:
            return ConnectionStatus(
                connected=False, email=None, scopes=[], connected_at=None, revoked_at=None
            )
        rec = row.data[0]
        connected = bool(
            rec.get("refresh_token_encrypted") and not rec.get("revoked_at")
        )
        return ConnectionStatus(
            connected=connected,
            email=rec.get("email") or None,
            scopes=list(rec.get("scopes") or []),
            connected_at=_parse_isoformat_or_none(rec.get("connected_at")),
            revoked_at=_parse_isoformat_or_none(rec.get("revoked_at")),
        )


# ─── Factory ─────────────────────────────────────────────────────────────────


def make_google_oauth_service(
    *,
    vault: VaultService,
    get_admin_client,
    client_id: str,
    client_secret: str,
    use_fake: bool = False,
    schema: str = "youtube_crawler",
    scopes: tuple[str, ...] | list[str] = DEFAULT_SCOPES,
) -> GoogleOAuthService:
    """Construct a fully-wired `GoogleOAuthService`.

    Args:
        vault: a `VaultService` instance.
        get_admin_client: no-arg callable returning the Supabase admin client.
        client_id: Google OAuth Client ID. Required when `use_fake=False`.
        client_secret: Google OAuth Client Secret. Required when `use_fake=False`.
        use_fake: when True, returns a service wired with `FakeOAuthProvider`
            (network-free; for dev / FakeMode). Tests typically construct
            `GoogleOAuthService` directly with a Fake instead of going through
            this factory.
        schema: the product schema; defaults to "youtube_crawler".
        scopes: the OAuth scope list; defaults to `DEFAULT_SCOPES`.

    Raises:
        ValueError: when `use_fake=False` and `client_id`/`client_secret`
            are missing — propagated from `make_oauth_provider`.
    """
    provider = make_oauth_provider(
        name="google",
        use_fake=use_fake,
        client_id=client_id,
        client_secret=client_secret,
    )
    return GoogleOAuthService(
        provider=provider,
        vault=vault,
        get_admin_client=get_admin_client,
        schema=schema,
        scopes=scopes,
    )


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _parse_isoformat(value: str) -> datetime:
    """Parse an ISO-8601 string into a tz-aware datetime.

    Supabase returns timestamps with a trailing 'Z' or '+00:00'. Python's
    `fromisoformat` since 3.11 accepts both; we coerce to UTC defensively.
    """
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _parse_isoformat_or_none(value: str | None) -> datetime | None:
    if value is None or value == "":
        return None
    try:
        return _parse_isoformat(value)
    except (ValueError, TypeError):
        logger.warning("google_oauth: could not parse timestamp %r", value)
        return None


def _email_from_raw(raw: dict[str, Any] | None) -> str:
    """Best-effort: pull `email` from a Google token response raw dict.

    Without `openid` scope (which we intentionally don't request), Google's
    token response carries no email. Returns "" when absent — the column
    is NOT NULL but accepts empty string. A future Phase can call
    `https://www.googleapis.com/oauth2/v2/userinfo` with the access_token
    to backfill the email; out of Phase 1 scope.
    """
    if not raw:
        return ""
    return str(raw.get("email") or "")


__all__ = [
    "ConnectionStatus",
    "DEFAULT_SCOPES",
    "GoogleOAuthService",
    "STATE_TTL",
    "make_google_oauth_service",
]
