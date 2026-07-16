"""n8n Settings tab — GET/PUT /api/n8n/settings.

GET DERIVES the incomplete state: if the decrypted credential has no
``base_url``, ``status='error'`` is reported regardless of what the
stored ``status`` column says. Pre-reshape rows say ``'validated'``
and are lying — there is deliberately no backfill script, because
credentials are Fernet BYTEA and invisible to SQL. This derivation
self-heals the moment the operator reconnects via PUT.

Auth pattern: ``Depends(get_current_user_org)`` per
``KB § PATTERNS/backend.md § Auth — canonical pattern``.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from noctusai_lib.integrations.n8n import N8nError

from app.dependencies import coerce_org_uuid, get_current_user_org
from app.modules.n8n.schemas.common import N8nTagOut
from app.modules.n8n.schemas.settings import N8nSettingsOut, N8nSettingsUpdateIn
from app.modules.n8n.services.account_resolver import (
    client_tag_out,
    decrypt_or_503,
    get_account_service,
    get_admin_client_dep,
    get_n8n_client_factory,
    resolve_n8n_account,
)
from app.services.integration_account_service import IntegrationAccountService

router = APIRouter(prefix="/api/n8n", tags=["n8n"])


@router.get("/settings", response_model=N8nSettingsOut)
def get_settings_route(
    account_id: UUID = Query(...),
    auth: tuple = Depends(get_current_user_org),
    svc: IntegrationAccountService = Depends(get_account_service),
    admin=Depends(get_admin_client_dep),
) -> N8nSettingsOut:
    """Never triggers an n8n API call by itself — same "don't spend
    quota / round-trips on a page load" rule
    ``youtube/routers/settings.py``'s ``get_youtube_status`` follows.
    ``reachable`` is always ``None`` here; PUT actively pings."""
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    account = resolve_n8n_account(svc, admin, account_id, org_id)
    credential = decrypt_or_503(svc, account_id, org_id)

    base_url = (credential or {}).get("base_url") or None
    api_key = (credential or {}).get("api_key") or None
    tag = client_tag_out(account)
    derived_status = "error" if not base_url else (account.status or "validated")

    return N8nSettingsOut(
        account_id=account.id,
        base_url=base_url,
        has_api_key=bool(api_key),
        tag=N8nTagOut(**tag) if tag else None,
        status=derived_status,
        reachable=None,
    )


@router.put("/settings", response_model=N8nSettingsOut)
def put_settings_route(
    body: N8nSettingsUpdateIn,
    auth: tuple = Depends(get_current_user_org),
    svc: IntegrationAccountService = Depends(get_account_service),
    admin=Depends(get_admin_client_dep),
    client_factory=Depends(get_n8n_client_factory),
) -> N8nSettingsOut:
    """Partial update: only the supplied fields are written. The
    resulting ``base_url``/``api_key`` pair is used to actively PING
    n8n (unlike GET) so the operator gets immediate feedback on a
    just-entered credential — GUESS: a ping failure does NOT fail the
    request (the credential is still saved; ``reachable=False`` +
    ``status='error'`` report the degraded state instead of a 502).
    The contract doesn't say whether a PUT-time ping failure should
    502 the whole request or just report degraded state; this slice
    chose "always save, report reachability honestly" since blocking
    the save on a transient n8n blip would be a worse UX than the
    save-then-report-broken alternative. Flagged since the FE can't
    see this choice either way.

    ``tag_id`` is resolved to ``{id, name}`` via a live ``list_tags()``
    call — GUESS: the contract only carries ``tag_id`` (no name), and
    both the settings-derivation rule and ``N8nTagOut`` need a name,
    so this slice looks it up rather than persisting a bare id.
    Requires complete credentials (424 if ``tag_id`` is supplied
    without them — nothing to resolve it against); 404 if the id
    doesn't match any tag on the instance.
    """
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    account = resolve_n8n_account(svc, admin, body.account_id, org_id)
    current_credential = decrypt_or_503(svc, body.account_id, org_id)

    merged = dict(current_credential or {})
    if body.base_url is not None:
        merged["base_url"] = body.base_url.strip()
    if body.api_key is not None:
        merged["api_key"] = body.api_key

    base_url = merged.get("base_url") or None
    api_key = merged.get("api_key") or None

    resolved_tag = client_tag_out(account)
    if body.tag_id is not None:
        if not base_url or not api_key:
            raise HTTPException(
                status.HTTP_424_FAILED_DEPENDENCY,
                detail="cannot resolve tag_id without a complete base_url + api_key.",
            )
        client = client_factory(base_url=base_url, api_key=api_key)
        try:
            tags = asyncio.run(client.list_tags())
        except N8nError as exc:
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY, detail=f"n8n error: {exc}"
            ) from exc
        match = next((t for t in tags if t.id == body.tag_id), None)
        if match is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail=f"tag {body.tag_id!r} not found on this n8n instance",
            )
        resolved_tag = {"id": match.id, "name": match.name}

    reachable: bool | None = None
    if base_url and api_key:
        client = client_factory(base_url=base_url, api_key=api_key)
        try:
            reachable = asyncio.run(client.ping())
        except N8nError:
            reachable = False

    if body.base_url is not None or body.api_key is not None:
        svc.update_credential(
            account_id=body.account_id, org_id=org_id, credential_dict=merged
        )

    derived_status = "validated" if (base_url and api_key and reachable) else "error"
    channel_info = dict(account.channel_info or {})
    if resolved_tag is not None:
        channel_info["tag"] = resolved_tag
    updated_account = svc.update_channel_info(
        account_id=body.account_id,
        org_id=org_id,
        channel_info=channel_info,
        status=derived_status,
        last_synced_at=datetime.now(timezone.utc),
    )

    return N8nSettingsOut(
        account_id=updated_account.id,
        base_url=base_url,
        has_api_key=bool(api_key),
        tag=N8nTagOut(**resolved_tag) if resolved_tag else None,
        status="error" if not base_url else derived_status,
        reachable=reachable,
    )


__all__ = ["router"]
