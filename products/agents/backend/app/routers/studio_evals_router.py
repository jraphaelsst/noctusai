"""``/api/studio/agents/{key}/evals`` — cases + runs + results (contract
§D4, slice BE-KE).

Auth: ``require_platform_admin`` (visibility tier 1 — the definition/knowledge/evals of an agent are the platform's IP, never an org admin's) (contract
§D intro). Listing, creating and editing CASES also accepts the platform-issued ``studio:content-write`` token
(``require_platform_content_admin`` — the ``noctus.agents.content`` MCP path, kind ``evals_mecanismo``); those writes
are audited ``conteudo_editado_mcp``. Deleting a case and every run route stay human platform admin only. The agent (and a run's version) resolve through BE-DEF's
``StudioDefinitionStore`` + ``resolve_agent``/``resolve_version`` — one
resolver for every studio route (404 ``agent_not_found`` / 409
``not_studio_agent`` / 404 ``version_not_found``).

Seams (FastAPI dependencies; production bindings are BE-RT's, the defaults
FAIL CLOSED):

* ``get_eval_scheduler_dep`` (contract §J2.2) — ``POST .../evals/runs``
  inserts the run as ``pendente`` then calls ``scheduler(run_id)``. The
  default raises :class:`EvalSchedulerUnavailable`; the just-created run is
  flipped to ``falhou`` (never left occupying the one-run-per-version slot)
  and the route returns 503 ``eval_runner_unavailable``.
* ``get_current_hash_dep`` — ``(org_id, agent, version) -> str``: the hash
  of the version compiled NOW. A run is stamped with it, never with the
  stored ``agent_versions.compiled_hash`` (the compiled text also carries
  live inputs — e.g. the knowledge collections and their document counts —
  that change without touching the version row, so the stored hash can be
  stale). The default raises 503 ``compile_unavailable``.

Error codes: 409 ``slug_taken`` (duplicate case slug), 409 ``case_in_use``
(deleting a case that has results — deactivate it instead), 409
``run_not_cancellable``, 422 ``no_eval_cases``. Several runs of one version
may execute at once (071).
"""
from __future__ import annotations

from typing import Callable

import anyio.to_thread
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.config import settings
from app.dependencies import (
    require_evals_run_access,
    require_evals_run_cancel,
    require_platform_admin,
    require_platform_content_admin,
)
from app.routers.studio_agents_router import (
    get_consolidacao_store_dep,
    get_loop_service_dep,
    audit_definition_read,
    actor_id,
    get_mecanismo_store_dep,
    guard_um_por_usuario,
    get_eval_store_dep,  # defined in studio_agents_router (publish/readiness read the cases too); re-exported here
    require_user_or_dev_advisor,
    get_studio_definition_store_dep,
    http_error,
    resolve_version,
    store_errors,
)
from app.routers.studio_knowledge_router import not_found_error, resolve_studio_agent
from app.schemas.studio_ke import (
    BackfillConsolidacaoRequest,
    CasoPuladoOut,
    ConsolidacaoCasoOut,
    ConsolidacaoCasoUpdateRequest,
    ConsolidacaoOut,
    CriteriosOut,
    EvalCaseCreateRequest,
    EvalCaseListOut,
    EvalCaseOut,
    EvalCaseUpdateRequest,
    EvalResultOut,
    EvalRunCreateRequest,
    EvalRunDetailOut,
    EvalRunListOut,
    EvalRunOut,
)
from app.stores._db_errors import StudioConflict, mensagem_conflito
from app.studio.consolidacao import resumir_estados
from app.studio.consolidacao_service import Selecao, confirmar_selecao, reconstruir, selecionar
from app.studio.eval_loop_service import resumo_comportamento
from app.studio.spend import KIND_EVAL_RUN, get_spend_ceiling_dep, reserve_run
from app.stores.errors import NotFound
from app.stores.studio_definitions import StudioAgentRecord, VersionRecord
from app.stores.studio_evals import EvalCaseInput, _UNSET
from noctusai_lib.api.auth.session import AuthContext

