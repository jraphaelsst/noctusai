"""Julia > Opt-outs (owner decisions 2026-10-21): per-org lead opt-out history, reactivation, "do not contact", and the
data-subject requests a lead sent.

  GET   /api/julia/opt-outs?limit&cursor&lead_ref                       member  {data:{items,next_cursor}}   (agents' history, newest first)
  POST  /api/julia/opt-outs/{evento_id}/notificar                       admin   {data: evento}              (send the admins' notice again)
  GET   /api/julia/opt-outs/leads/{contato_id}/estado                   member* {data:{verificado,opt_out_ativo,opt_out_em,motivo,...}}
  POST  /api/julia/opt-outs/leads/{contato_id}/nao-contatar {motivo}    admin   {data:{...}}                (origem `operador`, actor = caller)
  POST  /api/julia/opt-outs/leads/{contato_id}/reativar {motivo}        admin   {data:{opt_out_ativo,evento}}
  GET   /api/julia/opt-outs/conversas/{connection_id}/{chat_id}/estado  member* {data: same as `estado`}   (the operator composer's warning)
  GET   /api/julia/opt-outs/solicitacoes?status&page&page_size          member  {data:{items,total}}        (data-subject requests, with `prazo_situacao`)
  PATCH /api/julia/opt-outs/solicitacoes/{id} {status,motivo?}          admin   {data: solicitacao}   (decision; `negada` needs the motivo)

* a per-lead route obeys the per-contato access rule A7 (`julia_acesso`): 404 for another org's contato, 403 `sem_acesso`.
The opt-out itself lives in AGENTS (the leads are the org's, not the platform's); SW keeps no copy and a failed read is
`verificado: false` -- never "no opt-out". A human operator is never blocked from messaging an opted-out lead.
Errors are typed codes: 503 `agents_nao_configurado`, 502 `agents_token_invalido` / `agents_indisponivel`, 409 `sem_opt_out_ativo`,
404 `lead_desconhecido` / `opt_out_nao_encontrado`, 422 `motivo_obrigatorio`.
"""
import anyio
# No `from __future__ import annotations`: FastAPI body/param models are resolved from the signature.
import logging
from typing import Any, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import Field

from noctusai_lib.api import StrictHttpModel
from noctusai_lib.api.auth._blocking import run_blocking
from noctusai_lib.api.auth.session import require_org_admin_for

from app.dependencies import coerce_org_uuid, get_core_client, get_current_user_org, get_scoped_admin_client
from app.routers.whatsapp_connections_router import get_agents_client_factory
from app.services import julia_acesso, julia_opt_out_service as svc, julia_solicitacoes_titular_service as solicitacoes

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/julia/opt-outs", tags=["julia-opt-outs"])


def get_opt_outs_client() -> Any:
    """DI seam: the schema-scoped service-role client (tests override)."""
    return get_scoped_admin_client("social_wiring")


class MotivoIn(StrictHttpModel):
    motivo: str = Field(min_length=1, max_length=svc.MOTIVO_MARCACAO_MAX)


class SolicitacaoPatch(StrictHttpModel):
    status: Literal["aberta", "em_analise", "atendida", "negada", "cancelada"]
    motivo: Optional[str] = Field(default=None, max_length=solicitacoes.MOTIVO_MAX)


def _org(auth: tuple) -> UUID:
    return coerce_org_uuid(auth[2])


def _uid(auth: tuple) -> str:
    return str(auth[0].id)


def _admin(auth: tuple, request: Optional[Request], what: str) -> None:
    require_org_admin_for(get_core_client(), auth, request, what)


# ── data-subject requests (declared first: `/solicitacoes` must not be read as an `{evento_id}`) ───────────
@router.get("/solicitacoes")
def listar_solicitacoes(
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=solicitacoes.PAGE_SIZE_MAX),
    auth: tuple = Depends(get_current_user_org),
    client: Any = Depends(get_opt_outs_client),
) -> dict[str, Any]:
    return {"data": solicitacoes.listar(client, _org(auth), status=status, page=page, page_size=page_size)}


@router.patch("/solicitacoes/{solicitacao_id}")
def decidir_solicitacao(
    solicitacao_id: UUID,
    corpo: SolicitacaoPatch,
    request: Request = None,
    auth: tuple = Depends(get_current_user_org),
    client: Any = Depends(get_opt_outs_client),
) -> dict[str, Any]:
    _admin(auth, request, "A decisão sobre solicitações de dados")
    return {"data": solicitacoes.decidir(client, _org(auth), solicitacao_id, _uid(auth), status=corpo.status, motivo=corpo.motivo)}


