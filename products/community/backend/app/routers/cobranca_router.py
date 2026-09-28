"""Cobrança router — projects/ninho-vazio/CONTRACT.md §Billing — slice BE-B.

* `GET  /api/cobranca/configuracoes`   — staff (admin + moderador).
* `PUT  /api/cobranca/configuracoes`   — admin.
* `POST /api/cobranca/executar-rotina` — admin; runs the billing sweep now.

Every route runs on the caller's own client (RLS: `eh_equipe()`), never
the service role — an admin endpoint does not bypass RLS. The scheduled
run (`app/scheduler.py`) is the only service-role caller of the sweep.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from app.dependencies import (
    coerce_org_uuid,
    get_community_role,
    get_current_user_org,
    get_user_client,
    require_admin,
)
from app.schemas.cobranca import ConfiguracoesCobranca, ExecutarRotinaResponse
from app.services.cobranca_service import CobrancaService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/cobranca", tags=["cobranca"])


@router.get("/configuracoes", response_model=ConfiguracoesCobranca)
async def obter_configuracoes(
    auth: tuple = Depends(get_current_user_org),
) -> ConfiguracoesCobranca:
    _user, token, raw_org = auth
    service = CobrancaService(get_user_client(token), org_id=coerce_org_uuid(raw_org))
    return ConfiguracoesCobranca(**service.obter_configuracoes())


@router.put("/configuracoes", response_model=ConfiguracoesCobranca)
async def salvar_configuracoes(
    payload: ConfiguracoesCobranca,
    auth: tuple = Depends(get_current_user_org),
) -> ConfiguracoesCobranca:
    user, token, raw_org = auth
    require_admin(get_community_role(user), action="alterar as configurações de cobrança")
    service = CobrancaService(get_user_client(token), org_id=coerce_org_uuid(raw_org))
    saved = service.salvar_configuracoes(
        dias_carencia=payload.dias_carencia, automacoes_ativas=payload.automacoes_ativas,
    )
    return ConfiguracoesCobranca(**saved)


@router.post("/executar-rotina", response_model=ExecutarRotinaResponse)
async def executar_rotina(
    auth: tuple = Depends(get_current_user_org),
) -> ExecutarRotinaResponse:
    user, token, raw_org = auth
    require_admin(get_community_role(user), action="executar a rotina de cobrança")
    service = CobrancaService(get_user_client(token), org_id=coerce_org_uuid(raw_org))
    relatorios = await service.executar_rotina()
    return ExecutarRotinaResponse(relatorios=[r.como_dict() for r in relatorios])
