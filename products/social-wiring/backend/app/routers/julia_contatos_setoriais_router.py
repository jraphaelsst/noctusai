"""Julia > Contatos por setor (owner decision 2026-11-17): the org admin manages who Julia redirects a NON-lead to.

  GET /api/julia/contatos-setoriais   org admin -> {data: {dono, contatos[], legado[], setores[], maximo, declarada}}
  PUT /api/julia/contatos-setoriais   org admin  {contatos: [{setor, finalidade, nome, telefone}]} -> the same body

Access tier `org` (router-level guard `get_current_user_org` + the admin check in each handler). The PUT writes ONE agents org
spec, `contatos_oficiais`, through the channel client with the acting user as `ator`; no other key can be reached (the route
builds the `valores` itself). The owner's own number is derived from core `noctus_users.telefone` at every request
(`julia_contatos_setoriais_service`), never typed here and never stored by SW. Each save records one `configuracao_alterada`
event (area, key, counts and the actor id: no names, no numbers).

Typed errors (pt-BR): 422 `setor_invalido` | `finalidade_invalida` | `nome_invalido` | `telefone_invalido` | `telefone_duplicado` |
`contatos_excede` | `finalidade_reservada`; 403 (not an org admin, before any call to agents); 409 `agente_nao_conectado`; 502 `agents_token_invalido` | `agents_indisponivel`; 404 `agente_nao_encontrado`.
"""
# No `from __future__ import annotations`: FastAPI body/param models are resolved from the signature.
import logging
from typing import Any, Optional

from fastapi import Depends, Request
from noctusai_lib.api import StrictHttpModel
from noctusai_lib.api.access_tiers import make_router
from noctusai_lib.api.auth._blocking import run_blocking
from noctusai_lib.api.auth.session import require_org_admin_for
from noctusai_lib.primitives.exceptions import AppException
from pydantic import Field

from app.clients.agents import AgentsClientError
from app.dependencies import coerce_org_uuid, get_core_client, get_current_user_org, get_scoped_admin_client
from app.routers.julia_especificacoes_router import _agents, _ator, _traduzir
from app.routers.whatsapp_connections_router import get_agents_client_factory
from app.services import julia_contatos_setoriais_service as svc
from app.services.julia_agente_service import DEFAULT_AGENT_KEY

logger = logging.getLogger(__name__)

router = make_router(
    tier="org", guard=get_current_user_org, prefix="/api/julia/contatos-setoriais", tags=["julia-contatos-setoriais"],
)

_O_QUE = "Os contatos por setor da Julia"


class ContatoIn(StrictHttpModel):
    setor: str = Field(max_length=40)
    finalidade: str = Field(max_length=400)
    nome: str = Field(max_length=200)
    telefone: str = Field(max_length=40)


class ContatosIn(StrictHttpModel):
    contatos: list[ContatoIn] = Field(max_length=20)


def get_contatos_setoriais_client() -> Any:
    """DI seam: the schema-scoped service-role client the events are written with (tests override)."""
    return get_scoped_admin_client("social_wiring")


def _valor_e_declarada(corpo: dict[str, Any]) -> tuple[Optional[str], bool]:
    declarada = any(d.get("chave") == svc.SPEC_CHAVE for d in corpo.get("declaradas") or [])
    for v in corpo.get("valores") or []:
        if v.get("chave") == svc.SPEC_CHAVE:
            return v.get("valor"), declarada
    return None, declarada


@router.get("")
async def ler(
    request: Request = None,
    auth: tuple = Depends(get_current_user_org),
    client_factory=Depends(get_agents_client_factory),
) -> dict[str, Any]:
    core = get_core_client()
    await run_blocking(require_org_admin_for, core, auth, request, _O_QUE)
    org_id = coerce_org_uuid(auth[2])
    agents = await run_blocking(_agents, client_factory, org_id)
    try:
        resposta = await agents.especificacoes(DEFAULT_AGENT_KEY)
    except AgentsClientError as exc:
        raise _traduzir(exc) from exc
    valor, declarada = _valor_e_declarada(resposta.corpo)
    dono = await run_blocking(svc.dono_da_org, core, org_id)
    return {"data": {**svc.montar(valor, dono), "declarada": declarada}}


@router.put("")
async def salvar(
    corpo: ContatosIn,
    request: Request = None,
    auth: tuple = Depends(get_current_user_org),
    client_factory=Depends(get_agents_client_factory),
    db: Any = Depends(get_contatos_setoriais_client),
) -> dict[str, Any]:
    core = get_core_client()
    await run_blocking(require_org_admin_for, core, auth, request, _O_QUE)
    org_id = coerce_org_uuid(auth[2])
    dono = await run_blocking(svc.dono_da_org, core, org_id)
    entradas = svc.validar([c.model_dump() for c in corpo.contatos], ha_dono=dono is not None)
    agents = await run_blocking(_agents, client_factory, org_id)
    ator = await run_blocking(_ator, auth, core)
    valor = svc.valor_a_salvar(entradas, dono)
    try:
        resposta = await agents.salvar_especificacoes(DEFAULT_AGENT_KEY, {svc.SPEC_CHAVE: valor}, ator)
    except AgentsClientError as exc:
        raise _traduzir(exc) from exc
    if resposta.status != 200:
        detalhe = str(resposta.corpo.get("detail") or "A Julia recusou os contatos.")
        raise AppException(str(resposta.corpo.get("code") or "contatos_recusados"), detalhe, status_code=422)
    await run_blocking(svc.registrar_evento, db, org_id, ator["user_id"], total=len(entradas) + (1 if dono else 0), com_dono=dono is not None)
    return {"data": {**svc.montar(valor, dono), "declarada": True}}
