"""Contratos — wave-2 slice A (roadmap R10/R12).

  GET  /api/contratos?cliente_id=
  GET  /api/contratos/{id}/pdf               signed URL of the generated contract
  POST /api/contratos/{id}/marcar-assinado   física only; optional multipart
                                             `arquivo` (the signed scan) →
                                             contrato ativo, cliente ativo

A contrato is CREATED from an accepted orçamento
(`POST /api/orcamentos/{id}/contrato`, `orcamento_router`). A digital
contrato is activated by the HMAC-signed signature webhook
(`/api/comercial/assinatura/webhook`), never by hand.
"""
# NOTE: no `from __future__ import annotations` — consistent with the other
# IgIg routers; see esteira_router.py.
import logging
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from noctusai_lib.integrations.storage import StorageBackend
from noctusai_lib.primitives.responses import success_response

from app.config import settings
from app.dependencies import coerce_org_uuid, get_current_user_org
from app.pipelines import get_db
from app.services import contratos as svc
from app.services import quadro_comum as qc
from app.services.regras import RegraViolada, http_de
from app.storage import get_storage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/contratos", tags=["contratos"])

#: Business limit for the signed scan. `app/main.py`'s max-body override for
#: this route sits ~20% above it so THIS 413 is the one the user sees.
ASSINADO_MAX_BYTES = 25 * 1024 * 1024
ASSINADO_TIPOS = {"application/pdf", "image/jpeg", "image/png"}


def _org(auth: tuple) -> str:
    _user, _token, raw_org = auth
    return str(coerce_org_uuid(raw_org))


@router.get("")
async def listar_contratos(
    cliente_id: str | None = None,
    auth: tuple = Depends(get_current_user_org),
    db: Any = Depends(get_db),
) -> dict:
    return success_response(svc.listar(db, _org(auth), cliente_id=cliente_id))


@router.get("/{contrato_id}/pdf")
async def url_contrato(
    contrato_id: str,
    auth: tuple = Depends(get_current_user_org),
    db: Any = Depends(get_db),
    storage: StorageBackend = Depends(get_storage),
) -> dict:
    contrato = qc.carregar(db, "contrato", _org(auth), contrato_id,
                           select="id, documento_key, documento_assinado_key", rotulo="contrato")
    if not contrato.get("documento_key"):
        raise http_de(RegraViolada(409, "pdf_nao_gerado", "Este contrato não tem documento gerado."))
    url = await storage.signed_url(bucket=settings.igig_storage_bucket,
                                   key=contrato["documento_key"],
                                   expires_in_seconds=svc.URL_TTL_SEGUNDOS)
    assinado = None
    if contrato.get("documento_assinado_key"):
        assinado = await storage.signed_url(bucket=settings.igig_storage_bucket,
                                            key=contrato["documento_assinado_key"],
                                            expires_in_seconds=svc.URL_TTL_SEGUNDOS)
    return success_response({"url": url, "url_assinado": assinado})


@router.post("/{contrato_id}/marcar-assinado")
async def marcar_assinado(
    contrato_id: str,
    arquivo: UploadFile | None = File(default=None),
    auth: tuple = Depends(get_current_user_org),
    db: Any = Depends(get_db),
    storage: StorageBackend = Depends(get_storage),
) -> dict:
    """The printed contract came back signed by hand (roadmap R12, física)."""
    anexo = None
    if arquivo is not None:
        tipo = (arquivo.content_type or "").lower()
        if tipo not in ASSINADO_TIPOS:
            raise http_de(RegraViolada(
                422, "arquivo_invalido", "Envie o contrato assinado em PDF, JPG ou PNG.",
            ))
        dados = await arquivo.read()
        if len(dados) > ASSINADO_MAX_BYTES:
            raise HTTPException(status_code=413, detail="Arquivo excede 25 MB")
        if not dados:
            raise http_de(RegraViolada(422, "arquivo_vazio", "O arquivo enviado está vazio."))
        anexo = (dados, arquivo.filename or "assinado.pdf", tipo)
    try:
        contrato = await svc.marcar_assinado(
            db, _org(auth), contrato_id, arquivo=anexo,
            storage=storage, bucket=settings.igig_storage_bucket,
        )
    except RegraViolada as erro:
        raise http_de(erro) from erro
    return success_response(contrato)
