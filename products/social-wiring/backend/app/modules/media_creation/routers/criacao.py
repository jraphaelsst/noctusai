"""Criação (media production) endpoints (criacao-pipeline-contract.md sections 1, 3, 5).

All under ``/api/media-creation``:

* ``POST /esteira/posts/{post_id}/criacao`` -- manual start of a post's media job graph, or (body ``{"passo": ...}``) the
  re-run of a failed / rejected step + everything downstream as a new rodada. 202; nothing is produced in the request: the
  separate ``worker criacao`` process does the work. Idempotent while a graph is running.
* ``GET /esteira/criacao/{post_id}:{rodada}/progress`` -- SSE of one rodada's live progress.
* ``GET /posts/{post_id}/criacao/progress`` -- SSE of the post's LATEST rodada (the card's status line).
  Both are the seed ``create_job_progress_router``; the first frame is read from the ledger, so a client that connects late
  or after the end still sees the truth.
* ``GET /criacao/cota`` -- the org's monthly vendor quota (limit, spend, remaining). ``PUT`` -- set the limit (org admin
  only); the first set creates the quota, every edit is an event of the seed transition log (``cs_criacao_cota_events``:
  who, from, to). Default US$15.

Auth ``get_current_user_org`` (tier ``org``); a foreign / unknown post is a 404; refusals are coded ``{"code", "detail"}``.
"""
from __future__ import annotations

import asyncio
import uuid
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Optional

from fastapi import Depends, HTTPException, Request
from pydantic import Field

from noctusai_lib.api import StrictHttpModel
from noctusai_lib.api.access_tiers import make_router
from noctusai_lib.api.auth.session import require_org_admin_for
from noctusai_lib.primitives.responses import success_response
from noctusai_lib.realtime import create_job_progress_router

from app.dependencies import coerce_org_uuid, get_admin_client, get_core_client, get_current_user_org
from app.modules.media_creation.services import criacao_service
from app.modules.media_creation.services.criacao_service import CriacaoError, CriacaoService
from app.modules.media_creation.services.esteira_service import EsteiraError

PREFIX = "/api/media-creation"
router = make_router(tier="org", guard=get_current_user_org, prefix=PREFIX, tags=["Media Creation — Criação"])

LIMITE_MAX_USD = Decimal("100000")


class CriacaoIniciar(StrictHttpModel):
    #: omitted = produce the whole route; given = re-run that step (and its downstream) of a failed / rejected post.
    passo: Optional[str] = Field(default=None, min_length=1, max_length=40)


class CotaIn(StrictHttpModel):
    limite_usd_mes: Decimal = Field(ge=0, le=LIMITE_MAX_USD, decimal_places=2)


def get_criacao_service() -> CriacaoService:
    """DI seam: the service over the admin client (it only ENQUEUES here). Tests override with a Fake-backed one."""
    return criacao_service.build_service(get_admin_client())


def get_cota_db() -> Any:
    """DI seam: the schema-pinned admin client for the quota reads / writes."""
    return get_admin_client()


def get_cota_admin():
    """DI seam: the org-admin predicate ``(auth, request) -> None`` (raises 403). Default = the seed's own, over the core
    client's trusted ``noctus_users`` row."""

    def check(auth, request):
        require_org_admin_for(get_core_client(), auth, request, "A cota de criação")

    return check


def _org(auth) -> str:
    return str(coerce_org_uuid(auth[2]))


def _raise(exc: Exception):
    if isinstance(exc, CriacaoError):
        raise HTTPException(status_code=exc.status, detail={"code": exc.code, "detail": exc.detail}) from exc
    raise HTTPException(status_code=exc.status, detail=exc.detail) from exc  # EsteiraError: already {code, detail, ...}


def _uuid_ou_404(valor: str) -> str:
    try:
        return str(uuid.UUID(valor))
    except ValueError:
        raise HTTPException(status_code=404, detail="Post não encontrado")  # not an id: nothing to start / stream


@router.post("/esteira/posts/{post_id}/criacao", status_code=202)
async def iniciar_criacao(
    post_id: str,
    body: CriacaoIniciar,
    auth=Depends(get_current_user_org),
    svc: CriacaoService = Depends(get_criacao_service),
):
    post_id = _uuid_ou_404(post_id)
    try:
        out = await svc.enfileirar(post_id, org_id=_org(auth), ator_id=str(auth[0].id), passo=body.passo)
    except (CriacaoError, EsteiraError) as exc:
        _raise(exc)
    return success_response(out)


