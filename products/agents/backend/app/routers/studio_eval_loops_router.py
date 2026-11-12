"""``/api/studio/agents/{key}/evals/loops`` -- the eval-loop gate (owner spec 2026-11-09, G1-G7; migration 076).

A loop is a refinement session of one suite of one agent: it declares its planned rounds, a target, a floor (the
agent's ``publicacao_limiar``) and a budget; target / budget cap / max rounds are the platform config (migration 086). Runs started with ``loop_id`` are its rounds
(``POST .../evals/runs`` body ``loop_id``; ``POST .../draft/mecanismo-runs?loop_id=``); when one ends the gate stops the
loop at the target / after 2 rounds without improvement / at the budget and notifies the platform admins in-app mid-flight.

Auth mirrors the run routes: start / read = ``require_evals_run_access`` (a platform admin, a ``studio:publish`` token on a
dev agent, or the platform-issued ``studio:evals-run`` token); stop = ``require_evals_run_cancel``. No caller may exceed the configured budget cap or max rounds. Error codes (409): ``loop_ativo_existente``, ``loop_ja_encerrado``; (404)
``loop_not_found``; (422) ``orcamento_acima_do_teto``, ``rodadas_acima_do_maximo``. The run-start codes live on the run routes (see the contract).
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.dependencies import require_evals_run_access, require_evals_run_cancel, require_platform_admin
from app.routers.studio_agents_router import (
    get_eval_loop_config_store_dep,
    get_loop_service_dep,
    get_loop_store_dep,
    get_studio_definition_store_dep,
    actor_id,
    http_error,
    require_user_or_dev_advisor,
)
from app.routers.studio_knowledge_router import resolve_studio_agent
from app.schemas.studio_eval_loops import (
    EvalLoopConfigIn,
    EvalLoopConfigOut,
    LoopCreateRequest,
    LoopListOut,
    LoopOut,
    LoopStopRequest,
)
from app.stores._db_errors import StudioConflict, mensagem_conflito
from app.stores.eval_loop_config import ConfigRegistrada
from app.studio.eval_loop_config import EvalLoopConfig, resolver_criacao
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
) -> LoopOut:
    """Open a loop: G1 target (the config's ``alvo``, frozen on the loop) / floor = the agent's ``publicacao_limiar``; G2 the
    planned rounds (omitted = the config's max, never above it); G7 the budget (omitted = the config's cap, never above it)."""
    agent = resolve_studio_agent(defs, ctx.org_id, key)
    require_user_or_dev_advisor(ctx, agent, evals_token_ok=True)
    cfg = config.get().config
    rodadas, orcamento = resolver_criacao(cfg, rodadas_planejadas=payload.rodadas_planejadas, orcamento_usd=payload.orcamento_usd)
    try:
        rec = loops.create_loop(
            ctx.org_id, agent.id, agente_chave=agent.key, suite=payload.suite, rodadas_planejadas=rodadas,
            alvo=cfg.alvo, piso=float(agent.publicacao_limiar), orcamento_usd=orcamento, started_by=actor_id(ctx))
    except StudioConflict as exc:
        raise http_error(409, exc.code, mensagem_conflito(exc)) from exc
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
        LoopOut(**EvalLoopService.montar_estado(r, loops.list_rodadas(ctx.org_id, r.id)))
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
