"""Per-party Certidões routes — mounted under `/api/clientes` by the Wave C0
integration patch (CONTRACT §10; `card_hub/router.py` includes this `router`).

Paths (final): `GET /{cliente_id}/certidoes/partes`,
`POST /{cliente_id}/certidoes/partes/{kind}/{alvo_id}/emissao`,
`POST /{cliente_id}/certidoes/resultados/{resultado_id}/reemitir`,
`POST /{cliente_id}/certidoes/celulas`,
`POST /{cliente_id}/certidoes/reler`. Raw-dict responses, no `{"data":…}`
envelope (card routes' convention, CONTRACT §0). All the logic lives in
`certidoes_partes_service`; this file only unpacks auth, schedules the
background InfoSimples run for the two emission routes, and sets status codes.
"""
from __future__ import annotations

from datetime import date
from typing import Optional
from uuid import UUID

import logging

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, Response
from noctusai_lib.integrations.storage import StorageBackend

from app.dependencies import get_current_user_org
from app.modules.card_hub import certidoes_partes_service as svc
from app.modules.card_hub.auth import auth_parts
from app.modules.card_hub.certidoes_partes_schemas import (
    CelulaBody,
    CienciaPcenBody,
    EmissaoBody,
    ReemitirBody,
    RelerBody,
)
from app.modules.card_hub.deps import get_card_hub_client
from app.modules.certidoes.deps import (
    CertidoesService,
    get_certidoes_service,
    get_storage_backend,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/{cliente_id}/certidoes/partes")
async def get_certidoes_partes_route(
    cliente_id: UUID,
    atendimento_id: Optional[UUID] = None,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    _user, org_id = auth_parts(auth)
    return svc.montar(client, org_id, cliente_id, atendimento_id=atendimento_id, hoje=date.today())


@router.post("/{cliente_id}/certidoes/partes/{kind}/{alvo_id}/emissao", status_code=201)
async def solicitar_emissao_route(
    cliente_id: UUID,
    kind: str,
    alvo_id: UUID,
    body: EmissaoBody,
    background_tasks: BackgroundTasks,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
    storage: StorageBackend = Depends(get_storage_backend),
    certidoes: CertidoesService = Depends(get_certidoes_service),
) -> dict:
    user, org_id = auth_parts(auth)
    out = svc.solicitar_emissao(
        client, org_id, cliente_id, kind, alvo_id,
        tipos=body.tipos, atendimento_id=body.atendimento_id,
        user_id=user.id, check_credentials=certidoes.check_required_credentials,
    )
    background_tasks.add_task(certidoes.processar_consulta, out["consulta_id"], client, storage)
    return out


@router.post("/{cliente_id}/certidoes/resultados/{resultado_id}/reemitir", status_code=201)
async def reemitir_route(
    cliente_id: UUID,
    resultado_id: UUID,
    body: ReemitirBody,
    background_tasks: BackgroundTasks,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
    storage: StorageBackend = Depends(get_storage_backend),
    certidoes: CertidoesService = Depends(get_certidoes_service),
) -> dict:
    user, org_id = auth_parts(auth)
    out = svc.reemitir(
        client, org_id, cliente_id, str(resultado_id),
        user_id=user.id, check_credentials=certidoes.check_required_credentials,
    )
    background_tasks.add_task(certidoes.processar_consulta, out["consulta_id"], client, storage)
    return out


@router.post("/{cliente_id}/certidoes/resultados/{resultado_id}/ciencia-pcen")
async def ciencia_pcen_route(
    cliente_id: UUID,
    resultado_id: UUID,
    body: CienciaPcenBody,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    """Receita "positiva com efeitos de negativa" 2ª via — the operator's
    acknowledgment (`entendi`) or support question (`duvida`); the contract
    readiness stays pending until `entendi` (owner amendment 2026-10-01)."""
    user, org_id = auth_parts(auth)
    return svc.registrar_ciencia_pcen(
        client, org_id, cliente_id, str(resultado_id), acao=body.acao, user_id=user.id,
    )


@router.post("/{cliente_id}/certidoes/celulas")
async def garantir_celula_route(
    cliente_id: UUID,
    body: CelulaBody,
    response: Response,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    user, org_id = auth_parts(auth)
    out, criado = svc.garantir_celula(
        client, org_id, cliente_id,
        kind=body.kind, alvo_id=body.alvo_id, linha_chave=body.linha_chave,
        atendimento_id=body.atendimento_id, user_id=user.id,
    )
    response.status_code = 201 if criado else 200
    return out


@router.post("/{cliente_id}/certidoes/reler")
async def reler_certidoes_route(
    cliente_id: UUID,
    body: RelerBody,
    background_tasks: BackgroundTasks,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
    storage: StorageBackend = Depends(get_storage_backend),
    certidoes: CertidoesService = Depends(get_certidoes_service),
) -> dict:
    """Re-read every stored certidão PDF (upload or live receipt) of the
    card's parties on the files already stored — `POST /api/certidoes/resultados/{id}/reler` for
    the whole card. Counts come back now; the extractions run as
    `BackgroundTasks` jobs, sequentially. Human-confirmed values are kept
    (D1); each re-read is logged with the actor in `certidao_resultado_acessos`
    (`acao='releitura'`)."""
    user, org_id = auth_parts(auth)
    async with httpx.AsyncClient() as http_client:
        contagem, extracoes = await svc.reler_certidoes_do_card(
            client, org_id, cliente_id,
            atendimento_id=body.atendimento_id, storage=storage,
            http_client=http_client, preparar=certidoes.preparar_releitura,
            usuario_id=user.id,
        )
    for kwargs in extracoes:
        background_tasks.add_task(certidoes.executar_releitura, **kwargs)
    logger.info(
        "certidoes: card relido user_id=%s org_id=%s cliente_id=%s %s",
        user.id, org_id, cliente_id, contagem,
    )
    return contagem
