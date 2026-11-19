"""``/api/studio/agents/{key}/evals/loops`` -- the eval-loop gate (owner spec 2026-11-09, G1-G7; migration 076).

A loop is a refinement session of one suite of one agent: it declares its planned rounds, a target, a floor (the
agent's ``publicacao_limiar``) and a budget; target / budget cap / max rounds are the platform config (migration 086). Runs started with ``loop_id`` are its rounds
(``POST .../evals/runs`` body ``loop_id``; ``POST .../draft/mecanismo-runs?loop_id=``); when one ends the gate stops the
loop at the target / after 2 rounds without improvement / at the budget and notifies the platform admins in-app mid-flight.

Auth mirrors the run routes: start / read = ``require_evals_run_access`` (a platform admin, a ``studio:publish`` token on a
dev agent, or the platform-issued ``studio:evals-run`` token); stop = ``require_evals_run_cancel``. No caller may exceed the configured budget cap or max rounds. Error codes (409): ``loop_ativo_existente``, ``loop_ja_encerrado``, ``execucao_em_andamento`` / ``loop_ativo_do_usuario`` (one run / loop per user, migration 087); (404)
``loop_not_found``; (422) ``orcamento_acima_do_teto``, ``rodadas_acima_do_maximo``. The run-start codes live on the run routes (see the contract).
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.dependencies import require_evals_run_access, require_evals_run_cancel, require_platform_admin
from app.routers.studio_agents_router import (
    get_eval_loop_config_store_dep,
    get_eval_store_dep,
    get_loop_service_dep,
    get_loop_store_dep,
    get_mecanismo_store_dep,
    get_studio_definition_store_dep,
    actor_id,
    guard_um_por_usuario,
    http_error,
    require_user_or_dev_advisor,
)
from app.routers.studio_knowledge_router import resolve_studio_agent
from app.schemas.studio_eval_loops import (
    EvalLoopConfigIn,
    EvalLoopConfigOut,
    LoopCreateRequest,
    LoopEventoOut,
    LoopEventosOut,
    LoopListOut,
    LoopModoRequest,
    LoopOut,
    LoopStopRequest,
)
from app.stores._db_errors import StudioConflict, mensagem_conflito
from app.stores.eval_loop_config import ConfigRegistrada
from app.studio.eval_loop_config import EvalLoopConfig, resolver_criacao
from app.studio.eval_loop_refino import EVENTOS_REFINO
from app.studio.eval_loop_service import EvalLoopService
from noctusai_lib.api.auth.session import AuthContext

router = APIRouter(prefix="/api/studio/agents", tags=["studio-eval-loops"], include_in_schema=False)


@router.post("/{key}/evals/loops", response_model=LoopOut, status_code=status.HTTP_201_CREATED)
def start_loop(
    key: str,
    payload: LoopCreateRequest,
    ctx: AuthContext = Depends(require_evals_run_access),
    defs=Depends(get_studio_definition_store_dep),
    loops=Depends(get_loop_store_dep),
    config=Depends(get_eval_loop_config_store_dep),
    runs=Depends(get_eval_store_dep),
    mecanismo=Depends(get_mecanismo_store_dep),
    svc=Depends(get_loop_service_dep),
) -> LoopOut:
    """Open a loop: G1 target (the config's ``alvo``, frozen on the loop) / floor = the agent's ``publicacao_limiar``; G2 the
    planned rounds (omitted = the config's max, never above it); G7 the budget (omitted = the config's cap, never above it)."""
    agent = resolve_studio_agent(defs, ctx.org_id, key)
    require_user_or_dev_advisor(ctx, agent, evals_token_ok=True)
    guard_um_por_usuario(ctx, agent, suite=payload.suite, loop_id=None, runs=runs, mecanismo=mecanismo, loops=loops, defs=defs,
                         abrindo_loop=True)
    cfg = config.get().config
    rodadas, orcamento = resolver_criacao(cfg, rodadas_planejadas=payload.rodadas_planejadas, orcamento_usd=payload.orcamento_usd)
    try:
        rec = loops.create_loop(
            ctx.org_id, agent.id, agente_chave=agent.key, suite=payload.suite, rodadas_planejadas=rodadas,
            alvo=cfg.alvo, piso=float(agent.publicacao_limiar), orcamento_usd=orcamento, started_by=actor_id(ctx),
            modo=payload.modo)
    except StudioConflict as exc:
        raise http_error(409, exc.code, mensagem_conflito(exc)) from exc
    loops.registrar_evento(ctx.org_id, rec.id, "loop_iniciado", detalhe={
        "suite": rec.suite, "modo": rec.modo, "rodadas_planejadas": rec.rodadas_planejadas, "orcamento_usd": rec.orcamento_usd},
        ator=actor_id(ctx))
    if rec.modo == "automatico":
        from app.studio.eval_loop_driver import get_driver

        driver = get_driver()
        if driver is not None:
            driver.agendar(rec)  # books round 1 in the background; the response does not wait for it
    return LoopOut(**EvalLoopService.montar_estado(rec, []))


@router.get("/{key}/evals/loops", response_model=LoopListOut)
def list_loops(
    key: str,
    suite: str | None = Query(None, pattern="^(comportamento|mecanismo)$"),
    status_: str | None = Query(None, alias="status", pattern="^(ativo|parado|concluido)$"),
    ctx: AuthContext = Depends(require_evals_run_access),
    defs=Depends(get_studio_definition_store_dep),
    loops=Depends(get_loop_store_dep),
) -> LoopListOut:
    agent = resolve_studio_agent(defs, ctx.org_id, key)
    require_user_or_dev_advisor(ctx, agent, evals_token_ok=True)
    return LoopListOut(items=[
        LoopOut(**EvalLoopService.montar_estado(
            r, loops.list_rodadas(ctx.org_id, r.id), loops.listar_eventos(ctx.org_id, r.id, eventos=EVENTOS_REFINO, limite=1000)))
        for r in loops.list_loops(ctx.org_id, agent.id, status=status_, suite=suite)])


@router.get("/{key}/evals/loops/{loop_id}", response_model=LoopOut)
def get_loop(
    key: str,
    loop_id: UUID,
    ctx: AuthContext = Depends(require_evals_run_access),
    defs=Depends(get_studio_definition_store_dep),
    svc=Depends(get_loop_service_dep),
) -> LoopOut:
    """The loop's state: the score series with each round's hash and failing cases, the overcalls with their cost, the
    checkpoints reached, the spend against the budget and (once stopped) the reason."""
    agent = resolve_studio_agent(defs, ctx.org_id, key)
    require_user_or_dev_advisor(ctx, agent, evals_token_ok=True)
    return LoopOut(**svc.estado(ctx.org_id, agent.id, loop_id))


@router.post("/{key}/evals/loops/{loop_id}/stop", response_model=LoopOut)
def stop_loop(
    key: str,
    loop_id: UUID,
    payload: LoopStopRequest,
    ctx: AuthContext = Depends(require_evals_run_cancel),
    defs=Depends(get_studio_definition_store_dep),
    svc=Depends(get_loop_service_dep),
) -> LoopOut:
    """Stop an active loop by hand (``parado_manualmente``). A round in flight finishes on its own and is still recorded."""
    agent = resolve_studio_agent(defs, ctx.org_id, key)
    svc.parar(ctx.org_id, agent.id, loop_id, motivo=payload.motivo)
    return LoopOut(**svc.estado(ctx.org_id, agent.id, loop_id))


@router.put("/{key}/evals/loops/{loop_id}/modo", response_model=LoopOut)
def put_loop_modo(
    key: str,
    loop_id: UUID,
    payload: LoopModoRequest,
    ctx: AuthContext = Depends(require_evals_run_access),
    defs=Depends(get_studio_definition_store_dep),
    svc=Depends(get_loop_service_dep),
) -> LoopOut:
    """``automatico`` resumes the driver (it books the next round now); ``manual`` pauses it: the round in flight finishes and is
    recorded, then the loop waits for the owner's "Rodar próxima rodada". 409 ``loop_ja_encerrado`` on a stopped loop."""
    agent = resolve_studio_agent(defs, ctx.org_id, key)
    require_user_or_dev_advisor(ctx, agent, evals_token_ok=True)
    rec = svc.definir_modo(ctx.org_id, agent.id, loop_id, payload.modo, ator=actor_id(ctx))
    if rec.modo == "automatico":
        from app.studio.eval_loop_driver import get_driver

        driver = get_driver()
        if driver is not None:
            driver.agendar(rec)
    return LoopOut(**svc.estado(ctx.org_id, agent.id, loop_id))


@router.get("/{key}/evals/loops/{loop_id}/eventos", response_model=LoopEventosOut)
def list_loop_eventos(
    key: str,
    loop_id: UUID,
    ctx: AuthContext = Depends(require_evals_run_access),
    defs=Depends(get_studio_definition_store_dep),
    svc=Depends(get_loop_service_dep),
) -> LoopEventosOut:
    """The loop's append-only lifecycle events (opened, round opened / closed / errored, preflight refused, driver idle / resumed,
    mode changed, stopped), oldest first: what the owner queries to see what the driver actually did."""
    agent = resolve_studio_agent(defs, ctx.org_id, key)
    require_user_or_dev_advisor(ctx, agent, evals_token_ok=True)
    return LoopEventosOut(items=[LoopEventoOut(
        evento=e["evento"], rodada_seq=e.get("rodada_seq"), run_id=e.get("run_id"), detalhe=e.get("detalhe") or {},
        created_at=e.get("created_at")) for e in svc.eventos(ctx.org_id, agent.id, loop_id)])


config_router = APIRouter(prefix="/api/studio/plataforma", tags=["studio-eval-loops"], include_in_schema=False)


def _config_out(rec: ConfigRegistrada) -> EvalLoopConfigOut:
    return EvalLoopConfigOut(
        alvo=rec.config.alvo, orcamento_usd=rec.config.orcamento_usd, rodadas_max=rec.config.rodadas_max,
        alterado_por=rec.alterado_por, alterado_em=rec.alterado_em)


@config_router.get("/eval-loop-config", response_model=EvalLoopConfigOut)
def get_eval_loop_config(
    ctx: AuthContext = Depends(require_platform_admin),
    config=Depends(get_eval_loop_config_store_dep),
) -> EvalLoopConfigOut:
    """The platform's loop config: target, per-loop budget cap, max planned rounds (code defaults until first edited)."""
    return _config_out(config.get())


@config_router.put("/eval-loop-config", response_model=EvalLoopConfigOut)
def put_eval_loop_config(
    payload: EvalLoopConfigIn,
    ctx: AuthContext = Depends(require_platform_admin),
    config=Depends(get_eval_loop_config_store_dep),
) -> EvalLoopConfigOut:
    """Replace the config (records a ``loop_config_alterada`` event). Loops already open keep the values they started with."""
    return _config_out(config.set(
        EvalLoopConfig(alvo=payload.alvo, orcamento_usd=payload.orcamento_usd, rodadas_max=payload.rodadas_max),
        actor=actor_id(ctx)))
