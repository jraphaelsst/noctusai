"""Julia > Especificações do negócio (Julia-line CONTRACT §C4 / §E): the org edits ITS business specifications, which
live and are validated in AGENTS -- SW is a faithful proxy, never a second validator, never a store.

  GET /api/julia/especificacoes   org admin  -> agents' body verbatim:
        {agent_key, version_id, versao, declaradas[{chave,rotulo,descricao,tipo,obrigatoria,exemplo}],
         valores[{chave,valor,updated_at}], faltando[], invalidas[{chave,codigo,motivo,mensagem}], modo_validacao}
  PUT /api/julia/especificacoes   org admin  {"valores": {chave: texto}}
        200 -> the same body (report mode lists `invalidas`; the write landed)
        422 -> agents' body verbatim: {code, detail, violacoes[{chave,codigo,motivo,mensagem}]} (block mode, or
               `spec_nao_declarada` for a key the definition does not declare)

Only the org's DECLARED business values travel; the core (prompt, fixed rules, tools) is not reachable from here.
Calls go through ``clients/agents.py`` with the org's own ``api_key:agents`` credential (the platform grant delivers it).
Typed errors (never silent): 409 `agente_nao_conectado` (no credential), 502 `agents_token_invalido` /
`agents_indisponivel`, 404 `agente_nao_encontrado`.
"""
# No `from __future__ import annotations`: FastAPI body/param models are resolved from the signature.
import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from noctusai_lib.api import StrictHttpModel
from noctusai_lib.api.auth._blocking import run_blocking
from noctusai_lib.api.auth.session import require_org_admin_for
from noctusai_lib.primitives.exceptions import AppException

from app.clients.agents import AgentNotFound, AgentsClient, AgentsClientError, AgentsTokenInvalid
from app.dependencies import coerce_org_uuid, get_core_client, get_current_user_org
from app.routers.whatsapp_connections_router import get_agents_client_factory
from app.services.julia_agente_service import DEFAULT_AGENT_KEY

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/julia/especificacoes", tags=["julia-especificacoes"])

_O_QUE = "As especificações do negócio da Julia"


class EspecificacoesIn(StrictHttpModel):
    """``valores``: ``{chave: texto}``; a blank value clears the spec. Nothing else is accepted (the org comes from the session)."""

    valores: dict[str, str]


def _agents(client_factory: Any, org_id: Any) -> AgentsClient:
    agents: Optional[AgentsClient] = client_factory(org_id)
    if agents is None:
        raise AppException(
            "agente_nao_conectado", "A Julia ainda não foi conectada à sua organização pela plataforma.", status_code=409,
        )
    return agents


def _traduzir(exc: AgentsClientError) -> AppException:
    if isinstance(exc, AgentNotFound):
        return AppException("agente_nao_encontrado", "A Julia não foi encontrada para esta organização.", status_code=404)
    if isinstance(exc, AgentsTokenInvalid):
        return AppException("agents_token_invalido", "O acesso ao agente é inválido.", status_code=502)
    logger.warning("julia: agents specs call failed (%s)", type(exc).__name__)
    return AppException("agents_indisponivel", "O agente está indisponível agora.", status_code=502)


@router.get("")
async def ler(
    request: Request = None,
    auth: tuple = Depends(get_current_user_org),
    client_factory=Depends(get_agents_client_factory),
) -> JSONResponse:
    await run_blocking(require_org_admin_for, get_core_client(), auth, request, _O_QUE)
    agents = await run_blocking(_agents, client_factory, coerce_org_uuid(auth[2]))
    try:
        resposta = await agents.especificacoes(DEFAULT_AGENT_KEY)
    except AgentsClientError as exc:
        raise _traduzir(exc) from exc
    return JSONResponse(resposta.corpo, status_code=resposta.status)


@router.put("")
async def salvar(
    corpo: EspecificacoesIn,
    request: Request = None,
    auth: tuple = Depends(get_current_user_org),
    client_factory=Depends(get_agents_client_factory),
) -> JSONResponse:
    await run_blocking(require_org_admin_for, get_core_client(), auth, request, _O_QUE)
    agents = await run_blocking(_agents, client_factory, coerce_org_uuid(auth[2]))
    try:
        resposta = await agents.salvar_especificacoes(DEFAULT_AGENT_KEY, corpo.valores)
    except AgentsClientError as exc:
        raise _traduzir(exc) from exc
    return JSONResponse(resposta.corpo, status_code=resposta.status)
