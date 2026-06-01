"""Canonical "adopt an existing single-account connection" capability.

This is the REFERENCE path for bringing a pre-existing single-account
``credentials`` row (the seed ``CredentialStore`` shape: one row per
(org, provider)) into the multi-account ``integration_accounts`` model as
a first-class account. It is NOT a one-off "backfill" — it is the
generic onboarding step every provider uses to graduate from
single-account to multi-account.

YouTube is **pilot #1**: it is the first provider wired end-to-end
(consumed via ``MultiAccountYouTubeStore``, surfaced as a card, default
swappable). The other single-account providers that today live in the
legacy ``credentials`` table (``google_calendar`` / ``gmail`` / ``meta``)
adopt through this SAME function when they are wired for multi-account —
this module is the canonical reference / seed for that work.

Contract:
  * Explicit, not implicit. Invoked by ``POST /api/integrations/accounts/
    {provider}/adopt-legacy`` (the unified Conexões page triggers it on
    load). NEVER a silent write inside a GET, never a lazy backfill on a
    read/consume path — adoption is a deliberate, observable feature step.
  * Idempotent. If the org already has ≥1 ``integration_accounts`` row for
    the provider, returns its default (no duplicate, no clobber).
  * First account becomes the default — it IS the account the consume
    path resolves until the operator connects + promotes another.

Seed-candidate (memory feedback_seed_shape_vs_primitive_consume): the
multi-account framework + this adoption path are product-local today, but
the shape generalizes across products — a future seed lift would make
``integration_accounts`` + adoption a canonical organ. Tracked as a
follow-up; this module is the reference implementation.
"""
from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from app.services.credential_vault import CredentialStore, build_credential_store
from app.services.integration_account_service import (
    IntegrationAccount,
    IntegrationAccountService,
)

logger = logging.getLogger(__name__)

__all__ = ["adopt_legacy_account", "derive_account_label"]

# Per-provider preference order for deriving a human label from the legacy
# record's metadata. YouTube (pilot) keys off the channel title; the others
# are the canonical keys their adapters persist. Falls back to a generic
# label when none are present. Extend this map as each provider is wired.
_LABEL_METADATA_KEYS: dict[str, tuple[str, ...]] = {
    "youtube": ("channel_title",),
    "google_drive": ("account_email", "email"),
    "gmail": ("account_email", "email"),
    "meta": ("page_name", "account_name", "account_email"),
}


def derive_account_label(provider: str, record: Any) -> str:
    """Best-effort human label for an adopted account from legacy metadata."""
    meta = getattr(record, "metadata", None) or {}
    for key in _LABEL_METADATA_KEYS.get(provider, ()):  # provider-specific first
        val = meta.get(key)
        if val:
            return str(val)
    # Generic, honest fallback — the operator can rename via the UI.
    return f"{provider} (conta existente)"


def adopt_legacy_account(
    admin_client: Any,
    svc: IntegrationAccountService,
    org_id: UUID,
    provider: str,
    cfg: Any,
    *,
    legacy_store: Optional[CredentialStore] = None,
) -> Optional[IntegrationAccount]:
    """Promote a legacy single-account ``credentials`` row for ``(org,
    provider)`` into a first-class ``integration_accounts`` row
    (``is_default=True``).

    Returns the adopted account, the pre-existing default if already
    adopted (idempotent), or ``None`` when there is no legacy connection
    to adopt.

    ``legacy_store`` is a DI seam (KB § PATTERNS/di-test-seam.md): tests
    inject the seed ``FakeCredentialStore``; production builds the real
    ``credentials``-backed store from ``admin_client``.
    """
    existing = svc.list_accounts(org_id, provider=provider)
    if existing:
        return next((a for a in existing if a.is_default), existing[0])

    if legacy_store is None:
        try:
            legacy_store = build_credential_store(
                admin_client, encryption_key=cfg.encryption_key
            )
        except Exception as exc:  # EncryptionNotConfigured et al.
            logger.warning(
                "legacy_adoption: cannot read legacy creds for adoption "
                "(org=%s, provider=%s): %s",
                org_id,
                provider,
                exc,
            )
            return None

    record = legacy_store.get(str(org_id), provider)
    if record is None:
        return None

    label = derive_account_label(provider, record)
    metadata = {
        k: v for k, v in (record.metadata or {}).items() if v is not None
    }
    try:
        account = svc.create_account(
            org_id=org_id,
            provider=provider,
            account_label=label,
            credential_dict=record.tokens,
            metadata=metadata,
            is_default=True,
        )
        logger.info(
            "legacy_adoption: adopted legacy %s connection into "
            "integration_accounts for org=%s (account=%s, label=%r)",
            provider,
            org_id,
            account.id,
            label,
        )
        return account
    except Exception as exc:  # unique-violation race / concurrent adoption
        logger.warning(
            "legacy_adoption: adopt insert failed for org=%s provider=%s "
            "(%s) — re-reading in case of a concurrent adoption",
            org_id,
            provider,
            exc,
        )
        again = svc.list_accounts(org_id, provider=provider)
        if again:
            return next((a for a in again if a.is_default), again[0])
        return None
