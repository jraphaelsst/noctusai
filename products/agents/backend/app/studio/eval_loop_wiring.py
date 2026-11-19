"""Production wiring of the eval-loop driver: how a loop's next round is booked WITHOUT an HTTP request.

The driver calls the SAME functions the routes call (``reservar_run`` for the behaviour suite, ``iniciar_run_mecanismo`` for the
mechanism suite), so every guard applies unchanged: one run per user, the G6/G7 admission, the preflight, the spend ceiling. What a
request normally carries -- the caller's context and the resolved FastAPI dependencies -- is rebuilt here: the context is the loop
OWNER's (``started_by``), the dependencies are resolved by :func:`resolver_dep` honouring ``app.dependency_overrides`` (the product's
real seam bindings, or a test's fakes), never a second construction path.
"""
from __future__ import annotations

import asyncio
import inspect
from types import SimpleNamespace
from typing import Any

import anyio.to_thread
from fastapi import HTTPException, params

from app.stores.studio_eval_loops import LoopRecord
from app.studio.eval_loop_driver import LoopDriver, install_driver
from app.studio.eval_loop_refino import casos_falhando_comportamento, casos_falhando_mecanismo
from app.studio.eval_loop_refino_service import RefinoService
from app.studio.eval_loop_service import resumo_comportamento, resumo_mecanismo
from noctusai_lib.api.auth.session import AuthContext

__all__ = ["resolver_dep", "ctx_do_dono", "construir_driver", "instalar_driver"]


def resolver_dep(app: Any, dep: Any, explicit: dict[str, Any] | None = None) -> Any:
    """Call a FastAPI dependency outside a request: ``Depends(...)`` defaults are resolved recursively through
    ``app.dependency_overrides``; ``explicit`` supplies by parameter name what only a request carries (``ctx``, ``request``) at the
    top level. Sync dependencies only (every eval seam is sync); an async / generator one is refused loudly."""
    dep = app.dependency_overrides.get(dep, dep)
    if inspect.iscoroutinefunction(dep) or inspect.isasyncgenfunction(dep) or inspect.isgeneratorfunction(dep):
        raise TypeError(f"eval-loop driver cannot resolve the non-plain dependency {getattr(dep, '__name__', dep)!r}")
    kwargs: dict[str, Any] = {}
    for name, param in inspect.signature(dep).parameters.items():
        if explicit and name in explicit:
            kwargs[name] = explicit[name]
        elif isinstance(param.default, params.Depends):
            kwargs[name] = resolver_dep(app, param.default.dependency)
        elif param.default is inspect.Parameter.empty:
            raise LookupError(f"dependency {getattr(dep, '__name__', dep)!r} needs {name!r}, which a request carries")
    return dep(**kwargs)


def ctx_do_dono(rec: LoopRecord) -> AuthContext:
    """The loop owner's context (a human user; for a ``studio:evals-run`` token the id is the token row's, as ``started_by``
    recorded it): the actor of every round it books and the subject of the one-run-per-user rule."""
    return AuthContext(
        org_id=rec.org_id, caller_kind="user", user_id=rec.started_by, scopes=[], raw_token="eval-loop-driver", api_token_id=None)


