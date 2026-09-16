"""`/api/edicao-fotos/guias` — the company style guide (contract §6).

| Method | Path | Who |
|---|---|---|
| GET  | `/guias` | platform admin ∨ photo curator — every version, newest first |
| POST | `/guias` | same — a MANUALLY written draft (`{"texto"}`) |
| POST | `/guias/regenerar` | same — enqueue `fotos.regen_guia` now (AI draft from the pool) |
| POST | `/guias/{versao}/ativar` | same — this version becomes the one batches snapshot |
| POST | `/guias/{versao}/restaurar` | same — clone as a NEW draft (versions are immutable) |

Every new version is a DRAFT until activated. Activation never changes an
in-flight batch: the effective guide is snapshotted at submit.

The manual draft exists so R1 can run without the AI builder (no OpenAI
credits, PROJECT.md §4c): write → activate → `POST /lotes/{id}/submeter`
stops answering 409 `guia_nao_ativo`.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from noctusai_lib.domain.photo_editing import (
    Actor,
    PhotoEditingPorts,
    activate_version,
    create_draft,
    request_guide_regen,
    restore_version,
)

from app.modules.edicao_fotos.deps import get_edicao_ports, require_pool_manager
from app.modules.edicao_fotos.errors import ENGINE_ERRORS, engine_error
from app.modules.edicao_fotos.presenters import guia_out, page_out
from app.modules.edicao_fotos.schemas import GuiaCreateBody

router = APIRouter(prefix="/api/edicao-fotos/guias", tags=["edicao-fotos"])


@router.get("")
async def list_guias_route(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _actor: Actor = Depends(require_pool_manager),
    ports: PhotoEditingPorts = Depends(get_edicao_ports),
) -> dict:
    guides, total = await ports.repo.list_guides(limit=page_size, offset=(page - 1) * page_size)
    active = await ports.repo.get_active_guide()
    return {
        **page_out([guia_out(g) for g in guides], page=page, page_size=page_size, total=total),
        "versao_ativa": active.versao if active else None,
    }


@router.post("", status_code=201)
async def create_guia_route(
    body: GuiaCreateBody,
    actor: Actor = Depends(require_pool_manager),
    ports: PhotoEditingPorts = Depends(get_edicao_ports),
) -> dict:
    guide = await create_draft(
        ports, texto=body.texto, gerado_de_versao=None, criado_por=actor.user_id
    )
    return guia_out(guide)


@router.post("/regenerar", status_code=202)
async def regenerate_guia_route(
    actor: Actor = Depends(require_pool_manager),
    ports: PhotoEditingPorts = Depends(get_edicao_ports),
) -> dict:
    try:
        job = await request_guide_regen(ports, requested_by=actor.user_id)
    except ENGINE_ERRORS as exc:
        raise engine_error(exc) from exc
    # The draft appears in GET /guias once the worker has run the job.
    return {"job_id": str(job.id), "status": str(getattr(job.status, "value", job.status))}


@router.post("/{versao}/ativar")
async def activate_guia_route(
    versao: int,
    actor: Actor = Depends(require_pool_manager),
    ports: PhotoEditingPorts = Depends(get_edicao_ports),
) -> dict:
    try:
        guide = await activate_version(ports, versao, ativado_por=actor.user_id)
    except ENGINE_ERRORS as exc:
        raise engine_error(exc) from exc
    return guia_out(guide)


@router.post("/{versao}/restaurar", status_code=201)
async def restore_guia_route(
    versao: int,
    actor: Actor = Depends(require_pool_manager),
    ports: PhotoEditingPorts = Depends(get_edicao_ports),
) -> dict:
    try:
        guide = await restore_version(ports, versao, criado_por=actor.user_id)
    except ENGINE_ERRORS as exc:
        raise engine_error(exc) from exc
    return guia_out(guide)
