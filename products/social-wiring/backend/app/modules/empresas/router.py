"""`/api/empresas/*` — the Cartão CNPJ upload/extraction/document lifecycle
(P0c contract §D3/§D4). The `GET/POST /api/clientes/{cliente_id}/empresas`
listing routes live in `card_hub/router.py` instead (they read across
`atendimento_partes`, card_hub's own territory) — this router owns only the
`empresas`/`empresa_documentos` surface itself.

Errors: `NotFoundError` → 404, `ValidationError_` → 400 (both handled by the
seed's global exception mapping — no local try/except here, same posture
every other card_hub-family router takes; `imovel_hub`'s identical upload
route is the precedent — `noctusai_lib.primitives.exceptions.
ValidationError_.__init__` stamps `status_code=400`, never 422, which is
reserved for a malformed request BODY FastAPI/Pydantic itself rejects
before this module's code ever runs — e.g. the `DELETE .../{documento_id}`
route's required `motivo` query param).
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Query, UploadFile

from app.dependencies import get_current_user_org
from app.modules.card_hub.auth import auth_parts as _auth_parts
from app.modules.empresas import dados_service, documentos_service, extracao_service
from app.modules.empresas.deps import (
    get_cartao_extractor_factory,
    get_empresa_notification_service,
    get_empresas_client,
    get_storage_backend,
)

router = APIRouter(prefix="/api/empresas", tags=["empresas"])


@router.get("/{empresa_id}")
async def get_empresa_route(
    empresa_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_empresas_client),
) -> dict:
    _user, org_id = _auth_parts(auth)
    return dados_service.ensure_empresa(client, org_id, empresa_id)


@router.get("/{empresa_id}/documentos")
async def list_documentos_route(
    empresa_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_empresas_client),
) -> dict:
    _user, org_id = _auth_parts(auth)
    return documentos_service.listar(client, org_id, empresa_id)


@router.post("/{empresa_id}/documentos", status_code=201)
async def upload_documento_route(
    empresa_id: UUID,
    background: BackgroundTasks,
    file: UploadFile = File(...),
    tipo_documento: str = Form(...),
    auth=Depends(get_current_user_org),
    client=Depends(get_empresas_client),
    storage=Depends(get_storage_backend),
    extractor_factory=Depends(get_cartao_extractor_factory),
    notification_service=Depends(get_empresa_notification_service),
) -> dict:
    user, org_id = _auth_parts(auth)
    data = await file.read()
    documento = await documentos_service.upload(
        client, storage, org_id, empresa_id,
        filename=file.filename or "arquivo",
        content_type=file.content_type or "application/octet-stream",
        data=data,
        tipo_documento=tipo_documento,
        enviado_por=getattr(user, "id", None),
    )
    if documentos_service.deve_extrair(tipo_documento):
        background.add_task(
            extracao_service.extrair_cartao,
            client, storage, org_id, empresa_id, UUID(documento["id"]),
            extractor=extractor_factory(str(org_id), tipo_documento),
            notification_service=notification_service,
        )
    return documento


@router.post("/{empresa_id}/documentos/{documento_id}/extrair")
async def reextrair_documento_route(
    empresa_id: UUID,
    documento_id: UUID,
    background: BackgroundTasks,
    auth=Depends(get_current_user_org),
    client=Depends(get_empresas_client),
    storage=Depends(get_storage_backend),
    extractor_factory=Depends(get_cartao_extractor_factory),
    notification_service=Depends(get_empresa_notification_service),
) -> dict:
    """Re-queue extraction. Refused (`ValidationError_` → 422) while the
    document is already `pendente`/`processando` — same posture `card_hub.
    documentos_service.reextrair_documento` takes, so a double-click cannot
    schedule two concurrent reads of the same file."""
    from noctusai_lib.primitives.exceptions import ValidationError_

    _user, org_id = _auth_parts(auth)
    documento = documentos_service.STORE.exigir(client, org_id, empresa_id, documento_id)
    if documento.get("extracao_status") in ("pendente", "processando"):
        raise ValidationError_(
            "Este documento já está em processamento.", field="extracao_status"
        )
    tentativas = int(documento.get("extracao_tentativas") or 0)
    if tentativas >= extracao_service.MAX_TENTATIVAS:
        raise ValidationError_(
            "Este documento já atingiu o número máximo de tentativas.",
            field="extracao_tentativas",
        )
    from app.services import table_reads

    table_reads.table(client, documentos_service.TABLE).update(
        {"extracao_status": "pendente"}
    ).eq("id", str(documento_id)).execute()
    background.add_task(
        extracao_service.extrair_cartao,
        client, storage, org_id, empresa_id, documento_id,
        extractor=extractor_factory(str(org_id), documento["tipo_documento"]),
        notification_service=notification_service,
    )
    return {**documento, "extracao_status": "pendente"}


@router.post("/{empresa_id}/documentos/{documento_id}/extracao/confirmar")
async def confirmar_extracao_route(
    empresa_id: UUID,
    documento_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_empresas_client),
) -> dict:
    """D2 — stamps `empresas.dados_confirmado_por/_em` on the currently
    machine-pending group (contract §D4)."""
    user, org_id = _auth_parts(auth)
    documentos_service.STORE.exigir(client, org_id, empresa_id, documento_id)
    return dados_service.confirmar_dados(
        client, org_id, empresa_id, confirmado_por=getattr(user, "id", None)
    )


@router.post("/{empresa_id}/documentos/{documento_id}/extracao/descartar")
async def descartar_extracao_route(
    empresa_id: UUID,
    documento_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_empresas_client),
) -> dict:
    user, org_id = _auth_parts(auth)
    return documentos_service.descartar_extracao(
        client, org_id, empresa_id, documento_id, usuario_id=getattr(user, "id", None)
    )


@router.get("/{empresa_id}/documentos/{documento_id}/url")
async def get_documento_url_route(
    empresa_id: UUID,
    documento_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_empresas_client),
    storage=Depends(get_storage_backend),
) -> dict:
    """No `intent` query param — view and download reuse the same short-TTL
    signed URL (contract §D4 clarification, 2026-09-24)."""
    user, org_id = _auth_parts(auth)
    return await documentos_service.url_do_documento(
        client, storage, org_id, empresa_id, documento_id,
        usuario_id=getattr(user, "id", None),
    )


@router.delete("/{empresa_id}/documentos/{documento_id}", status_code=204)
async def delete_documento_route(
    empresa_id: UUID,
    documento_id: UUID,
    motivo: str = Query(..., min_length=1),
    auth=Depends(get_current_user_org),
    client=Depends(get_empresas_client),
) -> None:
    """`motivo` is a QUERY PARAM, not a JSON body — the existing transport
    `cliente_documentos`/`imovel_documentos` removal already uses
    (`createCardHubHooks.useDocumentoMutations.remove`); contract §D4
    clarification, 2026-09-24."""
    user, org_id = _auth_parts(auth)
    documentos_service.remover(
        client, org_id, empresa_id, documento_id,
        motivo=motivo, usuario_id=getattr(user, "id", None),
    )


__all__ = ["router"]
