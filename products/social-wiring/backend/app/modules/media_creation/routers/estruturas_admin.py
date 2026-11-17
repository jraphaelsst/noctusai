"""Estruturas library -- ADMIN WRITES (estruturas-contract.md section 6.2, tier ``platform``).

Platform admins only (``require_platform_admin``: 403 with a plain string detail). The router is built with
``make_router(tier="platform", guard=require_platform_admin)``: every route inherits the gate and is left out of the
public OpenAPI schema. Every write is ONE call to a SECURITY DEFINER RPC that mutates and writes its event row in the
same transaction; every response is the fresh ``EstruturaDetalhe`` with the admin fields. ``a-partir-do-viral`` (EST-5)
and ``importacoes`` (EST-3) are other routers.

NOTE: no ``from __future__ import annotations`` -- keeps FastAPI resolving annotations in this module's globals.
"""
import logging
import uuid

from fastapi import Depends, Response

from noctusai_lib.api.access_tiers import make_router
from noctusai_lib.api.auth._blocking import run_blocking
from noctusai_lib.integrations.storage import StorageBackend
from noctusai_lib.primitives.responses import success_response

from app.dependencies import get_admin_client, get_platform_admin_check, require_platform_admin
from app.modules.media_creation.routers.estruturas import (
    build_service,
    get_estruturas_storage,
    raise_http,
)
from app.modules.media_creation.schemas.estruturas import (
    BlocosReplace,
    ConfirmarBody,
    EstruturaCreate,
    EstruturaPatch,
    PublicarBody,
    TipoBlocoCreate,
    TipoBlocoUpdate,
)
from app.modules.media_creation.services.estruturas_service import EstruturaError, assinar_urls

logger = logging.getLogger(__name__)

router = make_router(
    tier="platform", guard=require_platform_admin, prefix="/api/media-creation/estruturas",
    tags=["Media Creation — Estruturas (admin)"],
)


def _svc(auth, is_admin):
    return build_service(auth, is_admin, force_admin=True)


async def _run(fn, *args, storage: StorageBackend, **kwargs):
    try:
        data = await run_blocking(fn, *args, **kwargs)
    except EstruturaError as exc:
        raise_http(exc)
    return success_response(await assinar_urls(data, storage))


@router.post("", status_code=201)
async def criar_estrutura(
    body: EstruturaCreate, auth=Depends(require_platform_admin), is_admin=Depends(get_platform_admin_check),
    storage: StorageBackend = Depends(get_estruturas_storage),
):
    return await _run(_svc(auth, is_admin).criar, body.model_dump(mode="json"), storage=storage)


@router.patch("/{estrutura_id}")
async def atualizar_estrutura(
    estrutura_id: uuid.UUID, body: EstruturaPatch, auth=Depends(require_platform_admin),
    is_admin=Depends(get_platform_admin_check), storage: StorageBackend = Depends(get_estruturas_storage),
):
    patch = {k: getattr(body, k) for k in body.model_fields_set}
    patch = {k: (str(v) if isinstance(v, uuid.UUID) else v) for k, v in patch.items()}
    return await _run(_svc(auth, is_admin).atualizar, str(estrutura_id), patch, storage=storage)


@router.put("/{estrutura_id}/blocos")
async def substituir_blocos(
    estrutura_id: uuid.UUID, body: BlocosReplace, auth=Depends(require_platform_admin),
    is_admin=Depends(get_platform_admin_check), storage: StorageBackend = Depends(get_estruturas_storage),
):
    return await _run(
        _svc(auth, is_admin).substituir_blocos, str(estrutura_id), body.expected_versao,
        [b.model_dump(mode="json") for b in body.blocos], storage=storage,
    )


@router.post("/{estrutura_id}/confirmar")
async def confirmar_campos(
    estrutura_id: uuid.UUID, body: ConfirmarBody, auth=Depends(require_platform_admin),
    is_admin=Depends(get_platform_admin_check), storage: StorageBackend = Depends(get_estruturas_storage),
):
    return await _run(
        _svc(auth, is_admin).confirmar, str(estrutura_id), body.expected_versao, body.campos, bool(body.todos),
        storage=storage,
    )


@router.post("/{estrutura_id}/publicar")
async def publicar_estrutura(
    estrutura_id: uuid.UUID, body: PublicarBody, auth=Depends(require_platform_admin),
    is_admin=Depends(get_platform_admin_check), storage: StorageBackend = Depends(get_estruturas_storage),
):
    return await _run(_svc(auth, is_admin).publicar, str(estrutura_id), body.expected_versao, storage=storage)


@router.post("/{estrutura_id}/arquivar")
async def arquivar_estrutura(
    estrutura_id: uuid.UUID, auth=Depends(require_platform_admin), is_admin=Depends(get_platform_admin_check),
    storage: StorageBackend = Depends(get_estruturas_storage),
):
    return await _run(_svc(auth, is_admin).arquivar, str(estrutura_id), storage=storage)


@router.post("/{estrutura_id}/restaurar")
async def restaurar_estrutura(
    estrutura_id: uuid.UUID, auth=Depends(require_platform_admin), is_admin=Depends(get_platform_admin_check),
    storage: StorageBackend = Depends(get_estruturas_storage),
):
    return await _run(_svc(auth, is_admin).restaurar, str(estrutura_id), storage=storage)


@router.delete("/{estrutura_id}", status_code=204)
async def excluir_estrutura(estrutura_id: uuid.UUID, auth=Depends(require_platform_admin), is_admin=Depends(get_platform_admin_check)):
    try:
        await run_blocking(_svc(auth, is_admin).excluir, str(estrutura_id))
    except EstruturaError as exc:
        raise_http(exc)
    return Response(status_code=204)


# ── block-type catalog ───────────────────────────────────────────────────────────────────────────────────────


@router.post("/tipos-bloco", status_code=201)
async def criar_tipo_bloco(body: TipoBlocoCreate, auth=Depends(require_platform_admin), is_admin=Depends(get_platform_admin_check)):
    try:
        data = await run_blocking(_svc(auth, is_admin).tipo_criar, body.model_dump(mode="json"))
    except EstruturaError as exc:
        raise_http(exc)
    return success_response(data)


@router.put("/tipos-bloco/{tipo_id}")
async def atualizar_tipo_bloco(
    tipo_id: uuid.UUID, body: TipoBlocoUpdate, auth=Depends(require_platform_admin), is_admin=Depends(get_platform_admin_check),
):
    patch = {k: getattr(body, k) for k in body.model_fields_set}
    try:
        data = await run_blocking(_svc(auth, is_admin).tipo_atualizar, str(tipo_id), patch)
    except EstruturaError as exc:
        raise_http(exc)
    return success_response(data)


@router.delete("/tipos-bloco/{tipo_id}", status_code=204)
async def excluir_tipo_bloco(tipo_id: uuid.UUID, auth=Depends(require_platform_admin), is_admin=Depends(get_platform_admin_check)):
    try:
        await run_blocking(_svc(auth, is_admin).tipo_excluir, str(tipo_id))
    except EstruturaError as exc:
        raise_http(exc)
    return Response(status_code=204)
