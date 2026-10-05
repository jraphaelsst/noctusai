"""Antigos proprietários routes — mounted under `/api/clientes` (see
`products/social-wiring/projects/antigos-proprietarios-CONTRACT.md`).

`GET    /{cliente_id}/certidoes/antigos-proprietarios`            header state
`POST   /{cliente_id}/certidoes/antigos-proprietarios/sincronizar` matrícula → group (+ emission)
`POST   /{cliente_id}/certidoes/antigos-proprietarios`            add by hand
`DELETE /{cliente_id}/certidoes/antigos-proprietarios/{parte_id}` remove
`PUT    /{cliente_id}/certidoes/antigos-proprietarios/dispensa`   dispense (admin)
`DELETE /{cliente_id}/certidoes/antigos-proprietarios/dispensa`   undispense (admin)

The rows themselves ride on `GET …/certidoes/partes` (`grupo =
antigo_proprietario`); there is no parallel list endpoint.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response
from noctusai_lib.api import StrictHttpModel
from noctusai_lib.api.auth.session import is_org_admin
from noctusai_lib.integrations.storage import StorageBackend
from pydantic import Field

from app.dependencies import get_core_client, get_current_user_org
from app.modules.card_hub import antigos_proprietarios_service as svc
from app.modules.card_hub.auth import auth_parts
from app.modules.card_hub.deps import get_card_hub_client
from app.modules.certidoes.deps import (
    CertidoesService,
    get_certidoes_service,
    get_storage_backend,
)

router = APIRouter()


class DispensaBody(StrictHttpModel):
    motivo: str = Field(min_length=svc.MOTIVO_MIN, max_length=svc.MOTIVO_MAX)
    atendimento_id: Optional[UUID] = None


class AntigoCreateBody(StrictHttpModel):
    """A person (`nome` + `cpf`) OR a company (`cnpj` [+ `razao_social`])."""

    nome: Optional[str] = Field(default=None, max_length=255)
    cpf: Optional[str] = Field(default=None, max_length=18)
    cnpj: Optional[str] = Field(default=None, max_length=18)
    razao_social: Optional[str] = Field(default=None, max_length=255)
    atendimento_id: Optional[UUID] = None


class SincronizarBody(StrictHttpModel):
    atendimento_id: Optional[UUID] = None


def _exigir_admin(user) -> None:
    if not is_org_admin(get_core_client(), getattr(user, "id", None)):
        raise HTTPException(
            status_code=403,
            detail="Dispensar os antigos proprietários de um negócio é restrito a administradores.",
        )


def _agendar(background_tasks: BackgroundTasks, certidoes: CertidoesService, client, storage, emissoes) -> None:
    for e in emissoes:
        if e.get("consulta_id"):
            background_tasks.add_task(certidoes.processar_consulta, e["consulta_id"], client, storage)


@router.get("/{cliente_id}/certidoes/antigos-proprietarios")
async def get_antigos_route(
    cliente_id: UUID,
    atendimento_id: Optional[UUID] = None,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    user, org_id = auth_parts(auth)
    return svc.estado(
        client, org_id, cliente_id, atendimento_id=atendimento_id, usuario_id=getattr(user, "id", None)
    )


@router.post("/{cliente_id}/certidoes/antigos-proprietarios/sincronizar")
async def sincronizar_antigos_route(
    cliente_id: UUID,
    body: SincronizarBody,
    background_tasks: BackgroundTasks,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
    storage: StorageBackend = Depends(get_storage_backend),
    certidoes: CertidoesService = Depends(get_certidoes_service),
) -> dict:
    user, org_id = auth_parts(auth)
    out = svc.sincronizar(
        client, org_id, cliente_id, atendimento_id=body.atendimento_id,
        user_id=getattr(user, "id", None), check_credentials=certidoes.check_required_credentials,
    )
    _agendar(background_tasks, certidoes, client, storage, out["emissoes"])
    return out


@router.post("/{cliente_id}/certidoes/antigos-proprietarios", status_code=201)
async def adicionar_antigo_route(
    cliente_id: UUID,
    body: AntigoCreateBody,
    background_tasks: BackgroundTasks,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
    storage: StorageBackend = Depends(get_storage_backend),
    certidoes: CertidoesService = Depends(get_certidoes_service),
) -> dict:
    user, org_id = auth_parts(auth)
    out = svc.adicionar_manual(
        client, org_id, cliente_id, nome=body.nome, cpf=body.cpf, cnpj=body.cnpj,
        razao_social=body.razao_social, atendimento_id=body.atendimento_id,
        user_id=getattr(user, "id", None), check_credentials=certidoes.check_required_credentials,
    )
    _agendar(background_tasks, certidoes, client, storage, [out["emissao"]])
    return out


@router.put("/{cliente_id}/certidoes/antigos-proprietarios/dispensa")
async def dispensar_antigos_route(
    cliente_id: UUID,
    body: DispensaBody,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    """Admin-only (trusted `noctus_users` row, never `user_metadata`) — same
    gate as `PUT …/contratos/{id}/processo-legado`."""
    user, org_id = auth_parts(auth)
    _exigir_admin(user)
    return svc.dispensar(
        client, org_id, cliente_id, motivo=body.motivo,
        usuario_id=getattr(user, "id", None), atendimento_id=body.atendimento_id,
    )


@router.delete("/{cliente_id}/certidoes/antigos-proprietarios/dispensa")
async def reativar_antigos_route(
    cliente_id: UUID,
    atendimento_id: Optional[UUID] = None,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    user, org_id = auth_parts(auth)
    _exigir_admin(user)
    return svc.reativar(
        client, org_id, cliente_id, usuario_id=getattr(user, "id", None), atendimento_id=atendimento_id
    )


@router.delete("/{cliente_id}/certidoes/antigos-proprietarios/{parte_id}", status_code=204)
async def remover_antigo_route(
    cliente_id: UUID,
    parte_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> Response:
    _user, org_id = auth_parts(auth)
    svc.remover(client, org_id, cliente_id, parte_id)
    return Response(status_code=204)
