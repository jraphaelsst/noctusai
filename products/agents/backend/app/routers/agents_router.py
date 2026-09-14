"""``/api/agents`` — list + toggle (contract §E.2,
``projects/julia-agents-academia-CONTRACT.md``).

Every route is user-only. Toggling ``julia`` flips the local
``agents.agents.ativo`` column. Toggling ``one-chat`` calls the
social-wiring E.6 bridge instead — its ``ativo``/``estado_externo`` are
whatever social-wiring returns, never a locally-stored truth (the row's
``ativo`` column stays a placeholder for that agent; see
``app/clients/social_wiring.py``'s module docstring and this slice's
delivery note for the interpretation call).
"""
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.clients.social_wiring import SocialWiringUnreachable
from app.dependencies import get_agent_store_dep, get_social_wiring_client_dep, require_admin, require_member
from app.schemas.agents import AgentListOut, AgentOut, AgentToggleRequest, EstadoExternoOut
from app.stores.errors import NotFound
from noctusai_lib.api.auth.session import AuthContext

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agents", tags=["agents"])


def _agent_out(
    record, *, estado_externo: EstadoExternoOut | None = None, aviso: str | None = None,
    ativo_override: bool | None = None,
) -> AgentOut:
    return AgentOut(
        key=record.key,
        nome=record.nome,
        runtime=record.runtime,
        owner_product=record.owner_product,
        ativo=record.ativo if ativo_override is None else ativo_override,
        estado_externo=estado_externo,
        aviso=aviso,
    )


async def _one_chat_state(record, client) -> tuple[EstadoExternoOut | None, str | None]:
    connection_id = (record.external_ref or {}).get("connection_id") if record.external_ref else None
    if not connection_id:
        return None, "One Chat ainda não configurado (nenhuma conexão vinculada)."
    try:
        state = await client.get_one_chat_state(UUID(str(connection_id)))
    except SocialWiringUnreachable:
        logger.warning("agents.one_chat.bridge_unreachable connection_id=%s", connection_id)
        return None, "Não foi possível consultar o social-wiring."
    return EstadoExternoOut(auto_reply_enabled=bool(state.get("auto_reply_enabled"))), None


@router.get("", response_model=AgentListOut)
async def list_agents(
    ctx: AuthContext = Depends(require_member),
    store=Depends(get_agent_store_dep),
    social_wiring_client=Depends(get_social_wiring_client_dep),
) -> AgentListOut:
    store.ensure_default_agents(ctx.org_id)
    records = store.list(ctx.org_id)

    items: list[AgentOut] = []
    for record in records:
        if record.key == "one-chat":
            estado_externo, aviso = await _one_chat_state(record, social_wiring_client)
            items.append(_agent_out(record, estado_externo=estado_externo, aviso=aviso))
        else:
            items.append(_agent_out(record))
    return AgentListOut(items=items, total=len(items))


@router.post("/{key}/toggle", response_model=AgentOut)
async def toggle_agent(
    key: str,
    payload: AgentToggleRequest,
    ctx: AuthContext = Depends(require_admin),
    store=Depends(get_agent_store_dep),
    social_wiring_client=Depends(get_social_wiring_client_dep),
) -> AgentOut:
    store.ensure_default_agents(ctx.org_id)
    try:
        record = store.get_by_key(ctx.org_id, key)
    except NotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"detail": "Agente não encontrado.", "code": "not_found"},
        ) from exc

    if key == "one-chat":
        # Contract §E.2: "one-chat: calls E.6, and the response reflects
        # social-wiring's returned state." The local `agents.ativo` column
        # is NEVER written for this key — one-chat's on/off truth lives
        # entirely in social-wiring's `auto_reply_enabled`; this response's
        # `ativo` mirrors THAT value (see `ativo_override` below), not a
        # local write. Tech-lead-accepted interpretation, 2026-09-14.
        connection_id = (record.external_ref or {}).get("connection_id") if record.external_ref else None
        if not connection_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "detail": "One Chat ainda não configurado (nenhuma conexão vinculada).",
                    "code": "not_configured",
                },
            )
        try:
            result = await social_wiring_client.set_one_chat_auto_reply(
                UUID(str(connection_id)), payload.ativo
            )
        except SocialWiringUnreachable as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={"detail": "Falha ao comunicar com o social-wiring.", "code": "upstream_failed"},
            ) from exc
        auto_reply_enabled = bool(result.get("auto_reply_enabled"))
        return _agent_out(
            record,
            estado_externo=EstadoExternoOut(auto_reply_enabled=auto_reply_enabled),
            ativo_override=auto_reply_enabled,
        )

    record = store.set_active(ctx.org_id, key, payload.ativo)
    return _agent_out(record)


__all__ = ["router"]
