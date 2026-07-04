"""Shared Meta-router helpers — extracted from ``meta_router`` so
``meta_insights_router`` (Instagram insights, W-ig-insights) can reuse the
exact same adapter-construction + org-resolution + adapter-label logic
without duplicating it (DRY — the N=2 recurrence rule).

Nothing here is product-specific business logic: it's the credential
store / org-id / adapter-label seam every Meta-consuming router needs.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status

from app.config import settings
from app.dependencies import get_admin_client
from app.services.credential_vault import CredentialStore, EncryptionNotConfigured, build_credential_store
from app.services.meta import FakeMetaAdapter, MetaOAuthAdapter

__all__ = ["build_store", "resolve_org_id", "adapter_label"]


def build_store() -> CredentialStore:
    try:
        return build_credential_store(get_admin_client())
    except EncryptionNotConfigured as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


def resolve_org_id(raw: str | None) -> UUID:
    """Mirror calendar_router's resolution: query string overrides
    fall back to the local-dev org id while the Meta surface runs
    without auth in front of it."""
    if raw:
        try:
            return UUID(raw)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="invalid org_id",
            ) from exc
    return UUID(settings.local_dev_org_id)


def adapter_label(adapter) -> str:
    if isinstance(adapter, MetaOAuthAdapter):
        return "oauth"
    if isinstance(adapter, FakeMetaAdapter):
        return "fake"
    return type(adapter).__name__
