"""WhatsApp conversation + document request/triage routes (CONTRACT §2).

`GET  /{cliente_id}/conversa`                           the card's chat (last 50)
`POST /{cliente_id}/conversa/pedir-documentos`          ask for the pending documents
`GET  /{cliente_id}/documentos/a-classificar`           triage list (WhatsApp media w/o a type)
`POST /{cliente_id}/documentos/{documento_id}/classificar`  operator picks the type; extraction runs

Own module so `card_hub/router.py` gains one include line. The send itself is
the existing connection send path (`whatsapp_connections_router.send_message`).
"""
from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.responses import JSONResponse
from noctusai_lib.api import StrictHttpModel
from noctusai_lib.primitives.exceptions import AppException
from pydantic import Field

from app.config import SocialWiringSettings
from app.dependencies import get_current_user_org
from app.modules.card_hub import conversa_service as svc
from app.modules.card_hub.auth import auth_parts
from app.modules.card_hub.deps import (
    get_card_hub_client,
    get_conflict_notification_service,
    get_cep_lookup_adapter,
    get_identity_extractor_factory,
    get_storage_backend,
)
from app.modules.card_hub.extracao import registry
from app.routers import whatsapp_connections_router as wa
from app.services import chat_cliente_link
from app.services import documento_intake_service as intake

router = APIRouter()
logger = logging.getLogger(__name__)


class PedirDocumentosBody(StrictHttpModel):
    texto: Optional[str] = Field(default=None, min_length=1, max_length=4000)


class ClassificarBody(StrictHttpModel):
    tipo_documento: str = Field(min_length=1, max_length=64)


def _sem_conversa() -> AppException:
    return AppException(
        code="sem_conversa",
        message="Este cliente não tem conversa nem telefone.",
        status_code=409,
    )


@router.get("/{cliente_id}/conversa")
async def get_conversa_route(
    cliente_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    _user, org_id = auth_parts(auth)
    return svc.conversa(client, org_id, cliente_id)


@router.post("/{cliente_id}/conversa/pedir-documentos", status_code=201)
async def pedir_documentos_route(
    cliente_id: UUID,
    body: PedirDocumentosBody,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
    store: Any = Depends(wa.get_connection_store),
    waha_factory: Any = Depends(wa.get_waha_client_factory),
    msg_store_factory: Any = Depends(wa.get_message_store_factory),
    chat_store_factory: Any = Depends(wa.get_chat_store_factory),
    settings: SocialWiringSettings = Depends(wa.get_settings),
) -> dict:
    """Ask the person, over WhatsApp, for what the checklist still lacks.

    409 `sem_conversa` when the card has no chat and no phone. With a phone but
    no chat yet, the message opens the chat on the org's newest connection.
    """
    _user, org_id = auth_parts(auth)
    cliente = svc._cliente(client, org_id, cliente_id)  # noqa: SLF001
    try:
        chat, novo_chat_id = svc.resolver_destino(client, org_id, cliente)
    except svc.SemConversa:
        raise _sem_conversa() from None

    itens = svc.itens_pendentes(client, org_id, cliente_id)
    if body.texto is None and not itens:
        raise AppException(
            code="nada_pendente",
            message="Nenhum documento pendente no checklist.",
            status_code=409,
        )
    texto = body.texto or svc.montar_texto(cliente.get("nome"), itens)

    if chat is not None:
        connection_id, chat_id = UUID(str(chat["connection_id"])), chat["chat_id"]
    else:
        conexoes = store.list_connections(org_id=org_id)
        if not conexoes:
            raise _sem_conversa()
        connection_id, chat_id = conexoes[0].id, novo_chat_id

    enviada = await wa.send_message(
        connection_id, chat_id, wa.SendMessageRequest(text=texto),
        auth=auth, store=store, waha_factory=waha_factory,
        msg_store_factory=msg_store_factory, chat_store_factory=chat_store_factory,
        settings=settings,
    )
    if isinstance(enviada, JSONResponse):  # WAHA refused: 502, nothing recorded
        raise AppException(
            code="waha_send_failed", message="Falha ao enviar pelo WhatsApp.", status_code=502
        )

    try:
        chat_cliente_link.vincular_chat(client, org_id, connection_id, chat_id)
        svc.patch_payload_da_mensagem(
            client, org_id, enviada.id,
            {"evento": svc.EVENTO_DOCUMENTOS_SOLICITADOS, "itens": itens},
        )
    except Exception:
        logger.warning("pedir-documentos: sent, but link/timeline write failed", exc_info=True)
    return {"mensagem_id": enviada.id, "itens_solicitados": itens}


@router.get("/{cliente_id}/documentos/a-classificar")
async def listar_a_classificar_route(
    cliente_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    _user, org_id = auth_parts(auth)
    svc._cliente(client, org_id, cliente_id)  # noqa: SLF001
    itens = intake.a_classificar(client, org_id, cliente_id)
    return {"items": itens, "total": len(itens)}


@router.post("/{cliente_id}/documentos/{documento_id}/classificar")
async def classificar_documento_route(
    cliente_id: UUID,
    documento_id: UUID,
    body: ClassificarBody,
    background: BackgroundTasks,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
    storage=Depends(get_storage_backend),
    extractor_factory=Depends(get_identity_extractor_factory),
    notification_service=Depends(get_conflict_notification_service),
    cep_lookup=Depends(get_cep_lookup_adapter),
) -> dict:
    """The operator names the type of a triage document; extraction then runs
    (the same background job a card upload schedules, via the registry)."""
    _user, org_id = auth_parts(auth)
    out = intake.classificar_manualmente(client, org_id, cliente_id, documento_id, body.tipo_documento)
    background.add_task(
        registry.extrair,
        body.tipo_documento, client, storage, org_id, cliente_id, documento_id,
        extractor_factory=extractor_factory,
        notification_service=notification_service,
        cep_lookup=cep_lookup,
    )
    return out
