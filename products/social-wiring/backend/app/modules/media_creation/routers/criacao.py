"""Criação (media production) endpoints: ``/api/media-creation/esteira`` (criacao-pipeline-contract.md sections 1, 3, 5).

* ``POST /posts/{post_id}/criacao`` -- manual start of a post's media job graph, or (body ``{"passo": ...}``) the re-run
  of a failed / rejected step + everything downstream, as a new rodada. 202; nothing is produced in the request: the
  separate ``worker criacao`` process does the work. The S5 trigger calls the same service function when the card enters
  Criação.
* ``GET /criacao/{post_id}:{rodada}/progress`` -- SSE of the graph's live progress (seed ``create_job_progress_router``;
  the first frame is read from the ledger, so a client that connects late or after the end still sees the truth).

Auth ``get_current_user_org`` (tier ``org``); a foreign / unknown post is a 404; refusals are coded
``HTTPException(detail={"code", "detail"})``.
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import Depends, HTTPException, Request
from pydantic import Field

from noctusai_lib.api import StrictHttpModel
from noctusai_lib.api.access_tiers import make_router
from noctusai_lib.primitives.responses import success_response
from noctusai_lib.realtime import create_job_progress_router

from app.dependencies import coerce_org_uuid, get_admin_client, get_current_user_org
from app.modules.media_creation.services import criacao_service
from app.modules.media_creation.services.criacao_service import CriacaoError, CriacaoService

PREFIX = "/api/media-creation/esteira"
router = make_router(tier="org", guard=get_current_user_org, prefix=PREFIX, tags=["Media Creation — Criação"])


class CriacaoIniciar(StrictHttpModel):
    #: omitted = produce the whole route; given = re-run that step (and its downstream) of a failed / rejected post.
    passo: Optional[str] = Field(default=None, min_length=1, max_length=40)


def get_criacao_service() -> CriacaoService:
    """DI seam: the service over the admin client (it only ENQUEUES here). Tests override with a Fake-backed one."""
    return criacao_service.build_service(get_admin_client())


def _org(auth) -> str:
    return str(coerce_org_uuid(auth[2]))


def _raise(exc: CriacaoError):
    raise HTTPException(status_code=exc.status, detail={"code": exc.code, "detail": exc.detail}) from exc


def _uuid_ou_404(valor: str) -> str:
    try:
        return str(uuid.UUID(valor))
    except ValueError:
        raise HTTPException(status_code=404, detail="Post não encontrado")  # not an id: nothing to start / stream


@router.post("/posts/{post_id}/criacao", status_code=202)
async def iniciar_criacao(
    post_id: str,
    body: CriacaoIniciar,
    auth=Depends(get_current_user_org),
    svc: CriacaoService = Depends(get_criacao_service),
):
    post_id = _uuid_ou_404(post_id)
    try:
        if body.passo:
            out = await svc.reexecutar(post_id, body.passo, org_id=_org(auth), ator_id=str(auth[0].id))
        else:
            out = await svc.enfileirar(post_id, org_id=_org(auth), ator_id=str(auth[0].id))
    except CriacaoError as exc:
        _raise(exc)
    return success_response(out)


# ── live progress (seed job-progress SSE; scope = org + "{post_id}:{rodada}") ─────────────────────────────────────────


def _stream_org(_request: Request, auth) -> str:
    return _org(auth)


async def _snapshot(request: Request, auth, job_id: str):
    post_id, _, rodada = job_id.partition(":")
    try:
        post_id = str(uuid.UUID(post_id))
        n = int(rodada)
    except ValueError:
        return None  # not "{post_id}:{rodada}" -> 404, never a driver error
    svc: CriacaoService = request.app.dependency_overrides.get(get_criacao_service, get_criacao_service)()
    return await svc.snapshot(_org(auth), post_id, n)


router.include_router(
    create_job_progress_router(
        criacao_service.progress_bus(),
        auth_dependency=get_current_user_org,
        org_resolver=_stream_org,
        snapshot_loader=_snapshot,
        path="/{job_id}/progress",
    ),
    prefix="/criacao",
)

__all__ = ["router"]