router = APIRouter(prefix="/api/studio/agents", tags=["studio-evals"], include_in_schema=False)

#: ``(org_id, agent, version) -> compiled hash`` — see module docstring.
CurrentHash = Callable[[UUID, StudioAgentRecord, VersionRecord], str]


class EvalSchedulerUnavailable(RuntimeError):
    """Raised by the default (fail-closed) :func:`get_eval_scheduler_dep`
    binding — no real eval runner is registered yet (contract §J2.2; BE-RT
    binds the production runner)."""


def get_eval_scheduler_dep():
    """Fail-closed default: every call raises. BE-RT overrides this
    dependency with a callable that actually schedules the run."""

    def _unavailable(run_id: UUID) -> None:
        raise EvalSchedulerUnavailable(f"no eval runner registered for run {run_id}")

    return _unavailable


#: ``(org_id, agent, version) -> per-part hashes | None`` -- what a default run compares per case (consolidation).
CurrentPartes = Callable[[UUID, StudioAgentRecord, VersionRecord], "dict[str, str] | None"]


def get_current_partes_dep() -> CurrentPartes:
    """Fail-safe default: no per-part hashes => every case counts as affected (a default run runs everything).
    ``app.studio.wiring`` binds the production compile."""
    return lambda org_id, agent, version: None


def get_current_hash_dep() -> CurrentHash:
    """Fail-closed default (503 ``compile_unavailable``): stamping a run
    with a hash nobody computed would let the gate judge the wrong text.
    BE-RT binds the production compiler."""
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={"detail": "Compilador indisponível.", "code": "compile_unavailable"},
    )


def _case_out(record, meta=None) -> EvalCaseOut:
    return EvalCaseOut(
        **({} if meta is None else {
            "criticidade": meta.criticidade, "criticidade_origem": meta.criticidade_origem,
            "depende_de": None if meta.depende_de is None else list(meta.depende_de),
            "depende_de_origem": meta.depende_de_origem}),
        id=record.id, slug=record.slug, titulo=record.titulo, entrada=record.entrada,
        contexto=record.contexto,
        criterios=CriteriosOut(
            deve=list(record.criterios.get("deve") or []),
            nao_deve=list(record.criterios.get("nao_deve") or []),
        ),
        rubrica=record.rubrica, tags=list(record.tags), ativo=record.ativo,
        suite=record.suite, k=record.k, roteiro=record.roteiro, asserts=record.asserts,
    )


def _run_out(record) -> EvalRunOut:
    return EvalRunOut(
        id=record.id, version_id=record.version_id, compiled_hash=record.compiled_hash,
        status=record.status, total=record.total, aprovados=record.aprovados, score=record.score,
        limiar=record.limiar, started_at=record.started_at, finished_at=record.finished_at,
        erro=record.erro, completa=record.completa,
        modelo_geracao=record.modelo_geracao, limite_usd=record.limite_usd, custo_usd=record.custo_usd,
    )


def _audit_case_mcp(defs, ctx: AuthContext, agent, case_id, record) -> None:
    """A case written with the platform ``studio:content-write`` token (the ``noctus.agents.content`` MCP path) is
    audit-logged like every other MCP content write: who (the token row), what (kind + slug), never the content."""
    if ctx.caller_kind != "product":
        return
    defs.append_audit(
        agent.org_id, agent.id, actor_id(ctx), "conteudo_editado_mcp",
        None if case_id is None else {"kind": "eval_caso", "case_id": str(case_id)},
        {"kind": "eval_caso", "case_id": str(record.id), "slug": record.slug, "suite": record.suite},
    )


# ── Cases ──────────────────────────────────────────────────────────────


