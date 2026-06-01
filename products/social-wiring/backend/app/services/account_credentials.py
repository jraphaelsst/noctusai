"""Canonical multi-account credential + service factory — ALL providers.

ONE place that builds the per-org, multi-account **credential store** for any
integration provider, and (where a multi-account-aware service exists) the
**service** wired to it. Replaces the N call-sites that each hand-built a store
+ service. YouTube is wired today; ``google_drive`` / ``gmail`` / ``meta`` /
``google_calendar`` register here as they graduate to multi-account — increment
this ONE registry, not the call-sites.

Two layers:
  1. ``build_credential_store(provider, ...)`` — the GENERIC credentials builder.
     Returns a :class:`MultiAccountCredentialStore` that resolves the org's
     DEFAULT ``integration_accounts`` row for ``provider`` per call. Works for
     ANY provider today (the store is provider-parametrized).
  2. ``build_service_for_org(provider, ...)`` — the per-provider SERVICE factory
     registry. A provider is "wired" once it has a multi-account-aware service
     class + a factory entry in ``_SERVICE_FACTORIES``. Unwired providers raise
     a clear ``ProviderNotWired`` (honest, not a silent fallback).

Design (memory feedback_seed_shape_vs_primitive_consume + feedback_framework_consume_wire_and_apply_gap):
  the store IMPLEMENTS the seed ``CredentialStore`` Protocol (org_id flows
  per-call → org-agnostic at construction), so a provider's existing service —
  which already speaks that Protocol — consumes multi-account WITHOUT being
  forked. Onboarding an existing single-account connection is the separate,
  explicit ``legacy_adoption.adopt_legacy_account`` step.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional
from uuid import UUID

from app.services.credential_vault import CredentialStore, StoredCredential
from app.services.integration_account_service import (
    IntegrationAccount,
    IntegrationAccountService,
    build_integration_account_service,
)

logger = logging.getLogger(__name__)

__all__ = [
    "MultiAccountCredentialStore",
    "ProviderNotWired",
    "build_credential_store",
    "build_service_for_org",
    "build_youtube_service_for_org",
    "resolve_default_account",
    "register_service_factory",
]


class ProviderNotWired(Exception):
    """Raised when ``build_service_for_org`` is asked for a provider that has
    no multi-account-aware service factory registered yet. Honest signal —
    the credential store still builds; only the service wrapper is pending."""


def _coerce_org(org_id: Any) -> UUID:
    return org_id if isinstance(org_id, UUID) else UUID(str(org_id))


def resolve_default_account(
    svc: IntegrationAccountService,
    org_id: UUID,
    provider: str,
) -> Optional[IntegrationAccount]:
    """The org's active account for ``provider``: its default row, else the
    sole row, else ``None``. Reads ``integration_accounts`` only — adoption of
    a legacy connection is an explicit step (see ``legacy_adoption``)."""
    accounts = svc.list_accounts(org_id, provider=provider)
    if not accounts:
        return None
    return next((a for a in accounts if a.is_default), accounts[0])


class MultiAccountCredentialStore:
    """A :class:`CredentialStore`-shaped view bound to ONE ``provider`` that
    routes ``(org, provider)`` to that org's DEFAULT ``integration_accounts``
    row, resolved per call. Slots into any consumer that takes a
    ``credential_store=`` (the seed Protocol) — unchanged.

    Answers only for its bound ``provider``; any other provider behaves as
    "not connected" (``get`` → ``None``). Consumers always pass their own
    provider, so this matches by construction.
    """

    def __init__(self, svc: IntegrationAccountService, provider: str):
        self._svc = svc
        self._provider = provider

    def _resolve(self, org_id: str) -> Optional[IntegrationAccount]:
        return resolve_default_account(self._svc, _coerce_org(org_id), self._provider)

    # ─── CredentialStore Protocol ──────────────────────────────────────
    def get(self, org_id: str, provider: str) -> Optional[StoredCredential]:
        if provider != self._provider:
            return None
        account = self._resolve(org_id)
        if account is None:
            return None
        bundle = self._svc.decrypt_credential(account.id, account.org_id)
        return StoredCredential(
            org_id=str(account.org_id),
            provider=self._provider,
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
        """Persist a refreshed bundle back to the resolved account row (the
        token-refresh path: a service rotates the access token and calls
        ``put``). Writes to the SAME account ``get`` resolved."""
        if provider != self._provider:
            raise ValueError(
                f"MultiAccountCredentialStore[{self._provider}] cannot persist "
                f"provider {provider!r}"
            )
        account = self._resolve(org_id)
        if account is None:
            raise RuntimeError(
                f"no default {self._provider} integration_account for org "
                f"{org_id} — cannot persist refreshed token"
            )
        updated = self._svc.update_credential(
            account.id, account.org_id, tokens, metadata=metadata
        )
        return StoredCredential(
            org_id=str(updated.org_id),
            provider=self._provider,
            tokens=dict(tokens),
            created_at=updated.created_at,
            updated_at=updated.updated_at,
            metadata=dict(updated.metadata or {}),
        )

    def delete(self, org_id: str, provider: str) -> bool:
        if provider != self._provider:
            return False
        account = self._resolve(org_id)
        if account is None:
            return False
        return self._svc.delete_account(account.id, account.org_id)

    def list_providers(self, org_id: str) -> list[str]:
        accounts = self._svc.list_accounts(_coerce_org(org_id), provider=self._provider)
        return [self._provider] if accounts else []


def build_credential_store(
    admin_client: Any,
    cfg: Any,
    provider: str,
) -> CredentialStore:
    """Build the multi-account credential store for ``provider`` (GENERIC).

    Validates the Fernet key loudly (via ``build_integration_account_service``
    → ``require_fernet``) so a missing ``ENCRYPTION_KEY`` raises
    ``EncryptionNotConfigured`` at the same spot the legacy single-account
    store did — callers' 503-on-config-gap handling is preserved."""
    svc = build_integration_account_service(
        admin_client, encryption_key=cfg.encryption_key
    )
    return MultiAccountCredentialStore(svc, provider)


