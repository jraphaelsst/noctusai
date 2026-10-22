"""``/api/studio/agents/{key}/geracoes`` -- AI-generated first drafts (S3a).

One surface for the UI and the chat (MCP token): every route is ``require_platform_content_admin`` (a NoctusAI platform
admin session OR the ``studio:content-write`` content token); anything else is 401 / 403. Errors are the product's flat
body ``{code, message, detail}``. The POST routes book the run, answer 202 and schedule the job as a background task
(the eval-run pattern); the job's blocking store calls run off the event loop. Drafts only -- nothing publishes.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable
from uuid import UUID

import anyio.to_thread
from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.dependencies import (
    get_geracao_chat_dep,
    get_geracao_store_dep,
    get_skills_store_dep,
    require_platform_content_admin,
)
from app.routers.studio_agents_router import (
    actor_id,
    get_knowledge_catalog_dep,
    get_studio_definition_store_dep,
)
from app.schemas.studio_geracao import (
    Area,
    GeracaoCreateRequest,
    GeracaoOut,
    GeracoesOut,
    RepetirRequest,
)
from app.stores.errors import NotFound
from app.stores.studio_geracoes import AREAS
from app.studio import geracao as engine
from noctusai_lib.api.auth.session import AuthContext

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/studio", tags=["studio-geracoes"])


def get_geracao_agendador_dep(request: Request) -> Callable[[Any], None]:
    """Seam: ``schedule(coroutine)`` -- a strong reference is kept on ``app.state`` (the event loop only weakly
    references tasks). Tests override it to run the job explicitly."""
    from app.routers.conversations_router import _track_background_task

    def _schedule(coro) -> None:
        _track_background_task(request.app.state, asyncio.create_task(coro))

    return _schedule


def get_geracao_deps_dep(
    store=Depends(get_studio_definition_store_dep), geracoes=Depends(get_geracao_store_dep),
    skills=Depends(get_skills_store_dep), catalog=Depends(get_knowledge_catalog_dep),
    chat=Depends(get_geracao_chat_dep),
) -> engine.Dependencias:
    return engine.Dependencias(studio=store, geracoes=geracoes, skills=skills, catalog=catalog, chat=chat)


def _http(exc: engine.GeracaoErro) -> HTTPException:
    return HTTPException(status_code=exc.status, detail={"code": exc.code, "message": exc.message, "detail": exc.detail})


async def _sync(fn: Callable[[], Any]) -> Any:
    """Run blocking store work off the event loop; map the engine's refusals onto the flat error body."""
    try:
        return await anyio.to_thread.run_sync(fn)
    except engine.GeracaoErro as exc:
        raise _http(exc) from exc


def _saida(deps: engine.Dependencias, org_id: UUID, key: str, ids: list[UUID]) -> list[GeracaoOut]:
    agent = deps.studio.get_agent(org_id, key)
    return engine.montar_saida(deps, agent, [deps.geracoes.get_geracao(org_id, i) for i in ids])


def _agendar(schedule, deps, rec, agent, areas) -> None:
    schedule(engine.executar(deps, org_id=rec.org_id, geracao_id=rec.id, agent_id=agent.id, areas=areas))


@router.post("/agents/{key}/geracoes", status_code=status.HTTP_202_ACCEPTED, response_model=GeracaoOut)
async def criar_geracao(
    key: str, payload: GeracaoCreateRequest, ctx: AuthContext = Depends(require_platform_content_admin),
    deps: engine.Dependencias = Depends(get_geracao_deps_dep), schedule=Depends(get_geracao_agendador_dep),
) -> GeracaoOut:
    """Book an AI generation run for the agent's DRAFT and start it in the background. 202 + the run (``pendente``)."""
    ator = actor_id(ctx)
    rec, agent, areas = await _sync(lambda: engine.iniciar(
        deps, org_id=ctx.org_id, key=key, briefing=payload.briefing, areas=payload.areas, forcar=payload.forcar,
        limite_usd=payload.limite_usd, ator=ator))
    _agendar(schedule, deps, rec, agent, areas)
    return (await _sync(lambda: engine.montar_saida(deps, agent, [rec])))[0]