# ── the history ─────────────────────────────────────────────────────────────
@router.get("")
async def historico(
    limit: int = Query(svc.LIMITE_PADRAO, ge=1, le=100),
    cursor: Optional[str] = Query(None, max_length=500),
    lead_ref: Optional[str] = Query(None, max_length=64),
    auth: tuple = Depends(get_current_user_org),
    client_factory=Depends(get_agents_client_factory),
) -> dict[str, Any]:
    org = _org(auth)
    agents = svc.exigir_agents(client_factory, org)
    return {"data": await svc.historico(agents, get_core_client(), org, limit=limit, cursor=cursor, lead_ref=lead_ref)}


@router.post("/{evento_id}/notificar")
async def renotificar(
    evento_id: str,
    request: Request = None,
    auth: tuple = Depends(get_current_user_org),
    client_factory=Depends(get_agents_client_factory),
) -> dict[str, Any]:
    await run_blocking(_admin, auth, request, "O reenvio da notificação de opt-out")
    org = _org(auth)
    agents = await run_blocking(svc.exigir_agents, client_factory, org)
    return {"data": await svc.renotificar(agents, get_core_client(), org, evento_id, ator_user_id=_uid(auth))}


# ── per lead ────────────────────────────────────────────────────────────────
@router.get("/leads/{contato_id}/estado")
async def estado_do_lead(
    contato_id: UUID,
    request: Request = None,
    auth: tuple = Depends(get_current_user_org),
    client: Any = Depends(get_opt_outs_client),
    client_factory=Depends(get_agents_client_factory),
) -> dict[str, Any]:
    org = _org(auth)
    contato = (await anyio.to_thread.run_sync(lambda: julia_acesso.exigir_contato(client, julia_acesso.contexto(auth, request), contato_id)))
    return {"data": await svc.estado_do_contato(client_factory(org), str(contato["id"]))}


@router.post("/leads/{contato_id}/nao-contatar")
async def nao_contatar(
    contato_id: UUID,
    corpo: MotivoIn,
    request: Request = None,
    auth: tuple = Depends(get_current_user_org),
    client: Any = Depends(get_opt_outs_client),
    client_factory=Depends(get_agents_client_factory),
) -> dict[str, Any]:
    await run_blocking(_admin, auth, request, "Marcar um lead como não contatar")
    org = _org(auth)
    contato = (await anyio.to_thread.run_sync(lambda: julia_acesso.exigir_contato(client, julia_acesso.contexto(auth, request), contato_id)))
    agents = await run_blocking(svc.exigir_agents, client_factory, org)
    return {"data": await svc.marcar_nao_contatar(client, agents, org, contato, motivo=corpo.motivo, ator_user_id=_uid(auth))}


@router.post("/leads/{contato_id}/reativar")
async def reativar(
    contato_id: UUID,
    corpo: MotivoIn,
    request: Request = None,
    auth: tuple = Depends(get_current_user_org),
    client: Any = Depends(get_opt_outs_client),
    client_factory=Depends(get_agents_client_factory),
) -> dict[str, Any]:
    await run_blocking(_admin, auth, request, "A reativação do atendimento de um lead")
    org = _org(auth)
    contato = (await anyio.to_thread.run_sync(lambda: julia_acesso.exigir_contato(client, julia_acesso.contexto(auth, request), contato_id)))
    agents = await run_blocking(svc.exigir_agents, client_factory, org)
    return {"data": await svc.reativar(agents, contato, motivo=corpo.motivo, ator_user_id=_uid(auth))}


# ── the operator composer's warning ─────────────────────────────────────────
@router.get("/conversas/{connection_id}/{chat_id:path}/estado")
async def estado_da_conversa(
    connection_id: UUID,
    chat_id: str,
    request: Request = None,
    auth: tuple = Depends(get_current_user_org),
    client: Any = Depends(get_opt_outs_client),
    client_factory=Depends(get_agents_client_factory),
) -> dict[str, Any]:
    org = _org(auth)
    contato = (await anyio.to_thread.run_sync(lambda: svc.contato_da_conversa(client, org, connection_id, chat_id)))
    if contato is not None:
        julia_acesso.exigir_acesso(client, julia_acesso.contexto(auth, request), contato)
    return {"data": await svc.estado_do_contato(client_factory(org), str(contato["id"]) if contato else None)}


__all__ = ["router"]
