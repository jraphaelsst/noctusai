"""Julia > Conhecimento editor (Lais study S8, owner decision 2026-11-17): the three knowledge specs in agents, edited from SW.

  GET /api/julia/conhecimento-editor   org admin  -> {data: {itens[{chave, rotulo, valor, declarada, updated_*, sugestao}], max_chars}}
  PUT /api/julia/conhecimento-editor   ORG ADMIN (owner 2026-11-18)  {valores: {conhecimento_venda|conhecimento_locacao|conhecimento_politicas: texto}}

Access tier `org` (router guard `get_current_user_org`). The business knowledge is org-owned data (owner 2026-11-18): the org's
own admin writes it (a non-admin is 403 before any call to agents); the legacy `PUT /api/julia/conhecimento/{secao}` stays
NoctusAI-only. The key allow-list is enforced here (a body can never reach another spec) and agents validates the type/size again. See
`julia_conhecimento_specs_service` for the keys, the legacy-form suggestion and the event.
"""
# No `from __future__ import annotations`: FastAPI body/param models are resolved from the signature.
import logging
from typing import Any

from fastapi import Depends, Request
from noctusai_lib.api import StrictHttpModel
from noctusai_lib.api.access_tiers import make_router
from noctusai_lib.api.auth._blocking import run_blocking
from noctusai_lib.api.auth.session import require_org_admin_for
from noctusai_lib.primitives.exceptions import AppException

from app.clients.agents import AgentsClientError
from app.dependencies import coerce_org_uuid, get_core_client, get_current_user_org, get_scoped_admin_client
from app.routers.julia_especificacoes_router import _agents, _ator, _traduzir
from app.routers.whatsapp_connections_router import get_agents_client_factory
from app.services import julia_conhecimento_specs_service as svc
from app.services.julia_agente_service import DEFAULT_AGENT_KEY

logger = logging.getLogger(__name__)

router = make_router(
    tier="org", guard=get_current_user_org, prefix="/api/julia/conhecimento-editor", tags=["julia-conhecimento-editor"],
)

_O_QUE = "O conhecimento da Julia"


class ConhecimentoIn(StrictHttpModel):
    valores: dict[str, str]


def get_conhecimento_editor_client() -> Any:
    """DI seam: the schema-scoped service-role client (the legacy sections + the events); tests override."""
    return get_scoped_admin_client("social_wiring")


@router.get("")
async def ler(
    request: Request = None,
    auth: tuple = Depends(get_current_user_org),
    client_factory=Depends(get_agents_client_factory),
    db: Any = Depends(get_conhecimento_editor_client),
) -> dict[str, Any]:
    await run_blocking(require_org_admin_for, get_core_client(), auth, request, _O_QUE)
    org_id = coerce_org_uuid(auth[2])
    agents = await run_blocking(_agents, client_factory, org_id)
    try:
        resposta = await agents.especificacoes(DEFAULT_AGENT_KEY)
    except AgentsClientError as exc:
        raise _traduzir(exc) from exc
    sug = await run_blocking(svc.sugestao, db, org_id)
    return {"data": svc.montar(resposta.corpo.get("valores") or [], resposta.corpo.get("declaradas") or [], sug)}


@router.put("")
async def salvar(
    corpo: ConhecimentoIn,
    request: Request = None,
    auth: tuple = Depends(get_current_user_org),
    client_factory=Depends(get_agents_client_factory),
    db: Any = Depends(get_conhecimento_editor_client),
) -> dict[str, Any]:
    core = get_core_client()
    await run_blocking(require_org_admin_for, core, auth, request, _O_QUE)
    org_id = coerce_org_uuid(auth[2])
    valores = svc.validar(corpo.valores)
    agents = await run_blocking(_agents, client_factory, org_id)
    ator = await run_blocking(_ator, auth, core)
    try:
        resposta = await agents.salvar_especificacoes(DEFAULT_AGENT_KEY, valores, ator)
    except AgentsClientError as exc:
        raise _traduzir(exc) from exc
    if resposta.status != 200:
        raise AppException(
            str(resposta.corpo.get("code") or "conhecimento_recusado"),
            str(resposta.corpo.get("detail") or "A Julia recusou o texto."), status_code=422,
        )
    await run_blocking(svc.registrar_evento, db, org_id, ator["user_id"], valores)
    sug = await run_blocking(svc.sugestao, db, org_id)
    return {"data": svc.montar(resposta.corpo.get("valores") or [], resposta.corpo.get("declaradas") or [], sug)}
