"""``/api/studio/agents/{key}/evals`` — cases + runs + results (contract
§D4, slice BE-KE).

Auth: ``require_member`` for reads, ``require_admin`` for writes (contract
§D intro). Every route resolves the agent by ``(ctx.org_id, key)`` — 404
``agent_not_found`` / 409 ``not_studio_agent`` (same as
``studio_knowledge_router``).

Scheduling seam (contract §J2.2): ``POST .../evals/runs`` inserts the run
as `pendente` then calls ``scheduler(run_id)`` via
:func:`get_eval_scheduler_dep`. THIS module's default binding always
raises :class:`EvalSchedulerUnavailable` (fail closed) — BE-RT overrides
the dependency with the production runner once wired. A scheduling
failure flips the just-created run to ``falhou`` (never leaves it
`pendente` forever occupying the one-run-per-version slot) before
returning 503 ``eval_runner_unavailable``.

Not registered on ``app/main.py`` yet — see
``studio_knowledge_router``'s module docstring for the same note.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.dependencies import require_admin, require_member
from app.schemas.studio_ke import (
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
from app.routers.studio_knowledge_router import (
    get_agent_lookup_dep,
    not_found_error,
    resolve_studio_agent,
)
from app.stores.errors import Conflict, NotFound
from app.stores.studio_evals import EvalCaseInput, _UNSET
from noctusai_lib.api.auth.session import AuthContext

router = APIRouter(prefix="/api/studio/agents", tags=["studio-evals"])


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
    dependency (``app.dependency_overrides`` in production wiring / a real
    binding in ``main.py``) with a callable that actually schedules the
    run through the runtime."""

    def _unavailable(run_id: UUID) -> None:
        raise EvalSchedulerUnavailable(f"no eval runner registered for run {run_id}")

    return _unavailable


def _invalid_field(exc: ValueError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={"detail": str(exc), "code": "invalid_field"},
    )


def _case_out(record) -> EvalCaseOut:
    return EvalCaseOut(
        id=record.id, slug=record.slug, titulo=record.titulo, entrada=record.entrada,
        contexto=record.contexto, criterios=record.criterios, rubrica=record.rubrica,
        tags=list(record.tags), ativo=record.ativo,
    )


def _run_out(record) -> EvalRunOut:
    return EvalRunOut(
        id=record.id, version_id=record.version_id, compiled_hash=record.compiled_hash,
        status=record.status, total=record.total, aprovados=record.aprovados, score=record.score,
        limiar=record.limiar, started_at=record.started_at, finished_at=record.finished_at,
        erro=record.erro,
    )


# ── Cases ──────────────────────────────────────────────────────────────


@router.get("/{key}/evals/cases", response_model=EvalCaseListOut)
async def list_cases(
    key: str,
    ctx: AuthContext = Depends(require_member),
    store=Depends(get_eval_store_dep),
    agent_lookup=Depends(get_agent_lookup_dep),
) -> EvalCaseListOut:
    agent = resolve_studio_agent(agent_lookup, ctx.org_id, key)
    records = store.list_cases(ctx.org_id, agent.id)
    return EvalCaseListOut(items=[_case_out(r) for r in records])


@router.post("/{key}/evals/cases", response_model=EvalCaseOut, status_code=status.HTTP_201_CREATED)
async def create_case(
    key: str,
    payload: EvalCaseCreateRequest,
    ctx: AuthContext = Depends(require_admin),
    store=Depends(get_eval_store_dep),
    agent_lookup=Depends(get_agent_lookup_dep),
) -> EvalCaseOut:
    agent = resolve_studio_agent(agent_lookup, ctx.org_id, key)
    try:
        record = store.create_case(
            ctx.org_id, agent.id,
            EvalCaseInput(
                slug=payload.slug, titulo=payload.titulo, entrada=payload.entrada,
                criterios={"deve": payload.criterios.deve, "nao_deve": payload.criterios.nao_deve},
                contexto=payload.contexto, rubrica=payload.rubrica,
                tags=tuple(payload.tags), ativo=payload.ativo,
            ),
        )
    except ValueError as exc:
        raise _invalid_field(exc) from exc
    return _case_out(record)


