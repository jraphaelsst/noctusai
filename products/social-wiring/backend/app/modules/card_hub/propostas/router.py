"""`/api/clientes/{cliente_id}/propostas` — CONTRACT §4.2.

`include_router`'d into `card_hub/router.py` (prefix `/api/clientes` is
inherited). Auth is asserted strictly (`== 401`) in
`tests/modules/card_hub/propostas/test_auth_boundary_propostas.py`.

`aceitar` / `pos-aceite` call `propostas/aceite.py` (§4.4 orchestration, another
slice) through a lazy import; until it exists they answer 503
`aceite_indisponivel` — never a silent success.
"""
from __future__ import annotations

import importlib
from typing import Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Response

from noctusai_lib.primitives.exceptions import AppException

from app.dependencies import get_current_user_org
from app.modules.card_hub.auth import auth_parts
from app.modules.card_hub.deps import get_card_hub_client, get_storage_backend
from app.modules.card_hub.propostas import service
from app.modules.card_hub.propostas.schemas import (
    PropostaAceitarBody,
    PropostaCreateBody,
    PropostaPatchBody,
    PropostaRecusarBody,
)

router = APIRouter()

_ACEITE_MODULE = "app.modules.card_hub.propostas.aceite"


class AceiteIndisponivel(AppException):
    def __init__(self) -> None:
        super().__init__(
            code="aceite_indisponivel",
            message="O aceite de propostas ainda não está disponível neste ambiente.",
            status_code=503,
        )


def _aceite() -> Any:
    try:
        return importlib.import_module(_ACEITE_MODULE)
    except ModuleNotFoundError as exc:
        if exc.name != _ACEITE_MODULE:
            raise  # a real broken import inside aceite.py must surface
        raise AceiteIndisponivel() from exc


def _agendador(background_tasks: BackgroundTasks, client: Any, storage: Any, org_id: UUID) -> Any:
    """The post-aceite background scheduler, or None when
    `pos_aceite_service` is not present (aceite records the step as
    'módulo indisponível'). A genuinely broken import inside it still raises."""
    name = "app.modules.card_hub.pos_aceite_service"
    try:
        mod = importlib.import_module(name)
    except ModuleNotFoundError as exc:
        if exc.name != name:
            raise
        return None
    return mod.agendador_em_background(background_tasks, client, storage, org_id)


def _resultado_aceite(client: Any, org_id: UUID, resultado: dict) -> dict:
    return {
        "proposta": service.proposta_out(client, org_id, resultado["proposta_row"]),
        "contrato_id": resultado.get("contrato_id"),
        "geracao": resultado.get("geracao"),
        "pos_aceite": resultado.get("pos_aceite"),
        "passos": resultado.get("passos") or [],
    }


@router.get("/{cliente_id}/propostas")
async def listar_propostas_route(
    cliente_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> list[dict]:
    _user, org_id = auth_parts(auth)
    return service.listar(client, org_id, cliente_id)


@router.post("/{cliente_id}/propostas", status_code=201)
async def criar_proposta_route(
    cliente_id: UUID,
    body: PropostaCreateBody,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    user, org_id = auth_parts(auth)
    return service.criar(client, org_id, cliente_id, body, usuario_id=getattr(user, "id", None))


@router.get("/{cliente_id}/propostas/{proposta_id}")
async def obter_proposta_route(
    cliente_id: UUID,
    proposta_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    _user, org_id = auth_parts(auth)
    return service.obter(client, org_id, cliente_id, proposta_id)


@router.patch("/{cliente_id}/propostas/{proposta_id}")
async def atualizar_proposta_route(
    cliente_id: UUID,
    proposta_id: UUID,
    body: PropostaPatchBody,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    user, org_id = auth_parts(auth)
    return service.atualizar(
        client, org_id, cliente_id, proposta_id, body, usuario_id=getattr(user, "id", None)
    )


@router.post("/{cliente_id}/propostas/{proposta_id}/enviar")
async def enviar_proposta_route(
    cliente_id: UUID,
    proposta_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    user, org_id = auth_parts(auth)
    return service.enviar(client, org_id, cliente_id, proposta_id, usuario_id=getattr(user, "id", None))


@router.post("/{cliente_id}/propostas/{proposta_id}/recusar")
async def recusar_proposta_route(
    cliente_id: UUID,
    proposta_id: UUID,
    body: PropostaRecusarBody,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    user, org_id = auth_parts(auth)
    return service.recusar(
        client, org_id, cliente_id, proposta_id, body.motivo, usuario_id=getattr(user, "id", None)
    )


@router.post("/{cliente_id}/propostas/{proposta_id}/aceitar")
async def aceitar_proposta_route(
    cliente_id: UUID,
    proposta_id: UUID,
    body: PropostaAceitarBody,
    background_tasks: BackgroundTasks,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
    storage=Depends(get_storage_backend),
) -> dict:
    user, org_id = auth_parts(auth)
    aceite = _aceite()
    atendimento_id = service.contexto_atendimento(client, org_id, cliente_id)
    resultado = aceite.aceitar(
        client, org_id, atendimento_id, proposta_id, getattr(user, "id", None),
        agendador=_agendador(background_tasks, client, storage, org_id),
    )
    return _resultado_aceite(client, org_id, resultado)


@router.post("/{cliente_id}/propostas/{proposta_id}/pos-aceite")
async def reexecutar_pos_aceite_route(
    cliente_id: UUID,
    proposta_id: UUID,
    body: PropostaAceitarBody,
    background_tasks: BackgroundTasks,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
    storage=Depends(get_storage_backend),
) -> dict:
    user, org_id = auth_parts(auth)
    aceite = _aceite()
    atendimento_id = service.contexto_atendimento(client, org_id, cliente_id)
    # "Retomar após aceite": same shape as aceitar (passos = funil + pos_aceite).
    resultado = aceite.reexecutar_pos_aceite(
        client, org_id, atendimento_id, proposta_id, getattr(user, "id", None),
        agendador=_agendador(background_tasks, client, storage, org_id),
    )
    return _resultado_aceite(client, org_id, resultado)


@router.delete("/{cliente_id}/propostas/{proposta_id}", status_code=204)
async def excluir_proposta_route(
    cliente_id: UUID,
    proposta_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> Response:
    _user, org_id = auth_parts(auth)
    service.excluir(client, org_id, cliente_id, proposta_id)
    return Response(status_code=204)