@router.get("/{key}/evals/cases", response_model=EvalCaseListOut)
def list_cases(
    key: str,
    ctx: AuthContext = Depends(require_platform_content_admin),
    store=Depends(get_eval_store_dep),
    defs=Depends(get_studio_definition_store_dep),
    consol=Depends(get_consolidacao_store_dep),
) -> EvalCaseListOut:
    agent = resolve_studio_agent(defs, ctx.org_id, key)
    records = store.list_cases(ctx.org_id, agent.id)
    meta = consol.list_meta(ctx.org_id, agent.id)
    return EvalCaseListOut(items=[_case_out(r, meta.get(r.id)) for r in records])


@router.post("/{key}/evals/cases", response_model=EvalCaseOut, status_code=status.HTTP_201_CREATED)
def create_case(
    key: str,
    payload: EvalCaseCreateRequest,
    ctx: AuthContext = Depends(require_platform_content_admin),
    store=Depends(get_eval_store_dep),
    defs=Depends(get_studio_definition_store_dep),
) -> EvalCaseOut:
    agent = resolve_studio_agent(defs, ctx.org_id, key)
    crit = payload.criterios
    with store_errors():
        record = store.create_case(
            ctx.org_id, agent.id,
            EvalCaseInput(
                slug=payload.slug, titulo=payload.titulo, entrada=payload.entrada,
                criterios={"deve": crit.deve if crit else [], "nao_deve": crit.nao_deve if crit else []},
                contexto=payload.contexto, rubrica=payload.rubrica,
                tags=tuple(payload.tags), ativo=payload.ativo,
                suite=payload.suite, k=payload.k, roteiro=payload.roteiro, asserts=payload.asserts,
            ),
        )
    _audit_case_mcp(defs, ctx, agent, None, record)
    return _case_out(record)


@router.patch("/{key}/evals/cases/{case_id}", response_model=EvalCaseOut)
def update_case(
    key: str,
    case_id: UUID,
    payload: EvalCaseUpdateRequest,
    ctx: AuthContext = Depends(require_platform_content_admin),
    store=Depends(get_eval_store_dep),
    defs=Depends(get_studio_definition_store_dep),
) -> EvalCaseOut:
    agent = resolve_studio_agent(defs, ctx.org_id, key)
    fields = payload.model_dump(mode="json", exclude_unset=True)
    try:
        with store_errors():
            record = store.update_case(
                ctx.org_id, agent.id, case_id,
                titulo=fields.get("titulo", _UNSET), entrada=fields.get("entrada", _UNSET),
                contexto=fields.get("contexto", _UNSET), criterios=fields.get("criterios", _UNSET),
                rubrica=fields.get("rubrica", _UNSET),
                tags=tuple(fields["tags"]) if "tags" in fields else _UNSET,
                ativo=fields.get("ativo", _UNSET),
                k=fields.get("k", _UNSET), roteiro=fields.get("roteiro", _UNSET),
                asserts=fields.get("asserts", _UNSET),
            )
    except NotFound as exc:
        raise not_found_error("Caso de avaliação não encontrado.", "eval_case_not_found") from exc
    _audit_case_mcp(defs, ctx, agent, case_id, record)
    return _case_out(record)


@router.delete("/{key}/evals/cases/{case_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_case(
    key: str,
    case_id: UUID,
    ctx: AuthContext = Depends(require_platform_admin),
    store=Depends(get_eval_store_dep),
    defs=Depends(get_studio_definition_store_dep),
) -> None:
    agent = resolve_studio_agent(defs, ctx.org_id, key)
    try:
        with store_errors():
            store.delete_case(ctx.org_id, agent.id, case_id)
    except NotFound as exc:
        raise not_found_error("Caso de avaliação não encontrado.", "eval_case_not_found") from exc


# ── Runs ───────────────────────────────────────────────────────────────


