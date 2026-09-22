"""``/api/studio/agents/{key}/evals`` — cases + runs + results (contract
§D4, slice BE-KE).

Auth: ``require_member`` for reads, ``require_admin`` for writes (contract
§D intro). The agent (and a run's version) resolve through BE-DEF's
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
``run_in_progress``, 409 ``run_not_cancellable``, 422 ``no_eval_cases``.
"""
from __future__ import annotations

from typing import Callable
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.dependencies import require_admin, require_member
from app.routers.studio_agents_router import (
    get_studio_definition_store_dep,
    http_error,
    resolve_version,
    store_errors,
)
from app.routers.studio_knowledge_router import not_found_error, resolve_studio_agent
from app.schemas.studio_ke import (
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
from app.stores._db_errors import StudioConflict
from app.stores.errors import NotFound
from app.stores.studio_definitions import StudioAgentRecord, VersionRecord
from app.stores.studio_evals import EvalCaseInput, _UNSET
from noctusai_lib.api.auth.session import AuthContext

router = APIRouter(prefix="/api/studio/agents", tags=["studio-evals"])

#: ``(org_id, agent, version) -> compiled hash`` — see module docstring.
CurrentHash = Callable[[UUID, StudioAgentRecord, VersionRecord], str]


class EvalSchedulerUnavailable(RuntimeError):
    """Raised by the default (fail-closed) :func:`get_eval_scheduler_dep`
    binding — no real eval runner is registered yet (contract §J2.2; BE-RT
    binds the production runner)."""


def get_eval_store_dep():
    from app.config import settings
    from app.stores.studio_evals import get_eval_store

    return get_eval_store(settings)


def get_eval_scheduler_dep():
    """Fail-closed default: every call raises. BE-RT overrides this
    dependency with a callable that actually schedules the run."""

    def _unavailable(run_id: UUID) -> None:
        raise EvalSchedulerUnavailable(f"no eval runner registered for run {run_id}")

    return _unavailable


def get_current_hash_dep() -> CurrentHash:
    """Fail-closed default (503 ``compile_unavailable``): stamping a run
    with a hash nobody computed would let the gate judge the wrong text.
    BE-RT binds the production compiler."""
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={"detail": "Compilador indisponível.", "code": "compile_unavailable"},
    )


def _case_out(record) -> EvalCaseOut:
    return EvalCaseOut(
        id=record.id, slug=record.slug, titulo=record.titulo, entrada=record.entrada,
        contexto=record.contexto,
        criterios=CriteriosOut(
            deve=list(record.criterios.get("deve") or []),
            nao_deve=list(record.criterios.get("nao_deve") or []),
        ),
        rubrica=record.rubrica, tags=list(record.tags), ativo=record.ativo,
    )


def _run_out(record) -> EvalRunOut:
    return EvalRunOut(
        id=record.id, version_id=record.version_id, compiled_hash=record.compiled_hash,
        status=record.status, total=record.total, aprovados=record.aprovados, score=record.score,
        limiar=record.limiar, started_at=record.started_at, finished_at=record.finished_at,
        erro=record.erro, completa=record.completa,
    )


# ── Cases ──────────────────────────────────────────────────────────────


@router.get("/{key}/evals/cases", response_model=EvalCaseListOut)
async def list_cases(
    key: str,
    ctx: AuthContext = Depends(require_member),
    store=Depends(get_eval_store_dep),
    defs=Depends(get_studio_definition_store_dep),
) -> EvalCaseListOut:
    agent = resolve_studio_agent(defs, ctx.org_id, key)
    records = store.list_cases(ctx.org_id, agent.id)
    return EvalCaseListOut(items=[_case_out(r) for r in records])


@router.post("/{key}/evals/cases", response_model=EvalCaseOut, status_code=status.HTTP_201_CREATED)
async def create_case(
    key: str,
    payload: EvalCaseCreateRequest,
    ctx: AuthContext = Depends(require_admin),
    store=Depends(get_eval_store_dep),
    defs=Depends(get_studio_definition_store_dep),
) -> EvalCaseOut:
    agent = resolve_studio_agent(defs, ctx.org_id, key)
    with store_errors():
        record = store.create_case(
            ctx.org_id, agent.id,
            EvalCaseInput(
                slug=payload.slug, titulo=payload.titulo, entrada=payload.entrada,
                criterios={"deve": payload.criterios.deve, "nao_deve": payload.criterios.nao_deve},
                contexto=payload.contexto, rubrica=payload.rubrica,
                tags=tuple(payload.tags), ativo=payload.ativo,
            ),
        )
    return _case_out(record)


