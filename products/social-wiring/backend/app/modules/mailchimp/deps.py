"""DI seams for the Mailchimp module.

Three seams (tests override all three via ``app.dependency_overrides``):

  ``get_mailchimp_store``
      Returns a wired :class:`MailchimpConnectionStore`; raises 503 when
      ENCRYPTION_KEY is unset/invalid (same fail-loud pattern as WhatsApp).

  ``get_mailchimp_client_factory``
      Returns the seed ``get_mailchimp_client`` factory callable. LAZY IMPORT:
      noctusai_lib.integrations.mailchimp is built concurrently in slice A;
      importing at module level would fail in the current tree. Import happens
      inside the function body so the seam is safe until slice A lands.

      Tests override this seam to inject ``ContractFakeMailchimpClient``
      producers without any import of the seed adapter.

  ``require_mailchimp_client``
      Composes the above two: fetches the connection record (decrypt=True) and
      builds a live client. Raises 503 ``mailchimp_not_configured`` when no
      connection row exists or when ``audience_id`` is unset (for routes that
      need a default audience).

Per ``KB § PATTERNS/backend/di-test-seam.md`` (Class-B).
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional, Tuple
from uuid import UUID

from fastapi import Depends, HTTPException, status

from app.dependencies import coerce_org_uuid, get_admin_client, get_current_user_org, get_settings
from app.modules.mailchimp.store import (
    MailchimpConnectionRecord,
    MailchimpConnectionStore,
    build_mailchimp_connection_store,
)
from app.services.credential_vault import EncryptionNotConfigured
from noctusai_lib.primitives.exceptions import AppException

logger = logging.getLogger(__name__)

_NOT_CONFIGURED = AppException(
    code="mailchimp_not_configured",
    message="Mailchimp is not configured for this org.",
    status_code=503,
)


# ── DI seam: store ────────────────────────────────────────────────────────────

def get_mailchimp_store(
    cfg=Depends(get_settings),
) -> MailchimpConnectionStore:
    """Return a wired store; 503 when ENCRYPTION_KEY is unset/invalid.

    Tests override via ``app.dependency_overrides[get_mailchimp_store]``
    with a SQLite-backed store (no singleton mutation, no self-monkeypatch).
    Per ``KB § PATTERNS/backend/di-test-seam.md`` (Class-B)."""
    try:
        return build_mailchimp_connection_store(
            get_admin_client(), encryption_key=cfg.encryption_key
        )
    except EncryptionNotConfigured as exc:
        raise AppException(
            code="mailchimp_not_configured",
            message=str(exc),
            status_code=503,
        ) from exc


# ── DI seam: client factory ──────────────────────────────────────────────────

def get_mailchimp_client_factory() -> Callable:
    """Return the seed ``get_mailchimp_client`` factory.

    LAZY IMPORT: noctusai_lib.integrations.mailchimp is built concurrently
    (slice A); the import is deferred inside this function body so tests that
    override this seam never trigger the import path. Once slice A lands, the
    import resolves normally.

    Tests override via ``app.dependency_overrides[get_mailchimp_client_factory]``
    to inject a ``ContractFakeMailchimpClient`` producer.
    Per ``KB § PATTERNS/backend/di-test-seam.md`` (Class-B).
    """
    from noctusai_lib.integrations.mailchimp import get_mailchimp_client  # noqa: PLC0415

    return get_mailchimp_client


# ── Composed seam: require a live client + record ────────────────────────────

async def require_mailchimp_client(
    auth: tuple = Depends(get_current_user_org),
    store: MailchimpConnectionStore = Depends(get_mailchimp_store),
    factory: Callable = Depends(get_mailchimp_client_factory),
    require_audience: bool = True,
) -> Tuple[Any, MailchimpConnectionRecord]:
    """Resolve (client, record) or raise 503 mailchimp_not_configured.

    Used by all routes that need a live Mailchimp client (contacts, segments,
    templates, campaigns). The ``require_audience`` flag can be set False for
    ``GET /audiences`` which doesn't need a default audience yet.
    """
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)

    record = store.get_connection(org_id, decrypt=True)
    if record is None:
        raise _NOT_CONFIGURED
    if require_audience and not record.audience_id:
        raise AppException(
            code="mailchimp_not_configured",
            message="No default audience selected. Configure one via PUT /connection.",
            status_code=503,
        )

    client = factory(api_key=record.api_key, server_prefix=record.server_prefix)
    return client, record


def make_require_mailchimp_client(*, require_audience: bool = True):
    """Factory for ``require_mailchimp_client`` with different ``require_audience``.

    FastAPI Depends() doesn't accept keyword args, so we wrap the composed
    dep into a closure for callers that need ``require_audience=False``
    (e.g. ``GET /audiences``).
    """
    async def _dep(
        auth: tuple = Depends(get_current_user_org),
        store: MailchimpConnectionStore = Depends(get_mailchimp_store),
        factory: Callable = Depends(get_mailchimp_client_factory),
    ) -> Tuple[Any, MailchimpConnectionRecord]:
        _user, _token, raw_org = auth
        org_id = coerce_org_uuid(raw_org)

        record = store.get_connection(org_id, decrypt=True)
        if record is None:
            raise _NOT_CONFIGURED
        if require_audience and not record.audience_id:
            raise AppException(
                code="mailchimp_not_configured",
                message="No default audience selected.",
                status_code=503,
            )
        client = factory(api_key=record.api_key, server_prefix=record.server_prefix)
        return client, record

    return _dep