def _guard_token_run(ctx: AuthContext, store, defs, agent, version, payload) -> None:
    """Denial-of-wallet guards for a PRODUCT-token run start (the platform-admin UI keeps its latitude): the run
    stays at the settings default cost cap and model and targets only the agent's current draft. The org's shared
    rolling-24h spend ceiling is reserved right after the run is booked (``reserve_run``, fail-closed)."""
    default_cap = settings.studio_eval_run_budget_usd
    if payload.limite_usd is not None and payload.limite_usd > default_cap:
        raise http_error(422, "limite_usd_above_default", f"limite_usd acima do padrão ({default_cap}).")
    if payload.modelo_geracao is not None:
        raise http_error(422, "modelo_geracao_not_allowed", "Este token não pode escolher o modelo de geração.")
    draft = defs.get_draft(ctx.org_id, agent.id)
    if draft is None or draft.id != version.id:
        raise http_error(422, "version_not_draft", "Este token só executa avaliações sobre o rascunho atual.")


@router.post("/{key}/evals/runs", response_model=EvalRunOut, status_code=status.HTTP_202_ACCEPTED)
# Stays `async def`: scheduler(run.id) -> asyncio.create_task needs the running loop,
# which a threadpool worker does not have.
async def create_run(
    key: str,
    payload: EvalRunCreateRequest,
    ctx: AuthContext = Depends(require_evals_run_access),
    store=Depends(get_eval_store_dep),
    defs=Depends(get_studio_definition_store_dep),
    scheduler=Depends(get_eval_scheduler_dep),
    current_hash: CurrentHash = Depends(get_current_hash_dep),
    current_partes: CurrentPartes = Depends(get_current_partes_dep),
    consol=Depends(get_consolidacao_store_dep),
    ceiling=Depends(get_spend_ceiling_dep),
    loops=Depends(get_loop_service_dep),
    mecanismo=Depends(get_mecanismo_store_dep),
) -> EvalRunOut:
    # The store/definition calls are sync PostgREST: run them in a worker thread so the loop keeps
    # serving. Only the scheduler (asyncio.create_task) stays on the loop. Exceptions (NotFound ->
    # 404, StudioConflict -> 409, ...) propagate through the thread unchanged.
    def _prepare():
        agent = resolve_studio_agent(defs, ctx.org_id, key)
        require_user_or_dev_advisor(ctx, agent, evals_token_ok=True)
        version = resolve_version(defs, ctx.org_id, agent, payload.version_id)

        def _fechar_loop(run_id: UUID) -> None:
            """A run booked into a loop that never gets executed closes its round now (neutral: no score)."""
            if payload.loop_id is not None:
                loops.fechar_sem_falhar(
                    ctx.org_id, lambda: resumo_comportamento(store, ctx.org_id, agent.id, run_id), run_id=run_id,
                    run_tipo="comportamento")

        if ctx.caller_kind == "product":
            _guard_token_run(ctx, store, defs, agent, version, payload)
        compiled_hash = current_hash(ctx.org_id, agent, version)

        limite_usd = payload.limite_usd if payload.limite_usd is not None else settings.studio_eval_run_budget_usd
        # one run / loop per user at a time (names what is running; migration 087's trigger is the race backstop)
        guard_um_por_usuario(ctx, agent, suite="comportamento", loop_id=payload.loop_id, runs=store, mecanismo=mecanismo,
                             loops=loops.store, defs=defs, fase="tudo" if payload.loop_id is None else "em_andamento")
        if payload.loop_id is not None:
            if payload.case_ids is not None or payload.repetir_falhas_de is not None:
                raise http_error(422, "loop_run_parcial", "Uma run de loop cobre a suíte inteira: não aceita case_ids nem repetir_falhas_de.")
            if payload.modelo_geracao is not None:
                raise http_error(422, "loop_modelo_geracao_nao_permitido", "Uma run de loop usa o modelo da própria versão.")
            # G6/G7: refuses a closed loop, an open round, a spent budget, an unchanged hash with nothing to consolidate;
            # the cost cap is clamped to what the loop budget has left.
            limite_usd = loops.admitir(
                ctx.org_id, agent.id, payload.loop_id, suite="comportamento", compiled_hash=compiled_hash, limite_usd=limite_usd,
                ler_resumo=lambda rid: resumo_comportamento(store, ctx.org_id, agent.id, rid)).limite_usd
            guard_um_por_usuario(ctx, agent, suite="comportamento", loop_id=payload.loop_id, runs=store, mecanismo=mecanismo,
                                 loops=loops.store, defs=defs, fase="loop")

        case_ids = payload.case_ids
        if payload.repetir_falhas_de is not None:
            # Contract §L: rerun only the failures of a prior run of THIS agent
            # (org-scoped by `get_run`, which 404s a foreign/unknown run id —
            # same resolver every studio route uses).
            try:
                prior = store.get_run(ctx.org_id, agent.id, payload.repetir_falhas_de)
            except NotFound as exc:
                raise not_found_error("Execução não encontrada.", "eval_run_not_found") from exc
            case_ids = [
                r.result.case_id for r in store.list_results_with_cases(ctx.org_id, agent.id, prior.id)
                if r.result.status != "aprovado"
            ]

        # Consolidation: a DEFAULT run (no explicit ids, no repeat-failures, no rodar_tudo) executes only the cases that are
        # not consolidated-and-unaffected. Explicit selections are never filtered.
        partes = current_partes(ctx.org_id, agent, version)
        filtrada = case_ids is None and not payload.rodar_tudo
        if filtrada:
            ativos = [c.id for c in store.list_cases(ctx.org_id, agent.id) if c.ativo and c.suite == "comportamento"]
            selecao = selecionar(
                consol, org_id=ctx.org_id, agent_id=agent.id, suite="comportamento", ativos=ativos, partes=partes,
                hash_atual=compiled_hash, rodar_tudo=False)
            if ativos and not selecao.rodar:
                raise http_error(
                    409, "todos_consolidados",
                    "Todos os casos estão consolidados e não foram afetados por mudanças. Use rodar_tudo para rodar mesmo assim.")
            if selecao.pulados:
                case_ids = list(selecao.rodar)  # a subset run: never `completa` (the publish gate still needs rodar_tudo)
        else:
            selecao = Selecao(rodar=list(case_ids or []), rodar_tudo=True)

        try:
            run = store.create_run(
                ctx.org_id, agent.id, version.id,
                compiled_hash=compiled_hash, limiar=agent.publicacao_limiar,
                case_ids=case_ids, started_by=actor_id(ctx),
                modelo_geracao=payload.modelo_geracao, limite_usd=limite_usd,
            )
        except NotFound as exc:
            raise not_found_error("Caso de avaliação não encontrado.", "eval_case_not_found") from exc
        except StudioConflict as exc:  # a DB conflict mapped by the store; parallel runs of a version are allowed (071)
            raise http_error(409, exc.code, mensagem_conflito(exc)) from exc
        except ValueError as exc:
            raise http_error(422, "no_eval_cases", str(exc)) from exc

        if payload.loop_id is not None:
            try:
                loops.abrir(ctx.org_id, payload.loop_id, run_id=run.id, run_tipo="comportamento", compiled_hash=compiled_hash,
                            partes=dict(partes) if partes is not None else None)
            except Exception:
                store.mark_run_failed(ctx.org_id, run.id, erro="loop_indisponivel")
                raise

        try:
            confirmar_selecao(
                consol, selecao, org_id=ctx.org_id, agent_id=agent.id, suite="comportamento", run_id=run.id,
                run_tipo="comportamento", partes=partes, hash_atual=compiled_hash)
        except Exception:
            store.mark_run_failed(ctx.org_id, run.id, erro="consolidacao_indisponivel")
            _fechar_loop(run.id)
            raise
        if selecao.pulados:
            run = store.get_run(ctx.org_id, agent.id, run.id)  # `completa` was stamped by the covered selection

        if ctx.caller_kind == "product":
            # The shared daily ceiling (seed): over it / unverifiable -> the booked run is failed, never scheduled.
            try:
                reserve_run(ceiling, org_id=ctx.org_id, kind=KIND_EVAL_RUN, run_id=run.id, amount_usd=limite_usd)
            except Exception:
                store.mark_run_failed(ctx.org_id, run.id, erro="daily_spend_ceiling")
                _fechar_loop(run.id)
                raise

        return run

    run = await anyio.to_thread.run_sync(_prepare)

    try:
        scheduler(run.id)
    except EvalSchedulerUnavailable as exc:
        await anyio.to_thread.run_sync(
            lambda: store.mark_run_failed(ctx.org_id, run.id, erro="eval_runner_unavailable")
        )
        if payload.loop_id is not None:
            await anyio.to_thread.run_sync(lambda: loops.fechar_sem_falhar(
                ctx.org_id, lambda: resumo_comportamento(store, ctx.org_id, run.agent_id, run.id), run_id=run.id,
                run_tipo="comportamento"))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"detail": "O executor de avaliações não está disponível.", "code": "eval_runner_unavailable"},
        ) from exc

    return _run_out(run)


