"""Shared account-resolution + n8n-client DI seams for the n8n module.

Every n8n route needs the same three things:

1. An org-scoped ``IntegrationAccountService`` (``get_account_service``
   DI seam — mirrors ``integration_accounts_router.get_account_service``;
   NOT formalized into a shared helper because that router file is a
   peer's live zone this slice must not touch — see the returned
   ``scoped-improvement:`` note).
2. The caller's ``integration_accounts`` row resolved with the
   contract's explicit 404-vs-403 split (``resolve_n8n_account``).
3. A properly-typed ``N8nClient`` built from the account's decrypted
   credential WITHOUT silently falling back to ``FakeN8nClient`` when
   the credential is incomplete — ``get_n8n_client()``'s deferred-
   config default (no creds ⇒ Fake) is exactly the "succeeds empty"
   trap ``require_complete_n8n_credential`` exists to prevent. A route
   that skipped this check and called ``get_n8n_client()`` straight
   from a half-filled credential would silently serve the FE
   ``FakeN8nClient``'s seeded demo workflows instead of a loud 424 —
   the exact silent-error shape this house forbids.
"""
from __future__ import annotations

import logging

from typing import Any, Optional
from uuid import UUID

from fastapi import Depends, HTTPException, status
from noctusai_lib.integrations.n8n import (
    N8nClient,
    N8nError,
    N8nNotFoundError,
    N8nWorkflowNotRunnableError,
    get_n8n_client,
)

from app.config import SocialWiringSettings
from app.dependencies import get_admin_client, get_settings
from app.services.credential_vault import CredentialStoreError, EncryptionNotConfigured
from app.services.integration_account_service import (
    IntegrationAccount,
    IntegrationAccountService,
    build_integration_account_service,
)

logger = logging.getLogger(__name__)

_SCHEMA = "social_wiring"
_ACCOUNTS_TABLE = "integration_accounts"
_PROVIDER = "n8n"

__all__ = [
    "get_account_service",
    "get_admin_client_dep",
    "get_n8n_client_factory",
    "resolve_n8n_account",
    "decrypt_or_503",
    "require_complete_n8n_credential",
    "build_n8n_client",
    "translate_n8n_error",
    "client_tag_out",
]


def get_admin_client_dep() -> Any:
    """DI seam wrapping ``app.dependencies.get_admin_client``.

    Every n8n route needs the admin (service-role) client for
    ``resolve_n8n_account``'s 403-vs-404 existence probe (a raw,
    narrow, org-agnostic lookup — see that function's docstring).
    Routing it through ``Depends(...)`` (rather than each router
    calling ``get_admin_client()`` inline) lets tests override it via
    ``app.dependency_overrides`` to point the probe at the SAME
    backing store as their ``get_account_service`` override, instead
    of exercising ``MockSupabaseClient``'s generic chain-stub API for
    one narrow query. Per ``KB § PATTERNS/di-test-seam.md`` (Class-B).
    """
    return get_admin_client()


def get_account_service(
    cfg: SocialWiringSettings = Depends(get_settings),
) -> IntegrationAccountService:
    """DI seam — 503-on-ENCRYPTION_KEY-gap shape, same convention as
    every other credential-touching router in this product. Tests
    override via ``app.dependency_overrides[get_account_service]``.
    Per ``KB § PATTERNS/di-test-seam.md`` (Class-B, service DI).
    """
    try:
        return build_integration_account_service(
            get_admin_client(), encryption_key=cfg.encryption_key
        )
    except EncryptionNotConfigured as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc


def get_n8n_client_factory():
    """DI seam: a ``(base_url, api_key) -> N8nClient`` callable.

    Real default: the seed's ``get_n8n_client`` factory. Tests override
    via ``app.dependency_overrides[get_n8n_client_factory]`` to return a
    closure over a SINGLE persistent ``FakeN8nClient`` instance (so
    state — e.g. a tag just created, a workflow just renamed — survives
    across the several client calls one test makes), rather than
    monkeypatching this module's import of ``get_n8n_client``. Per
    ``KB § PATTERNS/di-test-seam.md`` (Class-B).
    """
    return get_n8n_client


def resolve_n8n_account(
    svc: IntegrationAccountService,
    admin_client: Any,
    account_id: UUID,
    org_id: UUID,
) -> IntegrationAccount:
    """Fetch the n8n account owner-scoped, distinguishing 404 (doesn't
    exist, or isn't an n8n account) from 403 (exists, wrong org) — the
    contract's explicit status-code split.

    ``IntegrationAccountService.get_account`` filters ``org_id`` inline
    and returns ``None`` for BOTH "doesn't exist" and "wrong org" (by
    design — least-privilege, it never leaks a cross-org existence
    signal on its own). Distinguishing the two here needs one extra,
    narrow, ID-only probe via the ADMIN (service-role) client — bypasses
    RLS deliberately, exactly like every other admin-client call in this
    router family, and reveals nothing beyond `(id, org_id, provider)`.

    Every rejection is LOGGED as well as returned. The three branches
    below are indistinguishable from the outside — all the caller sees
    is ``404 n8n account not found`` (deliberately: the response must
    not leak whether an id exists in another org) — so without a log
    line the operator cannot tell "the FE sent a stale id" from "the FE
    sent another provider's id" from "the row was deleted", and those
    have three different fixes. Diagnosing the live 404 on 2026-07-31
    cost a manual DB cross-reference for exactly this reason: the
    account id in the request belonged to ``provider='meta'``, and
    nothing on the server said so. Same lesson as ``translate_n8n_error``
    one layer down — the detail string reaching the browser is not an
    operator-visible diagnosis.

    WARNING, not exception(): these are client errors with a fully
    known cause, not crashes. There is no traceback worth carrying.
    """
    account = svc.get_account(account_id, org_id)
    if account is not None and account.provider == _PROVIDER:
        return account

    resp = (
        admin_client.schema(_SCHEMA)
        .table(_ACCOUNTS_TABLE)
        .select("id,org_id,provider")
        .eq("id", str(account_id))
        .execute()
    )
    rows = resp.data or []
    if not rows:
        logger.warning(
            "n8n account resolve failed: no integration_accounts row with id=%s "
            "(org=%s) — stale or deleted account id from the caller",
            account_id,
            org_id,
        )
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="n8n account not found")
    if str(rows[0].get("org_id")) != str(org_id):
        logger.warning(
            "n8n account resolve rejected: account id=%s belongs to org=%s, "
            "caller org=%s",
            account_id,
            rows[0].get("org_id"),
            org_id,
        )
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="account does not belong to your organization",
        )
    # Belongs to the caller's org but isn't an n8n account (wrong provider).
    logger.warning(
        "n8n account resolve failed: account id=%s (org=%s) is provider=%r, not %r "
        "— the caller sent another provider's account id to an n8n route",
        account_id,
        org_id,
        rows[0].get("provider"),
        _PROVIDER,
    )
    raise HTTPException(status.HTTP_404_NOT_FOUND, detail="n8n account not found")


