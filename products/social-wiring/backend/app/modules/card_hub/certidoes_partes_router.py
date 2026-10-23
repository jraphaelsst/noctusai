"""Per-party Certidões routes — mounted under `/api/clientes` by the Wave C0
integration patch (CONTRACT §10; `card_hub/router.py` includes this `router`).

Paths (final): `GET /{cliente_id}/certidoes/partes`,
`POST /{cliente_id}/certidoes/partes/{kind}/{alvo_id}/emissao`,
`POST /{cliente_id}/certidoes/resultados/{resultado_id}/reemitir`,
`POST /{cliente_id}/certidoes/celulas`,
`POST /{cliente_id}/certidoes/reler`, and the card-scoped controls the retired
/certidoes screen used to own: `POST …/resultados/{id}/cancelar`,
`POST …/partes/{kind}/{alvo_id}/cancelar`, `POST …/partes/{kind}/{alvo_id}/
reemitir-erros`, `DELETE …/resultados/{id}` (discard a wrong emission) and
`GET …/partes/{kind}/{alvo_id}/download-zip`. Raw-dict responses, no `{"data":…}`
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
import anyio
from fastapi import APIRouter, BackgroundTasks, Depends, Response
from noctusai_lib.primitives.content_disposition import attachment_disposition
from noctusai_lib.primitives.exceptions import AppException
from noctusai_lib.integrations.storage import StorageBackend

from app.dependencies import get_current_user_org
from app.modules.card_hub import certidoes_partes_service as svc
from app.modules.card_hub.auth import auth_parts
from app.modules.card_hub.certidoes_partes_schemas import (
    CancelarBody,
    CelulaBody,
    CienciaPcenBody,
    EmissaoBody,
    ParteAcaoBody,
    ExigenciasBody,
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
def get_certidoes_partes_route(
    cliente_id: UUID,
    atendimento_id: Optional[UUID] = None,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    _user, org_id = auth_parts(auth)
    return svc.montar(client, org_id, cliente_id, atendimento_id=atendimento_id, hoje=date.today())


@router.put("/{cliente_id}/certidoes/exigencias")
def definir_exigencias_route(
    cliente_id: UUID,
    body: ExigenciasBody,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    """The deal's opt-in switches for the optional certidões (antigos
    proprietários / CRF-FGTS) — owner decision 2026-10-21."""
    _user, org_id = auth_parts(auth)
    return svc.definir_exigencias(
        client, org_id, cliente_id,
        exigir_certidoes_antigos=body.exigir_certidoes_antigos,
        exigir_crf_fgts=body.exigir_crf_fgts,
        atendimento_id=body.atendimento_id,
    )


@router.post("/{cliente_id}/certidoes/partes/{kind}/{alvo_id}/emissao", status_code=201)
def solicitar_emissao_route(
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
def reemitir_route(
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
def ciencia_pcen_route(
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
def garantir_celula_route(
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


@router.post("/{cliente_id}/certidoes/resultados/{resultado_id}/cancelar")
def cancelar_resultado_route(
    cliente_id: UUID,
    resultado_id: UUID,
    body: CancelarBody,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
    certidoes: CertidoesService = Depends(get_certidoes_service),
) -> dict:
    """Cancel ONE emission in progress (automatic consultas only)."""
    _user, org_id = auth_parts(auth)
    return svc.cancelar_emissao_do_resultado(
        client, org_id, cliente_id, str(resultado_id), cancelar=certidoes.cancelar_processamento,
    )


@router.post("/{cliente_id}/certidoes/partes/{kind}/{alvo_id}/cancelar")
def cancelar_parte_route(
    cliente_id: UUID,
    kind: str,
    alvo_id: UUID,
    body: ParteAcaoBody,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
    certidoes: CertidoesService = Depends(get_certidoes_service),
) -> dict:
    """Cancel every emission in progress of the party."""
    _user, org_id = auth_parts(auth)
    return svc.cancelar_emissao_da_parte(
        client, org_id, cliente_id, kind, alvo_id,
        atendimento_id=body.atendimento_id, cancelar=certidoes.cancelar_processamento,
    )


@router.post("/{cliente_id}/certidoes/partes/{kind}/{alvo_id}/reemitir-erros")
def reemitir_erros_route(
    cliente_id: UUID,
    kind: str,
    alvo_id: UUID,
    body: ParteAcaoBody,
    background_tasks: BackgroundTasks,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
    storage: StorageBackend = Depends(get_storage_backend),
    certidoes: CertidoesService = Depends(get_certidoes_service),
) -> dict:
    """Retry only the party's FAILED automatic cells, in place."""
    _user, org_id = auth_parts(auth)
    out = svc.reemitir_com_erro(
        client, org_id, cliente_id, kind, alvo_id,
        atendimento_id=body.atendimento_id,
        check_credentials=certidoes.check_required_credentials,
        reprocessar=certidoes.reprocessar_resultados,
    )
    for consulta_id in out["consultas"]:
        background_tasks.add_task(certidoes.processar_consulta, consulta_id, client, storage)
    if out["tem_tjsp"]:
        # `processar_consulta` only picks up `pendente`; the TJSP cells now
        # `na_fila` need their own scheduling pass (30-minute cooldown).
        certidoes.schedule_tjsp_for_org(str(org_id), client, storage)
    return out


@router.delete("/{cliente_id}/certidoes/resultados/{resultado_id}")
def descartar_emissao_route(
    cliente_id: UUID,
    resultado_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
    certidoes: CertidoesService = Depends(get_certidoes_service),
) -> dict:
    """Discard a wrong emission (soft-delete) — the previous evidence wins again."""
    user, org_id = auth_parts(auth)
    return svc.descartar_emissao(
        client, org_id, cliente_id, str(resultado_id),
        user_id=user.id, descartar=certidoes.soft_delete_resultado,
    )


@router.get("/{cliente_id}/certidoes/partes/{kind}/{alvo_id}/download-zip")
async def baixar_zip_da_parte_route(
    cliente_id: UUID,
    kind: str,
    alvo_id: UUID,
    atendimento_id: Optional[UUID] = None,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
    storage: StorageBackend = Depends(get_storage_backend),
    certidoes: CertidoesService = Depends(get_certidoes_service),
):
    """Every certidão PDF currently on the party's grid, as one ZIP."""
    _user, org_id = auth_parts(auth)
    parte, items = await anyio.to_thread.run_sync(
        lambda: svc.arquivos_da_parte(
            client, org_id, cliente_id, kind, alvo_id, atendimento_id=atendimento_id,
        )
    )
    if not items:
        raise AppException(
            code="SEM_ARQUIVOS", message="Nenhuma certidão com PDF para baixar.", status_code=404,
        )
    async with httpx.AsyncClient() as http_client:
        conteudo = await certidoes.montar_zip(
            items, storage, http_client,
            read=certidoes.read_certidao_bytes, contexto=f"parte {parte['nome']}",
        )
    if conteudo is None:
        raise AppException(
            code="ARQUIVOS_INDISPONIVEIS",
            message="Não foi possível baixar os arquivos das certidões.", status_code=502,
        )
    nome = (parte["nome"] or "parte").replace(" ", "_")[:50]
    return Response(
        content=conteudo,
        media_type="application/zip",
        headers={"Content-Disposition": attachment_disposition(f"certidoes_{nome}_{parte['documento'] or ''}.zip")},
    )