@router.get("/{key}/evals/runs", response_model=EvalRunListOut)
def list_runs(
    key: str,
    version_id: UUID | None = Query(None),
    ctx: AuthContext = Depends(require_evals_run_access),
    store=Depends(get_eval_store_dep),
    defs=Depends(get_studio_definition_store_dep),
) -> EvalRunListOut:
    agent = resolve_studio_agent(defs, ctx.org_id, key)
    require_user_or_dev_advisor(ctx, agent, evals_token_ok=True)
    runs = store.list_runs(ctx.org_id, agent.id, version_id)
    return EvalRunListOut(items=[_run_out(r) for r in runs])


@router.get("/{key}/evals/runs/{run_id}", response_model=EvalRunDetailOut)
def get_run(
    key: str,
    run_id: UUID,
    ctx: AuthContext = Depends(require_evals_run_access),
    store=Depends(get_eval_store_dep),
    defs=Depends(get_studio_definition_store_dep),
    consol=Depends(get_consolidacao_store_dep),
) -> EvalRunDetailOut:
    agent = resolve_studio_agent(defs, ctx.org_id, key)
    require_user_or_dev_advisor(ctx, agent, evals_token_ok=True)
    try:
        run = store.get_run(ctx.org_id, agent.id, run_id)
    except NotFound as exc:
        raise not_found_error("Execução não encontrada.", "eval_run_not_found") from exc
    if ctx.caller_kind == "product":
        audit_definition_read(defs, ctx, agent, "eval_run", run.version_id)  # a failed audit write fails the read
    results = store.list_results_with_cases(ctx.org_id, agent.id, run_id)
    slugs = {str(c.id): c.slug for c in store.list_cases(ctx.org_id, agent.id)}
    pulados = [
        CasoPuladoOut(case_id=UUID(str(p["case_id"])), case_slug=slugs.get(str(p["case_id"])), estado=p["estado"],
                      motivo=p["motivo"], sequencia=int(p.get("sequencia") or 0), limite=int(p.get("limite") or 1))
        for p in consol.list_pulados(ctx.org_id, run_id, "comportamento")
    ]
    return EvalRunDetailOut(
        casos_pulados=pulados,
        **_run_out(run).model_dump(),
        resultados=[
            EvalResultOut(
                case_id=r.result.case_id, case_slug=r.case_slug, case_titulo=r.case_titulo,
                status=r.result.status, score=r.result.score, saida=r.result.saida,
                veredito=r.result.veredito, notas_juiz=r.result.notas_juiz,
                duracao_ms=r.result.duracao_ms,
                custo_usd=r.result.custo_usd, tokens_entrada=r.result.tokens_entrada,
                tokens_saida=r.result.tokens_saida, tokens_cache_leitura=r.result.tokens_cache_leitura,
            )
            for r in results
        ],
    )


