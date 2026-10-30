"""Renata cutover (agents-unified): move a code-defined chat agent's in-app history onto a Studio agent, retire the
code-defined rows so their key is free, and tell the old chat URLs where the academia's agent lives now.

* ``POST /api/agents/{source_key}/transferir-historico`` -- conversations (with their messages, approvals and
  session transcripts, i.e. the agent's memory) + the tokens bound to the source as principal move to
  ``target_key``, in ONE transaction (053 ``agents.transferir_historico_agente``), audited as the definition event
  ``historico_transferido``. ``dry_run`` (default TRUE) answers the counts and writes nothing. Idempotent: a re-run
  finds nothing left on the source. When the platform's academia principal (``academia_agent_id``) named the
  source, it is re-pointed to the target in the same call.
* ``POST /api/agents/{key}/arquivar`` -- ``definition_mode`` ``legacy`` -> ``arquivado`` for the code-defined rows of
  ``key`` (this org, or every org with ``todas_orgs``); the row's key becomes ``<key>-arquivado-<id8>``, so ``key``
  is free. Refused (409 ``historico_pendente``) while a row still owns a conversation. Dry run by default.
* ``GET /api/agents/painel/destino-chat`` -- the in-app chat agent of the caller's org that the legacy ``/bia`` and
  ``/agentes/bia/...`` URLs resolve to: the agent the academia principal names (when it is this org's), else the
  org's code-defined chat agent, else 404. Decided by data, never by a hard-coded key.

The two writes are NoctusAI-superadmin only: anyone else gets **404, never 403** (D31 -- a 403 would confirm what is
behind the route); no credential is a strict 401.
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field

from app.config import settings
from app.dependencies import get_agent_store_dep, get_credential_service_dep, require_member
from app.routers.agente_painel_router import tier_do_chamador
from app.routers.studio_agents_router import actor_id, get_studio_definition_store_dep
from app.stores._db_errors import StudioConflict
from app.stores.errors import NotFound
from app.studio.plataforma import ensure_instancia
from noctusai_lib.api import StrictHttpModel
from noctusai_lib.api.auth.session import AuthContext

logger = logging.getLogger(__name__)

router = APIRouter(tags=["agentes"])

__all__ = ["router", "get_cutover_store_dep"]

_NAO_ENCONTRADO = {"detail": "Agente não encontrado.", "code": "agent_not_found"}
_KEY = r"^[a-z][a-z0-9-]{1,63}$"
_ACADEMIA_AGENT_CREDENTIAL = "academia_agent_id"


def get_cutover_store_dep():
    """Seam over ``get_cutover_store`` -- the router suites override it with a ``FakeCutoverStore``."""
    from app.stores.cutover import get_cutover_store

    return get_cutover_store(settings)


class TransferirHistoricoIn(StrictHttpModel):
    target_key: str = Field(pattern=_KEY)
    dry_run: bool = True


class TransferirHistoricoOut(StrictHttpModel):
    source_key: str
    target_key: str
    target_agent_id: UUID
    dry_run: bool
    conversas: int
    mensagens: int
    aprovacoes: int
    transcricoes: int
    tokens: int
    tokens_academia: int
    executado: bool
    #: ``repontado`` (the academia principal named the source and now names the target) · ``ja_aponta`` ·
    #: ``nao_aplicavel`` (it names another agent / none) · ``seria_repontado`` (dry run) · ``falhou`` (history moved,
    #: the credential write failed -- set it on the Credenciais page).
    credencial_academia: str


class ArquivarIn(StrictHttpModel):
    dry_run: bool = True
    todas_orgs: bool = False


class ArquivarOut(StrictHttpModel):
    key: str
    dry_run: bool
    todas_orgs: bool
    linhas: int
    com_historico: int
    executado: bool


class DestinoChatOut(StrictHttpModel):
    key: str
    #: ``academia`` (the academia principal's agent) · ``legado`` (the org's code-defined chat agent).
    origem: str


def _so_superadmin(ctx: AuthContext, request: Request) -> None:
    if tier_do_chamador(ctx, request) != "plataforma":
        raise HTTPException(status_code=404, detail=_NAO_ENCONTRADO)


def _conflito(exc: StudioConflict) -> HTTPException:
    textos = {
        "origem_invalida": "A origem não é um agente de código desta organização.",
        "destino_invalido": "O destino não é um agente do Studio desta organização.",
        "mesmo_agente": "Origem e destino são o mesmo agente.",
        "historico_pendente": "O agente ainda tem conversas — transfira o histórico antes de arquivar.",
    }
    return HTTPException(status_code=409, detail={"detail": textos.get(exc.code, str(exc)), "code": exc.code})


def _academia_agent_id(credenciais: Any) -> str | None:
    principal = credenciais.academia_agent_id()
    return str(principal) if principal else None


@router.post("/api/agents/{source_key}/transferir-historico", response_model=TransferirHistoricoOut)
def transferir_historico(
    source_key: str,
    payload: TransferirHistoricoIn,
    request: Request,
    ctx: AuthContext = Depends(require_member),
    agentes=Depends(get_agent_store_dep),
    studio_store=Depends(get_studio_definition_store_dep),
    cutover=Depends(get_cutover_store_dep),
    credenciais=Depends(get_credential_service_dep),
) -> TransferirHistoricoOut:
    _so_superadmin(ctx, request)
    try:
        origem = agentes.get_by_key(ctx.org_id, source_key)
    except NotFound:
        raise HTTPException(status_code=404, detail=_NAO_ENCONTRADO)
    # the org's row for the target: an org Studio agent, or (created here if missing) its instance of a platform
    # definition granted to it -- Renata is created by the wizard in the platform org.
    destino = ensure_instancia(ctx.org_id, payload.target_key, studio_store=studio_store)
    if destino is None:
        raise HTTPException(status_code=404, detail=_NAO_ENCONTRADO)
    try:
        contagem = cutover.transferir_historico(
            ctx.org_id, origem.id, destino.id, actor=actor_id(ctx), executar=not payload.dry_run,
        )
    except StudioConflict as exc:
        raise _conflito(exc) from exc

    atual = _academia_agent_id(credenciais)
    if atual == str(destino.id):
        credencial = "ja_aponta"
    elif atual != str(origem.id):
        credencial = "nao_aplicavel"
    elif payload.dry_run:
        credencial = "seria_repontado"
    else:
        try:
            credenciais.set_value(_ACADEMIA_AGENT_CREDENTIAL, str(destino.id))
            credencial = "repontado"
        except Exception as exc:  # the history already moved (committed) -- report it, never mask it as a success
            logger.error("agents.cutover.credential_repoint_failed error=%s", type(exc).__name__)
            credencial = "falhou"
    logger.info(
        "agents.cutover.transferir_historico org=%s source=%s target=%s dry_run=%s conversas=%d executado=%s "
        "credencial=%s", ctx.org_id, source_key, payload.target_key, payload.dry_run, contagem.conversas,
        contagem.executado, credencial,
    )
    return TransferirHistoricoOut(
        source_key=source_key, target_key=payload.target_key, target_agent_id=destino.id, dry_run=payload.dry_run,
        conversas=contagem.conversas, mensagens=contagem.mensagens, aprovacoes=contagem.aprovacoes,
        transcricoes=contagem.transcricoes, tokens=contagem.tokens, tokens_academia=contagem.tokens_academia,
        executado=contagem.executado, credencial_academia=credencial,
    )


@router.post("/api/agents/{key}/arquivar", response_model=ArquivarOut)
def arquivar_agente(
    key: str,
    payload: ArquivarIn,
    request: Request,
    ctx: AuthContext = Depends(require_member),
    cutover=Depends(get_cutover_store_dep),
) -> ArquivarOut:
    _so_superadmin(ctx, request)
    try:
        r = cutover.arquivar_legado(
            key, None if payload.todas_orgs else ctx.org_id, actor=actor_id(ctx), executar=not payload.dry_run,
        )
    except StudioConflict as exc:
        raise _conflito(exc) from exc
    if r.linhas == 0:
        raise HTTPException(status_code=404, detail=_NAO_ENCONTRADO)
    logger.info(
        "agents.cutover.arquivar org=%s key=%s todas_orgs=%s dry_run=%s linhas=%d executado=%s",
        ctx.org_id, key, payload.todas_orgs, payload.dry_run, r.linhas, r.executado,
    )
    return ArquivarOut(
        key=key, dry_run=payload.dry_run, todas_orgs=payload.todas_orgs, linhas=r.linhas,
        com_historico=r.com_historico, executado=r.executado,
    )


@router.get("/api/agents/painel/destino-chat", response_model=DestinoChatOut)
def destino_chat(
    ctx: AuthContext = Depends(require_member),
    agentes=Depends(get_agent_store_dep),
    studio_store=Depends(get_studio_definition_store_dep),
    credenciais=Depends(get_credential_service_dep),
) -> DestinoChatOut:
    principal = _academia_agent_id(credenciais)
    if principal:
        try:
            agente = studio_store.get_agent_by_id(UUID(principal))
        except NotFound:
            agente = None
        if agente is not None and agente.org_id == ctx.org_id and agente.definition_mode != "arquivado":
            return DestinoChatOut(key=agente.key, origem="academia")
    legados = [a for a in agentes.list(ctx.org_id) if a.chat_legado]
    if len(legados) == 1:
        return DestinoChatOut(key=legados[0].key, origem="legado")
    raise HTTPException(status_code=404, detail=_NAO_ENCONTRADO)
