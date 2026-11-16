"""Estruturas library -- READS (estruturas-contract.md section 6.1, tier ``org``).

Every authenticated member browses / chooses; the platform-wide library is never exported (paged <= 50, no CSV
route). The admin-only fields (provenance, source ids, pending-review, non-``ativa`` rows) are stripped for a
non-admin by the service, by construction. Writes live in ``estruturas_admin.py`` (a SEPARATE router, guard
``require_platform_admin``) so a read can never inherit a write gate or the other way round.

Static paths (``/admin``, ``/tipos-bloco``) are declared BEFORE ``/{estrutura_id}``. ``/resolver-perfil`` (EST-4a)
and ``/importacoes`` (EST-3) live in their own routers, included before this one.

NOTE: no ``from __future__ import annotations`` -- keeps FastAPI resolving annotations in this module's globals.
"""
import logging
import uuid
from typing import Callable, Literal, Optional

from fastapi import Depends, HTTPException, Query

from noctusai_lib.api.access_tiers import access_tier, make_router
from noctusai_lib.api.auth._blocking import run_blocking
from noctusai_lib.integrations.storage import StorageBackend
from noctusai_lib.primitives.responses import success_response

from app.dependencies import get_admin_client, get_current_user_org, get_platform_admin_check
from app.modules.certidoes.deps import storage_for
from app.modules.media_creation.schemas.estruturas import Formato, Objetivo
from app.modules.media_creation.services.estruturas_service import (
    EstruturaError,
    EstruturasService,
    assinar_urls,
)

logger = logging.getLogger(__name__)

router = make_router(
    tier="org", guard=get_current_user_org, prefix="/api/media-creation/estruturas",
    tags=["Media Creation — Estruturas"],
)


def get_estruturas_storage() -> StorageBackend:
    """Private ``sw-biblioteca`` bucket (photos / thumbnails as short-TTL signed URLs). Tests MUST override with a
    ``FakeStorageBackend`` (the mock client's ``.storage`` answers anything)."""
    return storage_for(get_admin_client())


def raise_http(exc: EstruturaError):
    raise HTTPException(status_code=exc.status, detail=exc.detail) from exc


def build_service(auth, is_admin: Callable[[str], bool], *, force_admin: bool = False) -> EstruturasService:
    user_id = str(getattr(auth[0], "id", "") or "")
    return EstruturasService(
        get_admin_client(), org_id=str(auth[2]), user_id=user_id,
        is_admin=True if force_admin else bool(user_id and is_admin(user_id)),
    )


@router.get("")
async def listar_estruturas(
    marca_id: Optional[uuid.UUID] = None,
    perfil_id: Optional[uuid.UUID] = None,
    q: Optional[str] = Query(default=None, max_length=200),
    formato: list[Formato] = Query(default=[], max_length=4),
    objetivo: list[Objetivo] = Query(default=[], max_length=4),
    status: Optional[Literal["ativa", "rascunho", "arquivada", "todas"]] = None,
    somente_pendentes_revisao: bool = False,
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0, le=100_000),
    auth=Depends(get_current_user_org),
    is_admin: Callable[[str], bool] = Depends(get_platform_admin_check),
    storage: StorageBackend = Depends(get_estruturas_storage),
):
    svc = build_service(auth, is_admin)
    try:
        data = await run_blocking(
            svc.listar, marca_id=str(marca_id) if marca_id else None, perfil_id=str(perfil_id) if perfil_id else None,
            q=q, formatos=list(formato), objetivos=list(objetivo), status=status,
            somente_pendentes_revisao=somente_pendentes_revisao, limit=limit, offset=offset,
        )
    except EstruturaError as exc:
        raise_http(exc)
    return success_response(await assinar_urls(data, storage))


@router.get("/admin")
@access_tier("org", reason="returns the caller's own is_admin flag, nothing else")
def estruturas_admin(auth=Depends(get_current_user_org), is_admin: Callable[[str], bool] = Depends(get_platform_admin_check)):
    """Whether the caller may edit (drives the FE admin controls; every write enforces it itself)."""
    user_id = str(getattr(auth[0], "id", "") or "")
    return success_response({"is_admin": bool(user_id and is_admin(user_id))})


@router.get("/tipos-bloco")
def listar_tipos_bloco(auth=Depends(get_current_user_org), is_admin: Callable[[str], bool] = Depends(get_platform_admin_check)):
    """The block-type catalog ordered by ``ordem`` (non-admins: ``ativo`` rows only). Read by the block editor, the
    Estrutura detail and the AI prompts."""
    return success_response(build_service(auth, is_admin).tipos_bloco())


@router.get("/{estrutura_id}")
async def get_estrutura(
    estrutura_id: uuid.UUID,
    auth=Depends(get_current_user_org),
    is_admin: Callable[[str], bool] = Depends(get_platform_admin_check),
    storage: StorageBackend = Depends(get_estruturas_storage),
):
    svc = build_service(auth, is_admin)
    try:
        data = await run_blocking(svc.detalhe, str(estrutura_id))
    except EstruturaError as exc:
        raise_http(exc)
    return success_response(await assinar_urls(data, storage))