@router.post("/{key}/evals/runs/{run_id}/cancel", response_model=EvalRunOut)
def cancel_run(
    key: str,
    run_id: UUID,
    ctx: AuthContext = Depends(require_evals_run_cancel),
    store=Depends(get_eval_store_dep),
    defs=Depends(get_studio_definition_store_dep),
    loops=Depends(get_loop_service_dep),
) -> EvalRunOut:
    agent = resolve_studio_agent(defs, ctx.org_id, key)
    try:
        with store_errors():
            run = store.cancel_run(ctx.org_id, agent.id, run_id)
    except NotFound as exc:
        raise not_found_error("Execução não encontrada.", "eval_run_not_found") from exc
    # a cancelled run of a loop closes its round (neutral); a no-op for a run that belongs to no loop
    loops.fechar_sem_falhar(ctx.org_id, lambda: resumo_comportamento(store, ctx.org_id, agent.id, run.id), run_id=run.id,
                            run_tipo="comportamento")
    return _run_out(run)


# ── Consolidation (owner rule 2026-11-09) ───────────────────────────────


@router.get("/{key}/evals/consolidacao", response_model=ConsolidacaoOut)
def get_consolidacao(
    key: str,
    suite: str | None = Query(None, pattern="^(mecanismo|comportamento)$"),
    ctx: AuthContext = Depends(require_platform_content_admin),
    store=Depends(get_eval_store_dep),
    defs=Depends(get_studio_definition_store_dep),
    consol=Depends(get_consolidacao_store_dep),
) -> ConsolidacaoOut:
    """The state of every case of the agent: ``em_validacao`` | ``consolidado`` | ``revalidar``, the streak ``sequencia``/``limite``,
    criticality and declared dependencies. Platform admin only (Platform IP)."""
    agent = resolve_studio_agent(defs, ctx.org_id, key)
    cfg = consol.config()
    meta = consol.list_meta(ctx.org_id, agent.id, suite)
    estados = consol.get_estados(ctx.org_id, agent.id)
    titulos = {c.id: c.titulo for c in store.list_cases(ctx.org_id, agent.id)}
    from app.studio.consolidacao import estado_inicial

    items = []
    for cid, m in meta.items():
        e = estados.get(cid) or estado_inicial(cid, m.criticidade, cfg)
        items.append(ConsolidacaoCasoOut(
            case_id=cid, slug=m.slug, titulo=titulos.get(cid), suite=m.suite, ativo=m.ativo, criticidade=m.criticidade,
            criticidade_origem=m.criticidade_origem, depende_de=None if m.depende_de is None else list(m.depende_de),
            depende_de_origem=m.depende_de_origem, estado=e.estado, sequencia=e.sequencia,
            limite=cfg.limite(e.estado, m.criticidade)))
    items.sort(key=lambda i: (i.suite, i.slug))
    return ConsolidacaoOut(
        config=dict(cfg.valores), contagem=resumir_estados(i.estado for i in items if i.ativo), items=items)


