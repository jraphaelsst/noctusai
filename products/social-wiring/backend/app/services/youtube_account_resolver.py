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

Auto-migration: the first time an org with a legacy single-account
YouTube credential is resolved (and it has no ``integration_accounts``
YouTube row yet), the legacy bundle is copied into an
``integration_accounts`` row (``is_default=True``) so existing
connections keep working AND show up as a card in the unified UI. The
legacy row is left in place as a transition-safety fallback.
"""
from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from app.services.credential_vault import (
    CredentialStore,
    StoredCredential,
    build_credential_store,
)
from app.services.integration_account_service import (
    IntegrationAccount,
    IntegrationAccountService,
    build_integration_account_service,
)

logger = logging.getLogger(__name__)

__all__ = [
    "MultiAccountYouTubeStore",
    "build_multi_account_youtube_store",
    "migrate_legacy_youtube_account",
    "resolve_default_youtube_account",
]

_PROVIDER = "youtube"


def _coerce_org(org_id: Any) -> UUID:
    if isinstance(org_id, UUID):
        return org_id
    return UUID(str(org_id))


def migrate_legacy_youtube_account(
    admin_client: Any,
    svc: IntegrationAccountService,
    org_id: UUID,
    cfg: Any,
    *,
    legacy_store: Optional[CredentialStore] = None,
) -> Optional[IntegrationAccount]:
    """Idempotently copy a legacy single-account YouTube credential into
    ``integration_accounts`` (``is_default=True``).

    Returns the new (or pre-existing) default account, or ``None`` when
    there is nothing to migrate. Safe to call repeatedly: it only acts
    when the org has ZERO ``integration_accounts`` YouTube rows AND a
    legacy ``credentials`` row exists.

    ``legacy_store`` is a DI seam (KB § PATTERNS/di-test-seam.md): tests
    inject the seed ``FakeCredentialStore``; production builds the real
    ``credentials``-backed store from ``admin_client``.
    """
    existing = svc.list_accounts(org_id, provider=_PROVIDER)
    if existing:
        # Already multi-account — nothing to migrate. Hand back the default.
        return next((a for a in existing if a.is_default), existing[0])

    if legacy_store is None:
        try:
            legacy_store = build_credential_store(
                admin_client, encryption_key=cfg.encryption_key
            )
        except Exception as exc:  # EncryptionNotConfigured et al.
            logger.warning(
                "youtube_account_resolver: cannot read legacy creds for migration "
                "(org=%s): %s",
                org_id,
                exc,
            )
            return None

    record = legacy_store.get(str(org_id), _PROVIDER)
    if record is None:
        return None

    label = (
        record.metadata.get("channel_title")
        or f"YouTube ({org_id})"
    )
    metadata = {
        k: record.metadata.get(k)
        for k in ("channel_id", "channel_title", "scopes")
        if record.metadata.get(k)
    }
    try:
        account = svc.create_account(
            org_id=org_id,
            provider=_PROVIDER,
            account_label=label,
            credential_dict=record.tokens,
            metadata=metadata,
            is_default=True,
        )
        logger.info(
            "youtube_account_resolver: migrated legacy single-account YouTube "
            "credential into integration_accounts for org=%s (account=%s, label=%r)",
            org_id,
            account.id,
            label,
        )
        return account
    except Exception as exc:  # unique-violation race / concurrent migration
        logger.warning(
            "youtube_account_resolver: legacy migration insert failed for org=%s "
            "(%s) — re-reading accounts in case of a concurrent migration",
            org_id,
            exc,
        )
        again = svc.list_accounts(org_id, provider=_PROVIDER)
        if again:
            return next((a for a in again if a.is_default), again[0])
        return None


def resolve_default_youtube_account(
    admin_client: Any,
    svc: IntegrationAccountService,
    org_id: UUID,
    cfg: Any,
    *,
    auto_migrate: bool = True,
    legacy_store: Optional[CredentialStore] = None,
) -> Optional[IntegrationAccount]:
    """Resolve the org's active YouTube account: its default row, else the
    sole row, else (after optional legacy auto-migration) ``None``.
    """
    accounts = svc.list_accounts(org_id, provider=_PROVIDER)
    if not accounts and auto_migrate:
        migrated = migrate_legacy_youtube_account(
            admin_client, svc, org_id, cfg, legacy_store=legacy_store
        )
        if migrated is not None:
            accounts = [migrated]
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

    def __init__(
        self,
        svc: IntegrationAccountService,
        admin_client: Any,
        cfg: Any,
        *,
        auto_migrate: bool = True,
        legacy_store: Optional[CredentialStore] = None,
    ):
        self._svc = svc
        self._admin = admin_client
        self._cfg = cfg
        self._auto_migrate = auto_migrate
        self._legacy_store = legacy_store

    def _resolve(self, org_id: str) -> Optional[IntegrationAccount]:
        org = _coerce_org(org_id)
        return resolve_default_youtube_account(
            self._admin,
            self._svc,
            org,
            self._cfg,
            auto_migrate=self._auto_migrate,
            legacy_store=self._legacy_store,
        )

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
        org = _coerce_org(org_id)
        accounts = self._svc.list_accounts(org, provider=_PROVIDER)
        return [_PROVIDER] if accounts else []


def build_multi_account_youtube_store(
    admin_client: Any,
    cfg: Any,
    *,
    auto_migrate: bool = True,
    legacy_store: Optional[CredentialStore] = None,
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
    return MultiAccountYouTubeStore(
        svc, admin_client, cfg, auto_migrate=auto_migrate, legacy_store=legacy_store
    )