@router.get("/agents/{key}/geracoes", response_model=GeracoesOut)
def listar_geracoes(
    key: str, ctx: AuthContext = Depends(require_platform_content_admin),
    deps: engine.Dependencias = Depends(get_geracao_deps_dep),
) -> GeracoesOut:
    try:
        agent = deps.studio.get_agent(ctx.org_id, key)
    except NotFound as exc:
        raise _http(engine.GeracaoErro(404, "agente_nao_encontrado", "Agente não encontrado.")) from exc
    return GeracoesOut(items=engine.montar_saida(deps, agent, deps.geracoes.list_geracoes(ctx.org_id, agent.id, 20)))


@router.get("/agents/{key}/geracoes/{geracao_id}", response_model=GeracaoOut)
def obter_geracao(
    key: str, geracao_id: UUID, ctx: AuthContext = Depends(require_platform_content_admin),
    deps: engine.Dependencias = Depends(get_geracao_deps_dep),
) -> GeracaoOut:
    try:
        agent = deps.studio.get_agent(ctx.org_id, key)
    except NotFound as exc:
        raise _http(engine.GeracaoErro(404, "agente_nao_encontrado", "Agente não encontrado.")) from exc
    try:
        ger = deps.geracoes.get_geracao(ctx.org_id, geracao_id)
    except NotFound as exc:
        raise _http(engine.GeracaoErro(404, "geracao_nao_encontrada", "Geração não encontrada.")) from exc
    if ger.agent_id != agent.id:
        raise _http(engine.GeracaoErro(404, "geracao_nao_encontrada", "Geração não encontrada."))
    return engine.montar_saida(deps, agent, [ger])[0]


@router.post("/agents/{key}/geracoes/{geracao_id}/areas/{area}/repetir", status_code=status.HTTP_202_ACCEPTED, response_model=GeracaoOut)
async def repetir_area(
    key: str, geracao_id: UUID, area: str, payload: RepetirRequest,
    ctx: AuthContext = Depends(require_platform_content_admin),
    deps: engine.Dependencias = Depends(get_geracao_deps_dep), schedule=Depends(get_geracao_agendador_dep),
) -> GeracaoOut:
    """Run ONE area of an existing run again (``falhou|pulado|cancelada``; ``concluida`` needs ``forcar``)."""
    if area not in AREAS:
        raise HTTPException(
            status_code=422, detail={"code": "area_invalida", "message": "Área inválida.", "detail": list(AREAS)})
    ator = actor_id(ctx)
    rec, agent = await _sync(lambda: engine.repetir(
        deps, org_id=ctx.org_id, key=key, geracao_id=geracao_id, area=area, forcar=payload.forcar, ator=ator))
    _agendar(schedule, deps, rec, agent, [area])
    return (await _sync(lambda: engine.montar_saida(deps, agent, [rec])))[0]


@router.post("/agents/{key}/geracoes/{geracao_id}/cancelar", response_model=GeracaoOut)
def cancelar_geracao(
    key: str, geracao_id: UUID, ctx: AuthContext = Depends(require_platform_content_admin),
    deps: engine.Dependencias = Depends(get_geracao_deps_dep),
) -> GeracaoOut:
    """Cancel an in-flight run: an in-flight LLM call finishes but its output is discarded."""
    try:
        rec = engine.cancelar(deps, org_id=ctx.org_id, key=key, geracao_id=geracao_id)
    except engine.GeracaoErro as exc:
        raise _http(exc) from exc
    return engine.montar_saida(deps, deps.studio.get_agent(ctx.org_id, key), [rec])[0]


__all__ = ["router", "get_geracao_agendador_dep", "get_geracao_deps_dep"]