@router.get("/{key}/evals/consolidacao/transicoes")
def list_transicoes(
    key: str,
    case_id: UUID | None = Query(None),
    limit: int = Query(200, ge=1, le=1000),
    ctx: AuthContext = Depends(require_platform_admin),
    defs=Depends(get_studio_definition_store_dep),
    consol=Depends(get_consolidacao_store_dep),
) -> dict:
    """The append-only transition history (newest first): run id, part hashes, reason -- what the owner queries to refine the rule."""
    agent = resolve_studio_agent(defs, ctx.org_id, key)
    rows = consol.list_transicoes(ctx.org_id, agent.id, case_id, limit)
    return {"items": [{k: (str(v) if isinstance(v, UUID) else v) for k, v in r.items() if k != "org_id"} for r in rows]}


@router.put("/{key}/evals/cases/{case_id}/consolidacao", response_model=ConsolidacaoCasoOut)
def put_caso_consolidacao(
    key: str,
    case_id: UUID,
    payload: ConsolidacaoCasoUpdateRequest,
    ctx: AuthContext = Depends(require_platform_content_admin),
    store=Depends(get_eval_store_dep),
    defs=Depends(get_studio_definition_store_dep),
    consol=Depends(get_consolidacao_store_dep),
) -> ConsolidacaoCasoOut:
    """Set a case's criticality and/or declared dependencies (a human decision: origins become ``definida`` / ``declarada``).
    Also the ``noctus.agents.content`` kind ``evals_consolidacao`` (platform ``studio:content-write`` token, audited)."""
    agent = resolve_studio_agent(defs, ctx.org_id, key)
    fields = payload.model_fields_set
    try:
        store.get_case(ctx.org_id, agent.id, case_id)
        consol.set_caso(
            ctx.org_id, agent.id, case_id,
            criticidade=payload.criticidade if "criticidade" in fields else None,
            depende_de=payload.depende_de if "depende_de" in fields else _UNSET,
            depende_de_origem="declarada" if payload.depende_de is not None else None)
    except NotFound as exc:
        raise not_found_error("Caso de avaliação não encontrado.", "eval_case_not_found") from exc
    cfg = consol.config()
    m = consol.list_meta(ctx.org_id, agent.id)[case_id]
    from types import SimpleNamespace

    _audit_case_mcp(defs, ctx, agent, case_id, SimpleNamespace(id=case_id, slug=m.slug, suite=m.suite))  # token writes are audited
    from app.studio.consolidacao import estado_inicial

    e = consol.get_estados(ctx.org_id, agent.id).get(case_id) or estado_inicial(case_id, m.criticidade, cfg)
    return ConsolidacaoCasoOut(
        case_id=case_id, slug=m.slug, suite=m.suite, ativo=m.ativo, criticidade=m.criticidade,
        criticidade_origem=m.criticidade_origem, depende_de=None if m.depende_de is None else list(m.depende_de),
        depende_de_origem=m.depende_de_origem, estado=e.estado, sequencia=e.sequencia,
        limite=cfg.limite(e.estado, m.criticidade))


