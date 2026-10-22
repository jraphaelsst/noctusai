"""The qualification-standard pin of a platform-defined agent (Julia v2 A-RT2; CONTRACT 3.1).

* ``GET /api/studio/agents/{key}/qualificacao`` -- which standard version the ACTIVE version and the DRAFT pin,
  the newest published one, and the "new standard version available" indicator.
* ``PUT /api/studio/agents/{key}/draft/qualificacao`` -- move (or clear) the DRAFT's pin. Platform admin only
  (the standard is platform IP); the move invalidates the judged hash, so an eval must run again before publish.

Publish stamps the pin itself (``publish_draft``: an unpinned draft gets the newest published standard version);
a new draft inherits the pin of the version it is based on (migration 040).
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.dependencies import require_platform_admin
from app.qualificacao.store import PadraoStore
from app.routers.qualificacao_router import get_padrao_store_dep
from app.routers.studio_agents_router import (
    _refresh_draft_hash,
    actor_id,
    audit_definition_read,
    get_knowledge_catalog_dep,
    get_studio_definition_store_dep,
    http_error,
    resolve_agent,
    resolve_draft,
    store_errors,
)
from app.stores.errors import NotFound
from app.studio.plataforma import padrao_de
from noctusai_lib.api import StrictHttpModel
from noctusai_lib.api.auth.session import AuthContext

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/studio", tags=["studio-padrao"])

__all__ = ["router", "estampar_padrao_no_rascunho"]


class PadraoVersaoOut(BaseModel):
    id: UUID
    versao: int
    status: str


class PinOut(BaseModel):
    """A pin: the standard version it targets and whether a newer published one exists."""

    versao: PadraoVersaoOut | None = None
    atualizacao_disponivel: bool = False


class QualificacaoPinOut(BaseModel):
    padrao: str
    ativa: PinOut | None = None
    rascunho: PinOut | None = None
    mais_nova: PadraoVersaoOut | None = None


class PinRequest(StrictHttpModel):
    #: ``null`` clears the pin (publish then stamps the newest published version).
    versao_id: UUID | None = None


def _chave_do_padrao(agent) -> str:
    chave = padrao_de(agent)
    if chave is None:
        raise http_error(409, "sem_padrao", "Este agente não tem padrão de qualificação.")
    return chave


def _mais_nova(padroes: PadraoStore, chave: str) -> PadraoVersaoOut | None:
    try:
        v = padroes.obter_versao_publicada(chave)
    except NotFound:
        return None
    return PadraoVersaoOut(id=v.id, versao=v.versao, status=v.status)


def _pin(padroes: PadraoStore, version, nova: PadraoVersaoOut | None) -> PinOut | None:
    if version is None:
        return None
    pin = getattr(version, "qualificacao_versao_id", None)
    if pin is None:
        return PinOut()
    try:
        v = padroes.obter_versao(pin)
    except NotFound:
        return PinOut()
    return PinOut(
        versao=PadraoVersaoOut(id=v.id, versao=v.versao, status=v.status),
        atualizacao_disponivel=nova is not None and nova.id != v.id,
    )


def _estado(store, padroes: PadraoStore, org_id: UUID, agent) -> QualificacaoPinOut:
    chave = _chave_do_padrao(agent)
    nova = _mais_nova(padroes, chave)
    return QualificacaoPinOut(
        padrao=chave,
        ativa=_pin(padroes, store.get_active_version(org_id, agent.id), nova),
        rascunho=_pin(padroes, store.get_draft(org_id, agent.id), nova),
        mais_nova=nova,
    )


def estampar_padrao_no_rascunho(store, padroes: PadraoStore, org_id: UUID, agent, draft) -> Any:
    """Publish-time stamp: a draft with no pin gets the newest PUBLISHED version of the agent's standard (an
    already-pinned draft keeps its pin -- the indicator tells the admin a newer one exists). Returns the draft
    (re-read when stamped). An agent with no standard is left alone; a standard with no published version
    refuses the publish (409 ``qualificacao_indisponivel``): a turn could not run on it."""
    chave = padrao_de(agent)
    if chave is None or draft.qualificacao_versao_id is not None:
        return draft
    try:
        nova = padroes.obter_versao_publicada(chave)
    except NotFound as exc:
        raise http_error(409, "qualificacao_indisponivel", "O padrão de qualificação não está publicado.") from exc
    with store_errors():
        return store.update_draft(org_id, draft.id, {"qualificacao_versao_id": nova.id})


@router.get("/agents/{key}/qualificacao", response_model=QualificacaoPinOut)
def ler_pin(
    key: str,
    ctx: AuthContext = Depends(require_platform_admin),
    store=Depends(get_studio_definition_store_dep),
    padroes: PadraoStore = Depends(get_padrao_store_dep),
) -> QualificacaoPinOut:
    agent = resolve_agent(store, ctx.org_id, key)
    audit_definition_read(store, ctx, agent, "qualificacao_pin")
    return _estado(store, padroes, ctx.org_id, agent)


@router.put("/agents/{key}/draft/qualificacao", response_model=QualificacaoPinOut)
def mover_pin(
    key: str,
    payload: PinRequest,
    ctx: AuthContext = Depends(require_platform_admin),
    store=Depends(get_studio_definition_store_dep),
    catalog=Depends(get_knowledge_catalog_dep),
    padroes: PadraoStore = Depends(get_padrao_store_dep),
) -> QualificacaoPinOut:
    agent = resolve_agent(store, ctx.org_id, key)
    chave = _chave_do_padrao(agent)
    draft = resolve_draft(store, ctx.org_id, agent)
    if payload.versao_id is not None:
        try:
            alvo = padroes.obter_versao(payload.versao_id)
        except NotFound as exc:
            raise http_error(404, "padrao_versao_not_found", "Versão do padrão não encontrada.") from exc
        if alvo.padrao_chave != chave:
            raise http_error(422, "invalid_field", "A versão pertence a outro padrão.")
        if alvo.status not in ("publicada", "arquivada"):
            raise http_error(409, "padrao_nao_publicado", "Só uma versão publicada do padrão pode ser fixada.")
    antes = draft.qualificacao_versao_id
    with store_errors():
        store.update_draft(ctx.org_id, draft.id, {"qualificacao_versao_id": payload.versao_id})
    store.append_audit(
        agent.org_id, agent.id, actor_id(ctx), "conteudo_editado_mcp",
        {"o_que": "padrao_fixado", "version_id": str(draft.id), "de": str(antes) if antes else None},
        {"o_que": "padrao_fixado", "version_id": str(draft.id), "para": str(payload.versao_id) if payload.versao_id else None},
    )
    _refresh_draft_hash(store, catalog, ctx.org_id, agent, draft.id)
    return _estado(store, padroes, ctx.org_id, agent)
