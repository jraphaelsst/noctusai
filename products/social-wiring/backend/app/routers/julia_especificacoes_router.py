"""Julia > Especificações do negócio (Julia-line CONTRACT §C4 / §E): the org edits ITS business specifications, which
live and are validated in AGENTS -- SW is a faithful proxy, never a second validator, never a store.

  GET /api/julia/especificacoes   org admin  -> agents' body verbatim:
        {agent_key, version_id, versao, declaradas[{chave,rotulo,descricao,tipo,obrigatoria,exemplo}],
         valores[{chave,valor,updated_at,updated_by,updated_by_nome}], faltando[], invalidas[{chave,codigo,motivo,mensagem}], modo_validacao}
  PUT /api/julia/especificacoes   PLATFORM ADMIN only (owner 2026-11-04: SW users do not edit Julia's content for now -- an org admin gets
        a strict 403 `edicao_restrita_plataforma`; agents refuses channel-token writes with the same code and its body passes through)
        {"valores": {chave: texto}}   (the acting user -- id, name, e-mail -- is filled by
        THIS route from the session and sent to agents as `ator`; a body `ator` is refused, the body is `valores` only)
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
from app.dependencies import coerce_org_uuid, get_core_client, get_current_user_org, get_platform_admin_check
from app.routers.whatsapp_connections_router import get_agents_client_factory
from app.services.julia_agente_service import DEFAULT_AGENT_KEY

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/julia/especificacoes", tags=["julia-especificacoes"])

_O_QUE = "As especificações do negócio da Julia"


class EspecificacoesIn(StrictHttpModel):
    """``valores``: ``{chave: texto}``; a blank value clears the spec. Nothing else is accepted (the org comes from the session)."""

    valores: dict[str, str]


def _ator(auth: tuple, core: Any) -> dict[str, str]:
    """The ACTING USER, from the authenticated session only (agents records it as who changed the specs): id, display
    name (the org user row's ``nome``, else the session's own name) and e-mail. Never taken from the request body."""
    user = auth[0]
    ator: dict[str, str] = {"user_id": str(getattr(user, "id"))}
    nome = None
    try:
        rows = core.table("noctus_users").select("nome").eq("id", ator["user_id"]).limit(1).execute().data or []
        nome = (rows[0].get("nome") or "").strip() if rows else None
    except Exception as exc:  # the name is a courtesy: a failed lookup falls back to the session's, never blocks the save
        logger.warning("julia: could not read the acting user's name (%s)", type(exc).__name__)
    meta = getattr(user, "user_metadata", None) or {}
    nome = nome or (meta.get("nome") or meta.get("full_name") or meta.get("name") or "").strip() or None
    email = (getattr(user, "email", None) or "").strip() or None
    for chave, valor in (("nome", nome), ("email", email)):
        if valor:
            ator[chave] = valor
    return ator


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
    e_admin_da_plataforma=Depends(get_platform_admin_check),
) -> JSONResponse:
    core = get_core_client()
    if not await run_blocking(e_admin_da_plataforma, str(getattr(auth[0], "id", "") or "")):
        logger.warning("julia: specs write refused -- not a platform admin (edicao_restrita_plataforma)")
        raise AppException(
            "edicao_restrita_plataforma",
            "As especificações da Julia são configuradas pela equipe NoctusAI. Para alterar, fale com o suporte.",
            status_code=403,
        )
    agents = await run_blocking(_agents, client_factory, coerce_org_uuid(auth[2]))
    ator = await run_blocking(_ator, auth, core)
    try:
        resposta = await agents.salvar_especificacoes(DEFAULT_AGENT_KEY, corpo.valores, ator)
    except AgentsClientError as exc:
        raise _traduzir(exc) from exc
    return JSONResponse(resposta.corpo, status_code=resposta.status)