@router.post("/{key}/evals/consolidacao/backfill")
def backfill_consolidacao(
    key: str,
    payload: BackfillConsolidacaoRequest,
    ctx: AuthContext = Depends(require_platform_admin),
    defs=Depends(get_studio_definition_store_dep),
    consol=Depends(get_consolidacao_store_dep),
    current_hash: CurrentHash = Depends(get_current_hash_dep),
    current_partes: CurrentPartes = Depends(get_current_partes_dep),
) -> dict:
    """Replay the finished runs of BOTH suites oldest-first per case into current states. DRY-RUN unless ``confirmar``.
    Old runs have no per-part hashes: each version is recompiled and accepted only when its hash equals the run's stamped one."""
    agent = resolve_studio_agent(defs, ctx.org_id, key)

    def _recomputar(version_id: UUID, compiled_hash: str):
        try:
            v = defs.get_version(ctx.org_id, version_id)
        except NotFound:
            return None
        partes = current_partes(ctx.org_id, agent, v)
        return partes if partes is not None and current_hash(ctx.org_id, agent, v) == compiled_hash else None

    ref = defs.get_draft(ctx.org_id, agent.id)
    conhecidas = (current_partes(ctx.org_id, agent, ref) or {}).keys() if ref is not None else ()
    with store_errors():
        rel = reconstruir(
            consol, org_id=ctx.org_id, agent_id=agent.id, partes_conhecidas=list(conhecidas), recomputar_partes=_recomputar,
            politica_sem_partes=payload.politica_sem_partes, usar_deps_propostas=payload.usar_deps_propostas,
            aplicar=payload.confirmar, propor_criticidade=payload.propor_criticidade)
    return rel.to_dict()


__all__ = [
    "router",
    "CurrentPartes",
    "get_current_partes_dep",
    "CurrentHash",
    "EvalSchedulerUnavailable",
    "get_current_hash_dep",
    "get_eval_scheduler_dep",
    "get_eval_store_dep",
]
