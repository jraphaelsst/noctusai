"""Multi-account YouTube credential routing — the consumption seam.

The multi-account framework (``integration_accounts`` table +
``IntegrationAccountService``) stores N YouTube channels per org, but
every YouTube *operation* (upload / list / chatbot) goes through
``YouTubeService``, which speaks the seed ``CredentialStore`` Protocol
(single-row-per-(org, provider)). Before this module, those operations
read the legacy single-account ``credentials`` table — so picking a
"default" account in the UI had no effect on which channel a video
went to.

This module closes that gap WITHOUT touching ``YouTubeService``: it
provides a ``CredentialStore``-shaped adapter
(:class:`MultiAccountYouTubeStore`) that, per call, resolves the org's
**default** ``integration_accounts`` YouTube row and reads/refreshes
THAT row's encrypted bundle. Because the seed Protocol passes ``org_id``
on every ``get`` / ``put`` / ``delete``, the adapter stays org-agnostic
at construction — it slots into the exact place ``build_credential_store``
used to.

Design rule (memory feedback_seed_shape_vs_primitive_consume): the seed
``CredentialStore`` is single-row-per-(org, provider); multi-account is a
product-local shape. This adapter BRIDGES the two via one named seam — it
is NOT a fork of the Protocol (it implements it) and NOT a fork of the
crypto (encryption stays in ``IntegrationAccountService`` →
``credential_vault.require_fernet`` → seed Fernet).

Onboarding an EXISTING single-account connection is a separate, explicit
step — see ``app.services.legacy_adoption.adopt_legacy_account`` (the
canonical "adopt existing connection" path, YouTube as pilot #1). This
consume path NEVER adopts implicitly: if the org has no
``integration_accounts`` YouTube row, ``get`` returns ``None`` (honest
"not connected") and the operator adopts/connects via the UI.
"""
from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from app.services.credential_vault import CredentialStore, StoredCredential
from app.services.integration_account_service import (
    IntegrationAccount,
    IntegrationAccountService,
    build_integration_account_service,
)
from app.modules.youtube.services.youtube import YouTubeService

logger = logging.getLogger(__name__)

__all__ = [
    "MultiAccountYouTubeStore",
    "build_multi_account_youtube_store",
    "build_youtube_service_for_org",
    "resolve_default_youtube_account",
]

_PROVIDER = "youtube"


def _coerce_org(org_id: Any) -> UUID:
    if isinstance(org_id, UUID):
        return org_id
    return UUID(str(org_id))


def resolve_default_youtube_account(
    svc: IntegrationAccountService,
    org_id: UUID,
) -> Optional[IntegrationAccount]:
    """Resolve the org's active YouTube account: its default row, else the
    sole row, else ``None``. Reads ``integration_accounts`` only — adoption
    of a legacy connection is an explicit step (see ``legacy_adoption``).
    """
    accounts = svc.list_accounts(org_id, provider=_PROVIDER)
    if not accounts:
        return None
    return next((a for a in accounts if a.is_default), accounts[0])


class MultiAccountYouTubeStore:
    """A :class:`CredentialStore`-shaped view that routes ``(org, 'youtube')``
    to that org's DEFAULT ``integration_accounts`` YouTube row, resolved
    per call. Slots into ``YouTubeService(credential_store=...)`` unchanged.

    Only the ``youtube`` provider is handled; any other provider behaves as
    "not connected" (``get`` → ``None``) — ``YouTubeService`` only ever asks
    for ``youtube``.
    """

    def __init__(self, svc: IntegrationAccountService):
        self._svc = svc

    def _resolve(self, org_id: str) -> Optional[IntegrationAccount]:
        return resolve_default_youtube_account(self._svc, _coerce_org(org_id))

    # ─── CredentialStore Protocol ──────────────────────────────────────
    def get(self, org_id: str, provider: str) -> Optional[StoredCredential]:
        if provider != _PROVIDER:
            return None
        account = self._resolve(org_id)
        if account is None:
            return None
        bundle = self._svc.decrypt_credential(account.id, account.org_id)
        return StoredCredential(
            org_id=str(account.org_id),
            provider=_PROVIDER,
            tokens=bundle,
            created_at=account.created_at,
            updated_at=account.updated_at,
            metadata=dict(account.metadata or {}),
        )

    def put(
        self,
        org_id: str,
        provider: str,
        tokens: dict,
        *,
        metadata: Optional[dict] = None,
    ) -> StoredCredential:
        """Persist a refreshed bundle back to the resolved account row.

        This is the token-refresh path: ``YouTubeService._fresh_credentials``
        rotates the access token and calls ``put`` to persist it. We write
        the re-encrypted bundle to the SAME account ``get`` resolved.
        """
        if provider != _PROVIDER:
            raise ValueError(
                f"MultiAccountYouTubeStore only handles 'youtube', got {provider!r}"
            )
        account = self._resolve(org_id)
        if account is None:
            # No account to persist to — should not happen on a refresh path
            # (get returned a credential first). Fail loud rather than silently
            # dropping the refreshed token.
            raise RuntimeError(
                f"no default YouTube integration_account for org {org_id} — "
                "cannot persist refreshed token"
            )
        updated = self._svc.update_credential(
            account.id, account.org_id, tokens, metadata=metadata
        )
        return StoredCredential(
            org_id=str(updated.org_id),
            provider=_PROVIDER,
            tokens=dict(tokens),
            created_at=updated.created_at,
            updated_at=updated.updated_at,
            metadata=dict(updated.metadata or {}),
        )

    def delete(self, org_id: str, provider: str) -> bool:
        if provider != _PROVIDER:
            return False
        account = self._resolve(org_id)
        if account is None:
            return False
        return self._svc.delete_account(account.id, account.org_id)

    def list_providers(self, org_id: str) -> list[str]:
        accounts = self._svc.list_accounts(_coerce_org(org_id), provider=_PROVIDER)
        return [_PROVIDER] if accounts else []


def build_multi_account_youtube_store(
    admin_client: Any,
    cfg: Any,
) -> CredentialStore:
    """Build the multi-account YouTube credential store.

    Mirrors ``build_credential_store``'s construction-site ergonomics: it
    validates the Fernet key loudly (via ``build_integration_account_service``
    → ``require_fernet``), so a missing ``ENCRYPTION_KEY`` raises
    ``EncryptionNotConfigured`` exactly where the legacy store did — the
    callers' existing 503-on-config-gap handling is preserved unchanged.
    """
    svc = build_integration_account_service(
        admin_client, encryption_key=cfg.encryption_key
    )
    return MultiAccountYouTubeStore(svc)


def build_youtube_service_for_org(admin_client: Any, cfg: Any) -> YouTubeService:
    """Canonical ``YouTubeService`` factory wired to the multi-account store.

    Absorbs the N=4 ``build_…store(...)`` + ``YouTubeService(...)`` recurrence
    that every YouTube call-site (upload / videos / chat / whatsapp) carried.
    Raises the same exceptions the inlined form did
    (``EncryptionNotConfigured`` from the store build, ``YouTubeServiceError``
    from the service ctor), so each call-site keeps its own error policy
    (503 vs. degrade-to-optional) unchanged.
    """
    store = build_multi_account_youtube_store(admin_client, cfg)
    return YouTubeService(
        client_id=cfg.youtube_client_id,
        client_secret=cfg.youtube_client_secret,
        redirect_uri=cfg.youtube_redirect_uri,
        credential_store=store,
    )
