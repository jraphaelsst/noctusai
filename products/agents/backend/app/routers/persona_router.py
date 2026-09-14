"""``/api/agents/julia/persona`` — read + edit the active persona version
(contract §E.2, ``projects/julia-agents-academia-CONTRACT.md``).

``PUT`` is admin-only (persona writes gate on ``ADMIN_ROLES``); ``GET`` is
any org member. ``PersonaStore.create_version`` raises ``ValueError`` for a
``model``/``effort`` outside its CHECK-constraint allowlist — mapped to 422
here (contract: "422 if ``model`` is outside the allowlist").
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import (
    get_agent_store_dep,
    get_persona_store_dep,
    require_admin,
    require_member,
)
from app.schemas.agents import PersonaOut, PersonaUpdateRequest
from app.stores.errors import NotFound
from app.stores.personas import PersonaInput
from noctusai_lib.api.auth.session import AuthContext

router = APIRouter(prefix="/api/agents/julia/persona", tags=["persona"])


def _persona_out(record) -> PersonaOut:
    return PersonaOut(
        versao=record.versao,
        nome=record.nome,
        papel=record.papel,
        tom=record.tom,
        system_prompt_append=record.system_prompt_append,
        model=record.model,
        effort=record.effort,
        idioma=record.idioma,
        org_display_name=record.org_display_name,
        project_display_name=record.project_display_name,
        ativa=record.ativa,
        created_by=record.created_by,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@router.get("", response_model=PersonaOut)
async def get_persona(
    ctx: AuthContext = Depends(require_member),
    agent_store=Depends(get_agent_store_dep),
    persona_store=Depends(get_persona_store_dep),
) -> PersonaOut:
    agent_store.ensure_default_agents(ctx.org_id)
    agent = agent_store.get_by_key(ctx.org_id, "julia")
    try:
        record = persona_store.get_active(ctx.org_id, agent.id)
    except NotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"detail": "Nenhuma persona ativa configurada.", "code": "not_found"},
        ) from exc
    return _persona_out(record)


@router.put("", response_model=PersonaOut)
async def update_persona(
    payload: PersonaUpdateRequest,
    ctx: AuthContext = Depends(require_admin),
    agent_store=Depends(get_agent_store_dep),
    persona_store=Depends(get_persona_store_dep),
) -> PersonaOut:
    agent_store.ensure_default_agents(ctx.org_id)
    agent = agent_store.get_by_key(ctx.org_id, "julia")

    data = PersonaInput(
        nome=payload.nome,
        papel=payload.papel,
        model=payload.model,
        effort=payload.effort,
        tom=payload.tom,
        system_prompt_append=payload.system_prompt_append,
        idioma=payload.idioma,
        org_display_name=payload.org_display_name,
        project_display_name=payload.project_display_name,
    )
    try:
        record = persona_store.create_version(ctx.org_id, agent.id, data, created_by=ctx.user_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"detail": str(exc), "code": "invalid_field"},
        ) from exc
    return _persona_out(record)


__all__ = ["router"]
