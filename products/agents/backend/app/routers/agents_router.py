"""``/api/agents`` — list + toggle (contract §E.2,
``projects/julia-agents-academia-CONTRACT.md``).

Every route is user-only. A toggle flips the local ``agents.agents.ativo``
column. (The "One Chat" operator bot and its social-wiring bridge were
retired 2026-11: Julia is the WhatsApp line.)
"""
from __future__ import annotations
import anyio

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import (
    get_agent_store_dep,
    require_member,
    require_platform_content_admin,
)
from app.schemas.agents import AgentListOut, AgentOut, AgentToggleRequest
from app.stores.errors import NotFound
from noctusai_lib.api.auth.session import AuthContext

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agents", tags=["agents"])


def _agent_out(record) -> AgentOut:
    return AgentOut(
        key=record.key,
        nome=record.nome,
        runtime=record.runtime,
        owner_product=record.owner_product,
        ativo=record.ativo,
    )


@router.get("", response_model=AgentListOut)
async def list_agents(
    ctx: AuthContext = Depends(require_member),
    store=Depends(get_agent_store_dep),
) -> AgentListOut:
    records = store.list(ctx.org_id)

    items = [_agent_out(record) for record in records]
    return AgentListOut(items=items, total=len(items))


@router.post("/{key}/toggle", response_model=AgentOut, include_in_schema=False)
async def toggle_agent(
    key: str,
    payload: AgentToggleRequest,
    ctx: AuthContext = Depends(require_platform_content_admin),
    store=Depends(get_agent_store_dep),
) -> AgentOut:
    try:
        record = (await anyio.to_thread.run_sync(lambda: store.get_by_key(ctx.org_id, key)))
    except NotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"detail": "Agente não encontrado.", "code": "not_found"},
        ) from exc

    # NOC-REMEDIATE[agents-toggle-bridge-generalize]: this toggle only flips the local `agents.ativo`. The One Chat ->
    # social-wiring bridge it used to special-case is retired (Julia is the WhatsApp line). Phase 2 of the per-app
    # WhatsApp switch: let `external_ref={product, connection_id}` call THAT product's seed route
    # `PUT /api/whatsapp/connections/{id}/enabled` (seed `create_whatsapp_connections_router`, already shipped), so
    # the "Agentes" toggle IS the app's on/off button for every app (nosnolimiar first) — 2026-10-26
    record = (await anyio.to_thread.run_sync(lambda: store.set_active(ctx.org_id, key, payload.ativo)))
    return _agent_out(record)


__all__ = ["router"]