# ─── Per-provider SERVICE factory registry ─────────────────────────────────
# provider id → callable(admin_client, cfg, store) -> service instance.
# A provider is "wired for a multi-account service" once it appears here.
# Add the next provider's factory below as it graduates — increment THIS map.
def _build_youtube_service(admin_client: Any, cfg: Any, store: CredentialStore):
    # Lazy import keeps account_credentials free of a hard youtube dep at import
    # time (avoids import cycles: youtube routers import this module).
    from app.modules.youtube.services.youtube import YouTubeService

    return YouTubeService(
        client_id=cfg.youtube_client_id,
        client_secret=cfg.youtube_client_secret,
        redirect_uri=cfg.youtube_redirect_uri,
        credential_store=store,
    )


_SERVICE_FACTORIES: dict[str, Callable[[Any, Any, CredentialStore], Any]] = {
    "youtube": _build_youtube_service,
    # "gmail":          _build_gmail_service,        # ← register as wired
    # "google_drive":   _build_drive_service,
    # "meta":           _build_meta_service,
}


def register_service_factory(
    provider: str,
    factory: Callable[[Any, Any, CredentialStore], Any],
) -> None:
    """Register (or override) a provider's multi-account service factory.

    The extension point: when a provider graduates to multi-account, add its
    factory here (or call this at import) instead of touching call-sites."""
    _SERVICE_FACTORIES[provider] = factory


def build_service_for_org(admin_client: Any, cfg: Any, provider: str) -> Any:
    """Build the multi-account-aware service for ``provider``, wired to that
    org's default account. Raises ``ProviderNotWired`` for providers without a
    registered service factory yet (the credential store still builds via
    ``build_credential_store`` — only the service wrapper is pending)."""
    factory = _SERVICE_FACTORIES.get(provider)
    if factory is None:
        raise ProviderNotWired(
            f"provider {provider!r} has no multi-account service factory yet — "
            f"register one in account_credentials._SERVICE_FACTORIES "
            f"(wired: {sorted(_SERVICE_FACTORIES)})"
        )
    store = build_credential_store(admin_client, cfg, provider)
    return factory(admin_client, cfg, store)


def build_youtube_service_for_org(admin_client: Any, cfg: Any):
    """Convenience wrapper — the YouTube call-sites' canonical entrypoint.

    Thin alias for ``build_service_for_org(admin_client, cfg, "youtube")``;
    keeps the YouTube routers readable while the general factory owns the
    construction. Raises ``EncryptionNotConfigured`` / ``YouTubeServiceError``
    exactly as the inlined form did."""
    return build_service_for_org(admin_client, cfg, "youtube")