@router.patch("/{key}/evals/cases/{case_id}", response_model=EvalCaseOut)
async def update_case(
    key: str,
    case_id: UUID,
    payload: EvalCaseUpdateRequest,
    ctx: AuthContext = Depends(require_admin),
    store=Depends(get_eval_store_dep),
    agent_lookup=Depends(get_agent_lookup_dep),
) -> EvalCaseOut:
    agent = resolve_studio_agent(agent_lookup, ctx.org_id, key)
    fields = payload.model_dump(exclude_unset=True)
    try:
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
    except ValueError as exc:
        raise _invalid_field(exc) from exc
    return _case_out(record)


@router.delete("/{key}/evals/cases/{case_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_case(
    key: str,
    case_id: UUID,
    ctx: AuthContext = Depends(require_admin),
    store=Depends(get_eval_store_dep),
    agent_lookup=Depends(get_agent_lookup_dep),
) -> None:
    agent = resolve_studio_agent(agent_lookup, ctx.org_id, key)
    try:
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
    agent_lookup=Depends(get_agent_lookup_dep),
    scheduler=Depends(get_eval_scheduler_dep),
) -> EvalRunOut:
    agent = resolve_studio_agent(agent_lookup, ctx.org_id, key)
    try:
        version = store.get_version_ref(ctx.org_id, agent.id, payload.version_id)
    except NotFound as exc:
        raise not_found_error("Versão não encontrada.", "version_not_found") from exc
    if not version.compiled_hash:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"detail": "A versão precisa ser compilada antes de avaliar.", "code": "compile_required"},
        )
    try:
        run = store.create_run(
            ctx.org_id, agent.id, payload.version_id,
            compiled_hash=version.compiled_hash, limiar=agent.publicacao_limiar,
            case_ids=payload.case_ids, started_by=ctx.user_id,
        )
    except Conflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"detail": str(exc), "code": "run_in_progress"},
        ) from exc
    except NotFound as exc:
        raise not_found_error("Caso de avaliação não encontrado.", "eval_case_not_found") from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"detail": str(exc), "code": "no_eval_cases"},
        ) from exc

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
    agent_lookup=Depends(get_agent_lookup_dep),
) -> EvalRunListOut:
    agent = resolve_studio_agent(agent_lookup, ctx.org_id, key)
    runs = store.list_runs(ctx.org_id, agent.id, version_id)
    return EvalRunListOut(items=[_run_out(r) for r in runs])


@router.get("/{key}/evals/runs/{run_id}", response_model=EvalRunDetailOut)
async def get_run(
    key: str,
    run_id: UUID,
    ctx: AuthContext = Depends(require_member),
    store=Depends(get_eval_store_dep),
    agent_lookup=Depends(get_agent_lookup_dep),
) -> EvalRunDetailOut:
    agent = resolve_studio_agent(agent_lookup, ctx.org_id, key)
    try:
        run = store.get_run(ctx.org_id, agent.id, run_id)
    except NotFound as exc:
        raise not_found_error("Execução não encontrada.", "eval_run_not_found") from exc
    results = store.list_results_with_cases(ctx.org_id, agent.id, run_id)
    return EvalRunDetailOut(
        id=run.id, version_id=run.version_id, compiled_hash=run.compiled_hash, status=run.status,
        total=run.total, aprovados=run.aprovados, score=run.score, limiar=run.limiar,
        started_at=run.started_at, finished_at=run.finished_at, erro=run.erro,
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
    agent_lookup=Depends(get_agent_lookup_dep),
) -> EvalRunOut:
    agent = resolve_studio_agent(agent_lookup, ctx.org_id, key)
    try:
        run = store.cancel_run(ctx.org_id, agent.id, run_id)
    except NotFound as exc:
        raise not_found_error("Execução não encontrada.", "eval_run_not_found") from exc
    except Conflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"detail": str(exc), "code": "run_not_cancellable"},
        ) from exc
    return _run_out(run)


__all__ = ["router", "EvalSchedulerUnavailable", "get_eval_scheduler_dep", "get_eval_store_dep"]
