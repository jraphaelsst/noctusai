"""CoreStudio post assets: ``/api/media-creation/cs-posts/{post_id}/assets`` + the validity matrix.

The file is read from storage and probed HERE (media kind, aspect ratio, duration come from the bytes, never from the
request body). Two DI seams: ``get_midia_storage`` and ``get_midia_probe`` — tests inject a Fake backend / probe.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from starlette.concurrency import run_in_threadpool

from noctusai_lib.integrations.storage import StorageBackend
from noctusai_lib.primitives.responses import success_response

from app.dependencies import coerce_org_uuid, get_admin_client, get_current_user_org
from app.modules.certidoes.deps import storage_for
from app.modules.media_creation.post_formatos import matriz_publica
from app.modules.media_creation.schemas.post_assets import AssetRegistrar, AssetStatusUpdate
from app.modules.media_creation.services.post_assets_service import (
    MAX_BYTES,
    MIDIA_BUCKET,
    MidiaProbe,
    MidiaStat,
    PostAssetError,
    PostAssetsService,
    checar_magic,
    probe_midia,
    stat_midia,
)

logger = logging.getLogger(__name__)
PREFIX = "/api/media-creation/cs-posts"
router = APIRouter(prefix=PREFIX, tags=["Media Creation — Post assets"])


def get_midia_storage() -> StorageBackend:
    """DI seam: blob storage for post media (tests override with a Fake backend)."""
    return storage_for(get_admin_client())


def get_midia_probe() -> MidiaProbe:
    """DI seam: the media reader (tests override with a deterministic probe)."""
    return probe_midia


def get_midia_stat() -> MidiaStat:
    """DI seam: object size from storage metadata, before any download (tests inject a Fake)."""
    client = get_admin_client()
    return lambda bucket, key: stat_midia(client, bucket, key)


def get_post_assets_db() -> Any:
    return get_admin_client()


def _svc(auth, db) -> PostAssetsService:
    return PostAssetsService(db, str(coerce_org_uuid(auth[2])), str(auth[0].id))


def _raise(exc: PostAssetError):
    raise HTTPException(status_code=exc.status, detail=exc.detail)


@router.get("/formatos")
def matriz_de_formatos(auth=Depends(get_current_user_org)):
    """The rede x formato x assets validity matrix (the FE greys out invalid targets from it)."""
    return success_response(matriz_publica())


@router.get("/{post_id}/assets")
def listar_assets(
    post_id: str, historico: bool = Query(False), auth=Depends(get_current_user_org), db=Depends(get_post_assets_db),
):
    try:
        return success_response(_svc(auth, db).listar(post_id, historico=historico))
    except PostAssetError as exc:
        _raise(exc)


@router.post("/{post_id}/assets", status_code=201)
async def registrar_asset(
    post_id: str,
    body: AssetRegistrar,
    auth=Depends(get_current_user_org),
    db=Depends(get_post_assets_db),
    storage: StorageBackend = Depends(get_midia_storage),
    probe: MidiaProbe = Depends(get_midia_probe),
    stat: MidiaStat = Depends(get_midia_stat),
):
    svc = _svc(auth, db)
    try:
        await run_in_threadpool(svc.validar_caminho, post_id, body.storage_path)
        tamanho = await run_in_threadpool(stat, MIDIA_BUCKET, body.storage_path)
        if tamanho is None:
            raise PostAssetError(422, {"code": "arquivo_nao_encontrado", "detail": "Arquivo não encontrado no armazenamento"})
        if tamanho > MAX_BYTES:  # checked on metadata BEFORE the object is read into memory
            raise PostAssetError(413, {"code": "arquivo_grande_demais", "detail": "Arquivo acima do limite"})
        blob = await storage.get(bucket=MIDIA_BUCKET, key=body.storage_path)
        if blob is None:
            raise PostAssetError(422, {"code": "arquivo_nao_encontrado", "detail": "Arquivo não encontrado no armazenamento"})
        if len(blob.data) > MAX_BYTES:
            raise PostAssetError(413, {"code": "arquivo_grande_demais", "detail": "Arquivo acima do limite"})
        checar_magic(blob.data, body.storage_path)
        fato = await run_in_threadpool(probe, blob.data, body.storage_path)
        row = await run_in_threadpool(
            lambda: svc.registrar(
                post_id, storage_path=body.storage_path, ordem=body.ordem, fato=fato,
                mime_type=blob.metadata.content_type, tamanho_bytes=len(blob.data),
            )
        )
    except PostAssetError as exc:
        _raise(exc)
    return success_response(row)


@router.patch("/{post_id}/assets/{asset_id}")
def atualizar_status_asset(
    post_id: str, asset_id: str, body: AssetStatusUpdate, auth=Depends(get_current_user_org), db=Depends(get_post_assets_db),
):
    try:
        return success_response(_svc(auth, db).atualizar_status(post_id, asset_id, body.status))
    except PostAssetError as exc:
        _raise(exc)
