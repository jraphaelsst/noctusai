"""`/api/clientes/{cliente_id}/contratos/{contrato_id}/assinatura[...]` —
e-signature envelope for a contract version. Contract §3.1-§3.3.

Migration 157 adds `POST .../{contrato_id}/assinatura-fisica` — the manual
close-out of a PHYSICAL contract (multipart; the scanned signed PDF is an
optional `file`). Its literal segment `assinatura-fisica` is distinct from
`assinatura`, so neither shadows the other.

A separate file, `include_router`'d into `card_hub/router.py`'s `router`
with one line — same layout `contrato_gerador/router.py` uses. All three
paths here share the segment `.../{contrato_id}/assinatura`, a literal
distinct from `versoes`/`geracao`/`gerar` (the sibling routes already
mounted at this depth), so no route-ordering hazard with this module's
other routers.

The webhook (§3.4) is NOT here — it carries no org, is mounted OUTSIDE
`get_current_user_org`, and lives in
`app/routers/assinatura_webhook_router.py` (the product's top-level
unauthenticated-webhook pattern, same as `whatsapp_router.py`).

Auth is asserted strictly (`== 401`) in
`tests/modules/card_hub/test_auth_boundary_assinatura.py`.
"""
from __future__ import annotations

from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import Field

from noctusai_lib.api import StrictHttpModel

from app.modules.card_hub import assinatura_service as service
from app.modules.card_hub.auth import auth_parts
from app.modules.card_hub.deps import (
    SignatureAdapterFactory,
    get_card_hub_client,
    get_signature_adapter_factory,
    get_storage_backend,
)
from app.dependencies import get_current_user_org

router = APIRouter()


class SignatarioBody(StrictHttpModel):
    nome: str = Field(..., min_length=1, max_length=200)
    #: Loosely typed on purpose (plain `str`, not `EmailStr`) — a malformed
    #: value is the contract's OWN `ASSINATURA_SIGNATARIO_INVALIDO` 400,
    #: never pydantic's generic 422. See `assinatura_service._EMAIL_RE`.
    email: str = Field(..., min_length=1, max_length=200)
    #: Digits or formatted (`412.954.238-98`) — `assinatura_service`
    #: normalises via `noctusai_lib.integrations.documents.cpf.is_valid`.
    cpf: str = Field(..., min_length=11, max_length=14)
    papel: Literal[
        "comprador", "vendedor", "testemunha", "interveniente", "intermediario"
    ]
    ordem: int = 0
    #: [papel='testemunha' only, migration 168] The `org_testemunhas` row
    #: this signatário was selected from (`contrato_testemunhas`) — how
    #: `assinatura_service._resolver_testemunhas_do_registro` re-resolves
    #: the authoritative e-mail/cpf now, replacing the old nome-match. `None`
    #: for every other papel, and for a testemunha submitted with no
    #: registry match (left exactly as typed).
    testemunha_id: Optional[UUID] = None


class EnviarAssinaturaBody(StrictHttpModel):
    versao_id: UUID
    signatarios: list[SignatarioBody]
    mensagem: Optional[str] = Field(default=None, max_length=500)


class CancelarAssinaturaBody(StrictHttpModel):
    motivo: str = Field(..., min_length=3, max_length=500)


@router.post("/{cliente_id}/contratos/{contrato_id}/assinatura", status_code=201)
async def post_assinatura_route(
    cliente_id: UUID,
    contrato_id: UUID,
    body: EnviarAssinaturaBody,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
    storage=Depends(get_storage_backend),
    adapter_factory: SignatureAdapterFactory = Depends(get_signature_adapter_factory),
) -> dict:
    user, org_id = auth_parts(auth)
    return await service.enviar(
        client,
        storage,
        adapter_factory,
        org_id,
        cliente_id,
        contrato_id,
        versao_id=body.versao_id,
        signatarios=[s.model_dump() for s in body.signatarios],
        mensagem=body.mensagem,
        usuario_id=getattr(user, "id", None),
    )


@router.get("/{cliente_id}/contratos/{contrato_id}/assinatura")
async def get_assinatura_route(
    cliente_id: UUID,
    contrato_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    """Read-only — never calls the provider (the webhook is the source of
    truth; contract §3.2)."""
    _user, org_id = auth_parts(auth)
    return service.obter(client, org_id, cliente_id, contrato_id)


@router.post("/{cliente_id}/contratos/{contrato_id}/assinatura/cancelar")
async def post_assinatura_cancelar_route(
    cliente_id: UUID,
    contrato_id: UUID,
    body: CancelarAssinaturaBody,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
    adapter_factory: SignatureAdapterFactory = Depends(get_signature_adapter_factory),
) -> dict:
    user, org_id = auth_parts(auth)
    return await service.cancelar(
        client,
        adapter_factory,
        org_id,
        cliente_id,
        contrato_id,
        motivo=body.motivo,
        usuario_id=getattr(user, "id", None),
    )


@router.post("/{cliente_id}/contratos/{contrato_id}/assinatura-fisica")
async def post_assinatura_fisica_route(
    cliente_id: UUID,
    contrato_id: UUID,
    file: Optional[UploadFile] = File(None),
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
    storage=Depends(get_storage_backend),
) -> dict:
    """Migration 157 — "Marcar como assinado" for a 'fisica' contract.
    Returns the contract (same shape `GET .../contratos` lists)."""
    user, org_id = auth_parts(auth)
    arquivo = None
    if file is not None:
        arquivo = (
            await file.read(),
            file.filename or "contrato-assinado.pdf",
            file.content_type or "application/octet-stream",
        )
    return await service.marcar_assinado_fisico(
        client,
        storage,
        org_id,
        cliente_id,
        contrato_id,
        arquivo=arquivo,
        usuario_id=getattr(user, "id", None),
    )


__all__ = [
    "CancelarAssinaturaBody",
    "EnviarAssinaturaBody",
    "SignatarioBody",
    "router",
]
