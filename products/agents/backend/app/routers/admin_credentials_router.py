"""``/api/admin/credentials`` — the platform-admin "Credenciais e integrações"
page (contract §B.0 / §D / §E.5 notes, 2026-09-16).

Every route: ``require_platform_admin`` (401 without a credential, 403 for
anyone who is not ``noctus_users.role == 'admin'``, product tokens
included). No response carries a secret — see ``app/schemas/admin.py``.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.credentials.registry import SOCIAL_WIRING_API_TOKEN
from app.credentials.service import CredentialError, CredentialService, CredentialStatus
from app.dependencies import (
    get_agent_store_dep,
    get_credential_service_dep,
    require_platform_admin,
)
from app.schemas.admin import (
    CredentialListOut,
    CredentialOut,
    CredentialValueIn,
    ProbeOut,
    RenewOut,
)
from app.stores.errors import NotFound
from noctusai_lib.api.auth.session import AuthContext

router = APIRouter(prefix="/api/admin/credentials", tags=["admin-credentials"])


def _out(status: CredentialStatus) -> CredentialOut:
    data = asdict(status)
    data["scopes"] = list(status.scopes)
    data["warnings"] = list(status.warnings)
    data["ring"] = [asdict(k) for k in status.ring]
    return CredentialOut(**data)


def _http(exc: CredentialError) -> HTTPException:
    return HTTPException(status_code=exc.http_status, detail={"detail": exc.detail, "code": exc.code})


def _one_chat_connection(agent_store, org_id: UUID, name: str) -> UUID | None:
    """The social-wiring probe targets the org's configured One Chat
    connection when there is one (otherwise the nil UUID — see prober)."""
    if name != SOCIAL_WIRING_API_TOKEN.name:
        return None
    try:
        agent_store.ensure_default_agents(org_id)
        ref = agent_store.get_by_key(org_id, "one-chat").external_ref or {}
    except NotFound:
        return None
    raw = ref.get("connection_id")
    try:
        return UUID(str(raw)) if raw else None
    except ValueError:
        return None


@router.get("", response_model=CredentialListOut)
async def list_credentials(
    ctx: AuthContext = Depends(require_platform_admin),
    service: CredentialService = Depends(get_credential_service_dep),
) -> CredentialListOut:
    items = [_out(s) for s in service.list_status()]
    return CredentialListOut(
        items=items,
        total=len(items),
        alerts=sum(1 for i in items if i.severity != "info"),
    )


@router.put("/{name}", response_model=CredentialOut)
async def set_credential(
    name: str,
    payload: CredentialValueIn,
    ctx: AuthContext = Depends(require_platform_admin),
    service: CredentialService = Depends(get_credential_service_dep),
) -> CredentialOut:
    """Write-only set/replace (Anthropic key, a pasted ``pk_`` token, or
    ``JULIA_AGENT_ID``). The value is never returned."""
    try:
        return _out(service.set_value(name, payload.value))
    except CredentialError as exc:
        raise _http(exc) from exc


@router.post("/{name}/import-env", response_model=CredentialOut)
async def import_credential_from_env(
    name: str,
    ctx: AuthContext = Depends(require_platform_admin),
    service: CredentialService = Depends(get_credential_service_dep),
) -> CredentialOut:
    """Operator migration step: copy the container's env value into the
    encrypted store, server-side (the value never reaches the browser)."""
    try:
        return _out(service.import_env(name))
    except CredentialError as exc:
        raise _http(exc) from exc


@router.post("/{name}/health", response_model=ProbeOut)
async def check_credential(
    name: str,
    ctx: AuthContext = Depends(require_platform_admin),
    service: CredentialService = Depends(get_credential_service_dep),
    agent_store=Depends(get_agent_store_dep),
) -> ProbeOut:
    try:
        result = await service.probe(
            name, connection_id=_one_chat_connection(agent_store, ctx.org_id, name)
        )
    except CredentialError as exc:
        raise _http(exc) from exc
    return ProbeOut(
        name=name,
        status=result.status,
        ok=result.ok,
        http_status=result.http_status,
        detail=result.detail,
        checked_at=datetime.now(timezone.utc),
    )


@router.post("/{name}/renew", response_model=RenewOut)
async def renew_credential(
    name: str,
    ctx: AuthContext = Depends(require_platform_admin),
    service: CredentialService = Depends(get_credential_service_dep),
    agent_store=Depends(get_agent_store_dep),
) -> RenewOut:
    """Mint → verify → store → revoke old (see ``app/credentials/service.py``)."""
    try:
        outcome = await service.renew(
            name,
            actor_user_id=ctx.user_id,
            fallback_org_id=ctx.org_id,
            connection_id=_one_chat_connection(agent_store, ctx.org_id, name),
        )
    except CredentialError as exc:
        raise _http(exc) from exc
    return RenewOut(credential=_out(outcome.status), warnings=list(outcome.warnings))


@router.post("/approval_assertion_secrets/rotate", response_model=CredentialOut)
async def rotate_approval_keys(
    ctx: AuthContext = Depends(require_platform_admin),
    service: CredentialService = Depends(get_credential_service_dep),
) -> CredentialOut:
    """Stage a new §D key: accepted by academia at once, signed with after
    the activation delay; current keys retire after the window."""
    try:
        return _out(service.rotate_ring())
    except CredentialError as exc:
        raise _http(exc) from exc


@router.post("/approval_assertion_secrets/prune", response_model=CredentialOut)
async def prune_approval_keys(
    ctx: AuthContext = Depends(require_platform_admin),
    service: CredentialService = Depends(get_credential_service_dep),
) -> CredentialOut:
    try:
        return _out(service.prune_ring())
    except CredentialError as exc:
        raise _http(exc) from exc


__all__ = ["router"]