@router.patch("/{key}/evals/cases/{case_id}", response_model=EvalCaseOut)
async def update_case(
    key: str,
    case_id: UUID,
    payload: EvalCaseUpdateRequest,
    ctx: AuthContext = Depends(require_admin),
    store=Depends(get_eval_store_dep),
    defs=Depends(get_studio_definition_store_dep),
) -> EvalCaseOut:
    agent = resolve_studio_agent(defs, ctx.org_id, key)
    fields = payload.model_dump(exclude_unset=True)
    try:
        with store_errors():
            record = store.update_case(
                ctx.org_id, agent.id, case_id,
                titulo=fields.get("titulo", _UNSET), entrada=fields.get("entrada", _UNSET),
                contexto=fields.get("contexto", _UNSET), criterios=fields.get("criterios", _UNSET),
                rubrica=fields.get("rubrica", _UNSET),
                tags=tuple(fields["tags"]) if "tags" in fields else _UNSET,
                ativo=fields.get("ativo", _UNSET),
            )
    except NotFound as exc:
        raise not_found_error("Caso de avaliação não encontrado.", "eval_case_not_found") from exc
    return _case_out(record)


@router.delete("/{key}/evals/cases/{case_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_case(
    key: str,
    case_id: UUID,
    ctx: AuthContext = Depends(require_admin),
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


@router.post("/{key}/evals/runs", response_model=EvalRunOut, status_code=status.HTTP_202_ACCEPTED)
async def create_run(
    key: str,
    payload: EvalRunCreateRequest,
    ctx: AuthContext = Depends(require_admin),
    store=Depends(get_eval_store_dep),
    defs=Depends(get_studio_definition_store_dep),
    scheduler=Depends(get_eval_scheduler_dep),
    current_hash: CurrentHash = Depends(get_current_hash_dep),
) -> EvalRunOut:
    agent = resolve_studio_agent(defs, ctx.org_id, key)
    version = resolve_version(defs, ctx.org_id, agent, payload.version_id)
    compiled_hash = current_hash(ctx.org_id, agent, version)
    try:
        run = store.create_run(
            ctx.org_id, agent.id, version.id,
            compiled_hash=compiled_hash, limiar=agent.publicacao_limiar,
            case_ids=payload.case_ids, started_by=ctx.user_id,
        )
    except NotFound as exc:
        raise not_found_error("Caso de avaliação não encontrado.", "eval_case_not_found") from exc
    except StudioConflict as exc:  # run_in_progress
        raise http_error(409, exc.code, str(exc)) from exc
    except ValueError as exc:
        raise http_error(422, "no_eval_cases", str(exc)) from exc

    try:
        scheduler(run.id)
    except EvalSchedulerUnavailable as exc:
        store.mark_run_failed(ctx.org_id, run.id, erro="eval_runner_unavailable")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"detail": "O executor de avaliações não está disponível.", "code": "eval_runner_unavailable"},
        ) from exc

    return _run_out(run)


@router.get("/{key}/evals/runs", response_model=EvalRunListOut)
async def list_runs(
    key: str,
    version_id: UUID | None = Query(None),
    ctx: AuthContext = Depends(require_member),
    store=Depends(get_eval_store_dep),
    defs=Depends(get_studio_definition_store_dep),
) -> EvalRunListOut:
    agent = resolve_studio_agent(defs, ctx.org_id, key)
    runs = store.list_runs(ctx.org_id, agent.id, version_id)
    return EvalRunListOut(items=[_run_out(r) for r in runs])


@router.get("/{key}/evals/runs/{run_id}", response_model=EvalRunDetailOut)
async def get_run(
    key: str,
    run_id: UUID,
    ctx: AuthContext = Depends(require_member),
    store=Depends(get_eval_store_dep),
    defs=Depends(get_studio_definition_store_dep),
) -> EvalRunDetailOut:
    agent = resolve_studio_agent(defs, ctx.org_id, key)
    try:
        run = store.get_run(ctx.org_id, agent.id, run_id)
    except NotFound as exc:
        raise not_found_error("Execução não encontrada.", "eval_run_not_found") from exc
    results = store.list_results_with_cases(ctx.org_id, agent.id, run_id)
    return EvalRunDetailOut(
        **_run_out(run).model_dump(),
        resultados=[
            EvalResultOut(
                case_id=r.result.case_id, case_slug=r.case_slug, case_titulo=r.case_titulo,
                status=r.result.status, score=r.result.score, saida=r.result.saida,
                veredito=r.result.veredito, notas_juiz=r.result.notas_juiz,
                duracao_ms=r.result.duracao_ms,
            )
            for r in results
        ],
    )


@router.post("/{key}/evals/runs/{run_id}/cancel", response_model=EvalRunOut)
async def cancel_run(
    key: str,
    run_id: UUID,
    ctx: AuthContext = Depends(require_admin),
    store=Depends(get_eval_store_dep),
    defs=Depends(get_studio_definition_store_dep),
) -> EvalRunOut:
    agent = resolve_studio_agent(defs, ctx.org_id, key)
    try:
        with store_errors():
            run = store.cancel_run(ctx.org_id, agent.id, run_id)
    except NotFound as exc:
        raise not_found_error("Execução não encontrada.", "eval_run_not_found") from exc
    return _run_out(run)


__all__ = [
    "router",
    "CurrentHash",
    "EvalSchedulerUnavailable",
    "get_current_hash_dep",
    "get_eval_scheduler_dep",
    "get_eval_store_dep",
]
