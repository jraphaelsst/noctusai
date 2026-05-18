"""`CredentialStore`-backed resolver bridges + OAuth-callback write seam.

WHY this module
---------------
The integration adapters (`google_calendar`, `meta`, `google_drive`)
each consume a per-tenant resolver Protocol
(`CalendarCredentialResolver`, `MetaCredentialResolver`, …). The
canonical encrypted persistence is
`noctusai_lib.security.token_store.CredentialStore`
(`get / put / delete / list_providers`). Without this module every
OAuth-using product hand-rolls the *same* glue twice:

1. A class wrapping a `CredentialStore` to satisfy each adapter's
   resolver Protocol (read side — Prereq-2 of
   `projects/seed-adapter-convergence/`).
2. An `oauth_router(on_callback=)` hook that writes the exchanged
   token bundle into the `CredentialStore` under a per-provider key
   (write side — Prereq-3).

This module ships both, single-sourced, so consumers pass the seed
`CredentialStore` directly (`credential_store=`) instead of each
re-implementing the bridge. N≥2 (social-wiring is the first; therapy
+ PF have tokenized integrations queued) → seed formalize per the
recurrence rule.

Provider constants
------------------
`CALENDAR_PROVIDER` / `META_PROVIDER` / `DRIVE_PROVIDER` are the
canonical `provider` keys for the `(org_id, provider)` natural key —
single-sourced here so the OAuth-callback write path and the adapter
read path can never drift to mismatched strings (the silent
"connected but no data" failure mode).

Token-bundle schema
--------------------
The store is bundle-agnostic (`token_store` encrypts the JSON blob
opaque). These bridges assume the bundle the OAuth callback wrote:
`{"access_token": ..., "refresh_token": ..., "expiry": ...,
"scope": ...}`. `metadata` carries the small non-secret extras
(`channel_id` / `channel_title` / `scopes`) that older product code
stored as columns — they ride in the `token_store` `metadata` dict,
no schema change required.

Fake-exempt? No — these bridges compose a real IO seam
(`CredentialStore`). They are tested against `FakeCredentialStore`
(the seam's own Fake), which is the canonical pattern: the bridge has
no IO of its own, so a dedicated Fake here would exercise no
different code than the bridge over `FakeCredentialStore` already
does.
"""

from __future__ import annotations

import logging
from typing import Awaitable, Callable

from noctusai_lib.integrations.google_calendar.credentials import (
    OAuthCalendarCredentials,
)
from noctusai_lib.integrations.meta.credentials import OAuthMetaCredentials
from noctusai_lib.security.oauth.types import OAuthCallbackResult
from noctusai_lib.security.token_store import CredentialStore

logger = logging.getLogger(__name__)


# ─── Canonical provider keys ──────────────────────────────────────────────

CALENDAR_PROVIDER = "google_calendar"
META_PROVIDER = "meta"
DRIVE_PROVIDER = "google_drive"


# ─── Read side — CredentialStore → adapter resolver Protocols ─────────────


class CredentialStoreCalendarResolver:
    """Satisfies `CalendarCredentialResolver` from a `CredentialStore`.

    Reads the `(org_id, CALENDAR_PROVIDER)` bundle and shapes it into
    `OAuthCalendarCredentials`. `client_id` / `client_secret` are the
    product's OAuth-client app identity (NOT per-tenant) so they're
    constructor args, not stored in the per-tenant bundle.

    Returns `None` when there is no stored credential — the calendar
    factory then falls back to `FakeCalendarAdapter`.
    """

    def __init__(
        self,
        store: CredentialStore,
        *,
        client_id: str,
        client_secret: str,
        provider: str = CALENDAR_PROVIDER,
    ) -> None:
        self._store = store
        self._client_id = client_id
        self._client_secret = client_secret
        self._provider = provider

    def get_credentials(
        self, tenant_id: str | None = None
    ) -> OAuthCalendarCredentials | None:
        if tenant_id is None:
            return None
        stored = self._store.get(tenant_id, self._provider)
        if stored is None:
            return None
        tokens = stored.tokens
        refresh_token = tokens.get("refresh_token")
        if not refresh_token:
            logger.warning(
                "stored calendar credential for org=%s has no refresh_token; "
                "treating as not-connected",
                tenant_id,
            )
            return None
        scopes = stored.metadata.get("scopes") if stored.metadata else None
        kwargs: dict = {
            "refresh_token": refresh_token,
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "token": tokens.get("access_token"),
        }
        if scopes:
            kwargs["scopes"] = list(scopes)
        return OAuthCalendarCredentials(**kwargs)


