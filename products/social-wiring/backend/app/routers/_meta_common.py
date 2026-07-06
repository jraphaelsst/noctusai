"""Shared Meta-router helpers — extracted from ``meta_router`` so
``meta_insights_router`` (Instagram insights, W-ig-insights) can reuse the
exact same adapter-construction + org-resolution + adapter-label logic
without duplicating it (DRY — the N=2 recurrence rule).

Nothing here is product-specific business logic: it's the credential
store / org-id / adapter-label seam every Meta-consuming router needs.

Wave 3 (account-scoped Meta surface) adds a second seam alongside the
org-level one above: :func:`get_account_adapter` — the FastAPI DI
dependency every account-scoped ``/api/meta/*`` router (context /
insights / content / comments / DMs) resolves its adapter through, built
over :func:`app.services.meta.get_meta_adapter_for_account` (the Wave 2
per-client ``integration_accounts`` seam, distinct from the org-level
Store-A adapter above). Tests override this ONE dependency with a
pre-seeded ``FakeMetaAdapter`` instead of standing up a real credential
row (``KB § PATTERNS/backend/di-test-seam.md``, Class-B).

:func:`resolve_primary_ig_user_id` and :func:`handle_meta_graph_error`
are the other two cross-router seams every new Wave 3 router shares:
resolving "the" Instagram Business/Creator account this connection sees
(there is exactly one per per-client Meta connection in practice — the
``context`` endpoint surfaces it as ``instagram: IGAccount|null``), and
mapping a caught ``MetaGraphError`` onto the uniform contract every
Wave 3 endpoint honors: ``requires_app_review`` → 200 structured (never
500 — the UI renders a "needs App Review" state), any other
``MetaGraphError`` → 502 structured (never an unhandled 500 leaking
Graph's raw error envelope).
"""
from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, Query, status
from fastapi.responses import JSONResponse

from app.config import settings
from app.dependencies import get_admin_client
from app.services.credential_vault import CredentialStore, EncryptionNotConfigured, build_credential_store
from app.services.integration_account_service import IntegrationAccountNotFound
from app.services.meta import (
    FakeMetaAdapter,
    MetaAdapter,
    MetaGraphError,
    MetaOAuthAdapter,
    get_meta_adapter_for_account,
)

__all__ = [
    "build_store",
    "resolve_org_id",
    "adapter_label",
    "get_account_adapter",
    "resolve_primary_ig_user_id",
    "handle_meta_graph_error",
]


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


# ─── Wave 3 — account-scoped seam ───────────────────────────────────────
def get_account_adapter(
    account_id: str = Query(..., description="integration_accounts row id (Meta)"),
    org_id: str | None = Query(default=None),
) -> MetaAdapter:
    """FastAPI dependency: resolve the Meta adapter bound to ONE per-client
    ``integration_accounts`` row (Wave 2's ``get_meta_adapter_for_account``
    seam) for every account-scoped ``/api/meta/*`` router.

    ``org_id`` follows the same fallback-to-local-dev-org convention as
    :func:`resolve_org_id` (the Meta surface still runs without auth in
    front of it). Maps the service-layer failure signals onto HTTP:
    malformed ``account_id`` → 400; account absent for this org, or
    present but not a ``provider="meta"`` row → 404 (never a silent
    Fake — a Wave 3 caller already knows it's asking for a specific,
    previously-connected Meta account).

    Overridden in tests via ``app.dependency_overrides[get_account_adapter]``
    with a pre-seeded ``FakeMetaAdapter`` (DI seam, Class-B —
    ``KB § PATTERNS/backend/di-test-seam.md``).
    """
    resolved_org = resolve_org_id(org_id)
    try:
        account_uuid = UUID(account_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="invalid account_id",
        ) from exc

    try:
        return get_meta_adapter_for_account(account_uuid, resolved_org)
    except IntegrationAccountNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


def resolve_primary_ig_user_id(adapter: MetaAdapter) -> str:
    """The Instagram Business/Creator account id this Meta connection
    sees — every account-scoped IG endpoint resolves ``ig_user_id`` this
    way instead of taking it as a path param (the Wave 3 refactor: "the
    IG user resolved from the account", not from the caller).

    A per-client Meta connection is expected to see exactly one linked
    IG account in practice (mirrors ``integration_accounts_router``'s
    OAuth-callback probe, which also takes ``ig_accounts[0]``); the
    first result is used deterministically. Raises 404 (structured, not
    a silent empty-data response) when the connection has no linked IG
    account at all — the caller should have checked ``GET
    /api/meta/context`` first, where ``instagram`` would already read
    ``null``.
    """
    accounts = adapter.list_instagram_accounts()
    if not accounts:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="no instagram account linked to this Meta connection",
        )
    return accounts[0].id


def handle_meta_graph_error(exc: MetaGraphError) -> JSONResponse:
    """Uniform Wave 3 ``MetaGraphError`` → HTTP mapping, shared by every
    account-scoped Meta router (context / insights / content / comments
    / DMs).

    ``requires_app_review`` → 200 with ``{requires_app_review: true,
    error}`` (NOT 500 — a write/read scope pending Meta App Review is an
    expected, actionable state; the FE renders a "requer Revisão do app
    Meta" prompt from this shape). Any other ``MetaGraphError`` → 502
    with a structured body (never an unhandled 500 leaking Graph's raw
    error envelope).

    Returns a ``JSONResponse`` directly for BOTH branches — never
    ``HTTPException(detail={...})``: the seed's global
    ``http_exception_handler`` ``str()``s a non-string ``detail`` into
    a flat message (``format_error_response``), which would silently
    collapse the structured ``code``/``fbtrace_id`` fields back into a
    string (``KB § PATTERNS/backend/backend.md`` — AppException-not-
    HTTPException-dict gotcha). Building the ``JSONResponse`` ourselves
    keeps the body exactly as documented.

    Callers: ``except MetaGraphError as exc: return
    handle_meta_graph_error(exc)``.
    """
    if exc.requires_app_review:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"requires_app_review": True, "error": str(exc)},
        )
    return JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content={
            "error": str(exc),
            "code": exc.code,
            "fbtrace_id": exc.fbtrace_id,
        },
    )