def decrypt_or_503(
    svc: IntegrationAccountService, account_id: UUID, org_id: UUID
) -> dict:
    """``svc.decrypt_credential`` wrapped with the house 503-on-
    key-mismatch convention (``CredentialStoreError`` — ENCRYPTION_KEY
    rotated/tampered ciphertext — is a server misconfiguration, not an
    incomplete-credential 424)."""
    try:
        return svc.decrypt_credential(account_id, org_id)
    except CredentialStoreError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc


def require_complete_n8n_credential(credential: Optional[dict]) -> tuple[str, str]:
    """Return ``(base_url, api_key)`` or raise 424.

    424 = OUR configuration is incomplete (fix the card) — GUESS: both
    fields are required here even though the GET /settings status-
    derivation rule only gates on ``base_url`` (per the brief). Widening
    to also require ``api_key`` is deliberate: ``get_n8n_client()``
    itself needs BOTH to build a real client, so a base_url-only
    credential would otherwise silently degrade into
    ``FakeN8nClient`` here — the exact trap this function exists to
    close. Flagged loudly in the delivery notes since the FE cannot see
    this widening choice.
    """
    base_url = (credential or {}).get("base_url") or ""
    api_key = (credential or {}).get("api_key") or ""
    if not base_url or not api_key:
        raise HTTPException(
            status.HTTP_424_FAILED_DEPENDENCY,
            detail=(
                "n8n account is not fully configured (missing base_url "
                "or api_key). Complete it via PUT /api/n8n/settings."
            ),
        )
    return base_url, api_key


def build_n8n_client(factory, credential: Optional[dict]) -> tuple[N8nClient, str, str]:
    """``require_complete_n8n_credential`` + the client-factory call in
    one step — the shape every workflow/tag/execution route needs."""
    base_url, api_key = require_complete_n8n_credential(credential)
    return factory(base_url=base_url, api_key=api_key), base_url, api_key


def translate_n8n_error(exc: N8nError) -> HTTPException:
    """Map the seed adapter's error hierarchy onto the contract's
    status codes.

    ``N8nNotFoundError`` → our 404 (the workflow/tag this route
    addresses doesn't exist on n8n's side either — the caller's
    path/body param is stale). Everything else in the hierarchy (auth /
    rate-limit / rejected / unreachable) → 502, per the contract's
    explicit "unreachable/auth-failed upstream" grouping — n8n *has* a
    complete credential to work with here (424 already gated that);
    502 means n8n itself said no. ``N8nWorkflowNotRunnableError`` → 409
    as a safety net (the run route pre-checks ``can_run`` BEFORE
    dispatch so this branch should be unreachable in practice — no
    request is ever sent on a blocked workflow).
    """
    if isinstance(exc, N8nWorkflowNotRunnableError):
        return HTTPException(status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, N8nNotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc))

    # LOG the cause, do not merely return it. The detail string reaches the
    # browser, but nothing reached the server log — so a 502 was diagnosable
    # only by someone holding a session token and reading a response body.
    # Debugging a live upstream failure on 2026-07-31 stalled on exactly that:
    # the access log showed `status_code=502` and no reason anywhere.
    #
    # `exception()` (not `error()`) so the adapter's traceback rides along —
    # "n8n error: " on its own does not distinguish a DNS failure from a 401
    # from a TLS mismatch, and those have different fixes.
    logger.exception("n8n upstream call failed (%s): %s", type(exc).__name__, exc)
    return HTTPException(status.HTTP_502_BAD_GATEWAY, detail=f"n8n error: {exc}")


def client_tag_out(account: IntegrationAccount) -> Optional[dict]:
    """Read the client's configured n8n tag from
    ``channel_info['tag']`` (``{'id': ..., 'name': ...}``) — the field
    PUT /api/n8n/settings owns (the generic
    ``IntegrationAccountService`` has no REST write path for
    ``channel_info``; this module's settings router is the first
    caller of ``update_channel_info`` from behind a REST route).
    ``None`` when no tag has been configured yet.
    """
    info = account.channel_info or {}
    tag = info.get("tag")
    if isinstance(tag, dict) and tag.get("id"):
        return {"id": str(tag["id"]), "name": str(tag.get("name") or "")}
    return None