def construir_driver(app: Any, event_loop: asyncio.AbstractEventLoop) -> LoopDriver:
    # imported here: the routers import this package's service, and the app is fully built before the driver starts
    from app.routers import studio_agents_router as agentes
    from app.routers import studio_evals_router as avaliacoes
    from app.studio.eval_driver import get_eval_turn_driver
    from app.studio.eval_preflight import preflight_mecanismo
    from app.studio.spend import get_spend_ceiling_dep

    def R(dep: Any, explicit: dict[str, Any] | None = None) -> Any:
        return resolver_dep(app, dep, explicit)

    def servico():
        return R(agentes.get_loop_service_dep)

    def ler_resumo(rec: LoopRecord, run_id):
        if rec.suite == "mecanismo":
            return resumo_mecanismo(R(agentes.get_mecanismo_store_dep), rec.org_id, rec.agent_id, run_id)
        return resumo_comportamento(R(agentes.get_eval_store_dep), rec.org_id, rec.agent_id, run_id)

    def ler_casos(rec: LoopRecord, run_id):
        if rec.suite == "mecanismo":
            return casos_falhando_mecanismo(R(agentes.get_mecanismo_store_dep), rec.org_id, rec.agent_id, run_id)
        return casos_falhando_comportamento(R(agentes.get_eval_store_dep), rec.org_id, rec.agent_id, run_id)

    def carimbar_hash(org_id, agent_id, draft_id) -> str:
        """Recompile the draft NOW (the same ``compile_version`` the rounds hash with), re-stamp its ``compiled_hash`` and return it."""
        defs = R(agentes.get_studio_definition_store_dep)
        agent = defs.get_agent_by_id(agent_id)
        _draft, compiled = agentes._refresh_draft_hash(defs, R(agentes.get_knowledge_catalog_dep), org_id, agent, draft_id)
        return compiled.hash

    def refino_service() -> RefinoService:
        return RefinoService(
            loops=servico().store, defs=R(agentes.get_studio_definition_store_dep), refinador=R(agentes.get_refinador_dep),
            refino=R(agentes.get_refino_store_dep), ler_casos=ler_casos, carimbar_hash=carimbar_hash)

    async def refinar(rec: LoopRecord) -> str:
        return await refino_service().refinar(rec)

    async def iniciar(rec: LoopRecord):
        ctx = ctx_do_dono(rec)
        if rec.suite == "mecanismo":
            res = await agentes.iniciar_run_mecanismo(
                ctx, rec.agente_chave, app.state, store=await anyio.to_thread.run_sync(lambda: R(agentes.get_studio_definition_store_dep)),
                mecanismo=R(agentes.get_mecanismo_store_dep), catalog=R(agentes.get_knowledge_catalog_dep),
                driver=get_eval_turn_driver(), ceiling=R(get_spend_ceiling_dep),
                consolidacao=R(agentes.get_consolidacao_store_dep), loops=servico(), evals=R(agentes.get_eval_store_dep),
                loop_id=rec.id, preflight=preflight_mecanismo)
            return res.run_id

        def reservar():
            from app.schemas.studio_ke import EvalRunCreateRequest

            defs = R(agentes.get_studio_definition_store_dep)
            draft = defs.get_draft(rec.org_id, rec.agent_id)
            if draft is None:
                raise HTTPException(409, detail={"detail": "O agente não tem rascunho para avaliar.", "code": "no_draft"})
            store = R(agentes.get_eval_store_dep)
            loops = servico()
            run = avaliacoes.reservar_run(
                ctx, rec.agente_chave, EvalRunCreateRequest(version_id=draft.id, loop_id=rec.id), store=store, defs=defs,
                current_hash=R(avaliacoes.get_current_hash_dep), current_partes=R(avaliacoes.get_current_partes_dep),
                consol=R(agentes.get_consolidacao_store_dep), ceiling=R(get_spend_ceiling_dep), loops=loops,
                mecanismo=R(agentes.get_mecanismo_store_dep), preflight=R(avaliacoes.get_preflight_dep))
            agendador = R(avaliacoes.get_eval_scheduler_dep, {"request": SimpleNamespace(app=app), "ctx": ctx})
            return run, agendador, store, loops

        run, agendador, store, loops = await anyio.to_thread.run_sync(reservar)
        try:
            agendador(run.id)  # asyncio.create_task: needs THIS (running) loop
        except avaliacoes.EvalSchedulerUnavailable as exc:
            await anyio.to_thread.run_sync(lambda: store.mark_run_failed(rec.org_id, run.id, erro="eval_runner_unavailable"))
            await anyio.to_thread.run_sync(lambda: loops.fechar_sem_falhar(
                rec.org_id, lambda: resumo_comportamento(store, rec.org_id, rec.agent_id, run.id), run_id=run.id,
                run_tipo="comportamento"))
            raise HTTPException(503, detail={
                "detail": "O executor de avaliações não está disponível.", "code": "eval_runner_unavailable"}) from exc
        return run.id

    return LoopDriver(servico=servico, iniciar=iniciar, ler_resumo=ler_resumo, event_loop=event_loop, refinar=refinar)


async def instalar_driver(app: Any) -> int:
    """Startup (after the orphan sweeps): build the driver, register it for the close hook and resume every active automatic
    loop from the DB state. Returns how many loops were resumed."""
    driver = construir_driver(app, asyncio.get_running_loop())
    install_driver(driver)
    return await driver.retomar_todos()