# ── quota ───────────────────────────────────────────────────────────────────────────────────────────────────────────────


def _estado_cota(db: Any, org: str) -> dict:
    res = db.rpc("cs_criacao_cota_estado", {"p_org": org}).execute()
    est = res.data if isinstance(res.data, dict) else (res.data or [None])[0]
    return {
        "limite_usd_mes": float(est["limite_usd_mes"]), "gasto_usd_mes": float(est["gasto_usd_mes"]),
        "restante_usd": float(est["restante_usd"]), "passos_sem_custo": int(est.get("passos_sem_custo") or 0),
    }


@router.get("/criacao/cota")
async def ler_cota(auth=Depends(get_current_user_org), db=Depends(get_cota_db)):
    return success_response(await asyncio.to_thread(_estado_cota, db, _org(auth)))


def _gravar_cota(db: Any, org: str, ator: str, cents: int) -> None:
    """First set = ``create``; every edit = a compare-and-set ``transition`` of the seed transition log (who, from, to)."""
    atual = db.table("cs_criacao_cotas").select("id,limite_usd_cents").eq("org_id", org).execute().data
    if not atual:
        r = db.rpc("cs_criacao_cota_create", {
            "p_org": org, "p_row": {"limite_usd_cents": cents, "updated_by": ator}, "p_data": {}, "p_actor_id": ator,
            "p_actor_kind": "user",
        }).execute().data
    elif int(atual[0]["limite_usd_cents"]) == cents:
        return  # no change is no event
    else:
        r = db.rpc("cs_criacao_cota_transition", {
            "p_org": org, "p_key": {"entity_id": atual[0]["id"]}, "p_from": int(atual[0]["limite_usd_cents"]),
            "p_to": cents, "p_event_type": "cota_alterada", "p_data": {}, "p_actor_id": ator, "p_actor_kind": "user",
        }).execute().data
    r = r[0] if isinstance(r, list) and r else r
    if not isinstance(r, dict) or r.get("status") not in ("ok", "replayed"):
        code = r.get("code") if isinstance(r, dict) else None
        raise HTTPException(
            status_code=409 if code == "stale_state" else 500,
            detail={"code": code or "cota_nao_gravada", "detail": "Não foi possível gravar a cota; tente de novo."},
        )


@router.put("/criacao/cota")
async def definir_cota(
    request: Request,
    body: CotaIn,
    auth=Depends(get_current_user_org),
    db=Depends(get_cota_db),
    admin=Depends(get_cota_admin),
):
    """Org admins only (the trusted ``noctus_users`` row, never ``user_metadata``)."""
    admin(auth, request)
    org = _org(auth)
    cents = int((body.limite_usd_mes * 100).to_integral_value(rounding=ROUND_HALF_UP))
    await asyncio.to_thread(_gravar_cota, db, org, str(auth[0].id), cents)
    return success_response(await asyncio.to_thread(_estado_cota, db, org))


# ── live progress (seed job-progress SSE) ─────────────────────────────────────────────────────────────────────────────────


def _stream_org(_request: Request, auth) -> str:
    return _org(auth)


def _svc(request: Request) -> CriacaoService:
    return request.app.dependency_overrides.get(get_criacao_service, get_criacao_service)()


async def _snapshot_rodada(request: Request, auth, job_id: str):
    post_id, _, rodada = job_id.partition(":")
    try:
        post_id = str(uuid.UUID(post_id))
        n = int(rodada)
    except ValueError:
        return None  # not "{post_id}:{rodada}" -> 404, never a driver error
    return await _svc(request).snapshot(_org(auth), post_id, n)


async def _snapshot_post(request: Request, auth, job_id: str):
    try:
        post_id = str(uuid.UUID(job_id))
    except ValueError:
        return None
    return await _svc(request).snapshot(_org(auth), post_id, None)


router.include_router(
    create_job_progress_router(
        criacao_service.progress_bus(), auth_dependency=get_current_user_org, org_resolver=_stream_org,
        snapshot_loader=_snapshot_rodada, path="/{job_id}/progress",
    ),
    prefix="/esteira/criacao",
)
# the scope `{post_id}` (no rodada) is published by ProgressoComposto: the latest rodada of the post
router.include_router(
    create_job_progress_router(
        criacao_service.progress_bus(), auth_dependency=get_current_user_org, org_resolver=_stream_org,
        snapshot_loader=_snapshot_post, path="/{job_id}/criacao/progress",
    ),
    prefix="/posts",
)

__all__ = ["router"]