class CredentialStoreMetaResolver:
    """Satisfies `MetaCredentialResolver` from a `CredentialStore`.

    Reads the `(org_id, META_PROVIDER)` bundle and shapes it into
    `OAuthMetaCredentials`. Meta persists only the long-lived user
    token (Page tokens are refetched per adapter construction)."""

    def __init__(
        self,
        store: CredentialStore,
        *,
        provider: str = META_PROVIDER,
    ) -> None:
        self._store = store
        self._provider = provider

    def get_credentials(
        self, org_id: str | None = None
    ) -> OAuthMetaCredentials | None:
        if org_id is None:
            return None
        stored = self._store.get(org_id, self._provider)
        if stored is None:
            return None
        access_token = stored.tokens.get("access_token")
        if not access_token:
            logger.warning(
                "stored meta credential for org=%s has no access_token; "
                "treating as not-connected",
                org_id,
            )
            return None
        meta = stored.metadata or {}
        return OAuthMetaCredentials(
            access_token=access_token,
            user_id=meta.get("user_id"),
            user_name=meta.get("user_name"),
        )


# ─── Write side — oauth_router on_callback → CredentialStore ──────────────

ProviderMap = dict[str, str]


def make_token_persisting_callback(
    store: CredentialStore,
    *,
    org_id_from_state: Callable[[str], str],
    provider_map: ProviderMap | None = None,
) -> Callable[[OAuthCallbackResult], Awaitable[None]]:
    """Build an `oauth_router(on_callback=)` hook that persists tokens.

    On a successful exchange the hook writes the token bundle into
    `store` under `(org_id, provider)`. `org_id` is derived from the
    OAuth `state` via `org_id_from_state` (products embed the org in
    the state param when starting the dance — the router is
    org-agnostic by design).

    `provider_map` optionally maps the OAuth provider name (the path
    segment, e.g. `"google"`) to the storage provider key (e.g.
    `CALENDAR_PROVIDER`). When omitted the provider name is stored
    verbatim.

    Failures (a missing org in the state, a store write error) are
    logged and re-raised so the router surfaces them in the callback
    response — never a silent swallow (a silently-dropped token write
    is the worst failure mode here: the user sees "connected" but no
    data ever loads).
    """

    pmap = dict(provider_map or {})

    async def _on_callback(result: OAuthCallbackResult) -> None:
        if result.error is not None or result.tokens is None:
            # Router already surfaces the error; nothing to persist.
            return
        org_id = org_id_from_state(result.state)
        provider = pmap.get(result.provider, result.provider)
        tokens = result.tokens
        bundle: dict = {
            "access_token": tokens.access_token,
            "refresh_token": tokens.refresh_token,
            "expiry": (
                tokens.expires_at.isoformat()
                if tokens.expires_at is not None
                else None
            ),
            "scope": tokens.scope,
        }
        store.put(org_id, provider, bundle)
        logger.info(
            "persisted OAuth tokens for org=%s provider=%s", org_id, provider
        )

    return _on_callback


__all__ = [
    "CALENDAR_PROVIDER",
    "CredentialStoreCalendarResolver",
    "CredentialStoreMetaResolver",
    "DRIVE_PROVIDER",
    "META_PROVIDER",
    "make_token_persisting_callback",
]
