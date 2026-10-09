"""The card's WhatsApp conversation (CONTRACT §2.1 / §2.2).

Read side (`conversa`), the "Pedir documentos" text built from the PENDING
checklist items, and the `documentos_solicitados` timeline event. Sending goes
through the existing connection send path (`whatsapp_connections_router.
send_message`) -- this module only decides WHAT to say and WHERE.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional
from uuid import UUID

from noctusai_lib.primitives.exceptions import NotFoundError

from app.modules.card_hub import documento_checklist_service as checklist_svc
from app.services import chat_cliente_link

logger = logging.getLogger(__name__)

LIMITE_MENSAGENS = 50
EVENTO_DOCUMENTOS_SOLICITADOS = "documentos_solicitados"

#: Checklist items the CLIENT cannot hand over (an internal consulta).
_ITENS_NAO_PEDIDOS = frozenset({"serasa_crednet"})


class SemConversa(Exception):
    """The cliente has no chat and no phone to start one (-> 409 sem_conversa)."""


def _tabela(client: Any, nome: str):
    return client.table(nome)


def _cliente(client: Any, org_id: UUID, cliente_id: UUID) -> dict:
    rows = (
        _tabela(client, "clientes")
        .select("id,nome,chave_canonica,chave_tipo,celular")
        .eq("org_id", str(org_id)).eq("id", str(cliente_id)).limit(1).execute()
    ).data or []
    if not rows:
        raise NotFoundError("clientes", str(cliente_id))
    return rows[0]


def chat_do_cliente(client: Any, org_id: UUID, cliente_id: UUID) -> Optional[dict]:
    """The most recently active chat linked to this card, or None."""
    rows = (
        _tabela(client, "whatsapp_chats")
        .select("connection_id,chat_id,last_message_at")
        .eq("org_id", str(org_id)).eq("cliente_id", str(cliente_id)).execute()
    ).data or []
    if not rows:
        return None
    rows.sort(key=lambda r: str(r.get("last_message_at") or ""), reverse=True)
    return rows[0]


def chat_ids_do_cliente(client: Any, org_id: UUID, cliente_id: UUID) -> list[str]:
    rows = (
        _tabela(client, "whatsapp_chats").select("chat_id")
        .eq("org_id", str(org_id)).eq("cliente_id", str(cliente_id)).execute()
    ).data or []
    return [r["chat_id"] for r in rows if r.get("chat_id")]


def _payload(row: dict) -> dict:
    sp = row.get("structured_payload")
    if isinstance(sp, str):
        try:
            sp = json.loads(sp)
        except ValueError:
            return {}
    return sp if isinstance(sp, dict) else {}


def _mensagem(row: dict) -> dict:
    anexo = _payload(row).get("anexo")
    return {
        "id": str(row["id"]),
        "direcao": "in" if row.get("direction") == "inbound" else "out",
        "texto": row.get("body") or "",
        "enviada_em": row.get("created_at"),
        "anexo": (
            {
                "mime": anexo.get("mime"),
                "nome": anexo.get("nome"),
                "documento_id": anexo.get("documento_id"),
            }
            if isinstance(anexo, dict)
            else None
        ),
    }


def conversa(client: Any, org_id: UUID, cliente_id: UUID) -> dict:
    """`{chat_id|null, connection_id|null, mensagens}` -- last 50, oldest first."""
    _cliente(client, org_id, cliente_id)
    chat = chat_do_cliente(client, org_id, cliente_id)
    if chat is None:
        return {"chat_id": None, "connection_id": None, "mensagens": []}
    rows = (
        _tabela(client, "conversation_messages").select("*")
        .eq("org_id", str(org_id)).eq("chat_id", chat["chat_id"])
        .order("created_at", desc=True).limit(LIMITE_MENSAGENS).execute()
    ).data or []
    rows.sort(key=lambda r: str(r.get("created_at") or ""))
    return {
        "chat_id": chat["chat_id"],
        "connection_id": str(chat["connection_id"]) if chat.get("connection_id") else None,
        "mensagens": [_mensagem(r) for r in rows],
    }


def patch_payload_da_mensagem(
    client: Any, org_id: UUID, mensagem_id: Any, patch: dict
) -> None:
    """Merge `patch` into one message's structured_payload (same JSON-string
    encoding `MessageStore.record` writes)."""
    rows = (
        _tabela(client, "conversation_messages").select("id,structured_payload")
        .eq("org_id", str(org_id)).eq("id", str(mensagem_id)).limit(1).execute()
    ).data or []
    if not rows:
        return
    novo = {**_payload(rows[0]), **patch}
    _tabela(client, "conversation_messages").update(
        {"structured_payload": json.dumps(novo, separators=(",", ":"))}
    ).eq("org_id", str(org_id)).eq("id", str(mensagem_id)).execute()


# ─── Pedir documentos ────────────────────────────────────────────────────


def _rotulo_do_pedido(item: dict) -> str:
    """What to call the item when ASKING a person (not the operator-facing label)."""
    slots = item.get("documentos")
    if slots:
        nomes = [checklist_svc._IDENTIDADE_ROTULOS.get(d, d) for d in slots]  # noqa: SLF001
        return " ou ".join(nomes)
    return item["label"]


def itens_pendentes(client: Any, org_id: UUID, cliente_id: UUID) -> list[str]:
    """Labels of the document-backed checklist items still open."""
    definicoes = {
        i["key"]: i for i in checklist_svc.ITENS
        if ("documento" in i or "documentos" in i) and i["key"] not in _ITENS_NAO_PEDIDOS
    }
    out: list[str] = []
    for item in checklist_svc.listar(client, org_id, cliente_id)["items"]:
        definicao = definicoes.get(item["key"])
        if definicao is not None and not item["concluido"]:
            out.append(_rotulo_do_pedido(definicao))
    return out


def montar_texto(nome: Optional[str], itens: list[str]) -> str:
    primeiro = (nome or "").strip().split(" ")[0].title()
    saudacao = f"Olá {primeiro}" if primeiro else "Olá"
    return f"{saudacao}, para seguirmos precisamos de: {', '.join(itens)}. Pode enviar por aqui mesmo (foto ou PDF)."


def resolver_destino(client: Any, org_id: UUID, cliente: dict) -> tuple[Optional[dict], Optional[str]]:
    """`(chat_existente, chat_id_a_criar)`. Raises `SemConversa` with neither."""
    chat = chat_do_cliente(client, org_id, UUID(str(cliente["id"])))
    if chat is not None:
        return chat, None
    digitos = "".join(
        c for c in (
            cliente.get("chave_canonica") if cliente.get("chave_tipo") == "telefone"
            else cliente.get("celular")
        ) or "" if c.isdigit()
    )
    if len(digitos) in (10, 11):  # national number without the country code
        digitos = "55" + digitos
    ids = chat_cliente_link.chat_ids_do_telefone("+" + digitos) if digitos else []
    if not ids:
        raise SemConversa()
    return None, ids[0]


# ─── Timeline ────────────────────────────────────────────────────────────


def eventos_documentos_solicitados(client: Any, org_id: UUID, cliente_id: UUID) -> list[dict]:
    """Timeline `sistema` events for every "Pedir documentos" sent to this card."""
    ids = chat_ids_do_cliente(client, org_id, cliente_id)
    if not ids:
        return []
    rows = (
        _tabela(client, "conversation_messages").select("id,created_at,structured_payload")
        .eq("org_id", str(org_id)).eq("direction", "outbound").in_("chat_id", ids)
        .order("created_at", desc=True).limit(200).execute()
    ).data or []
    eventos = []
    for row in rows:
        sp = _payload(row)
        if sp.get("evento") != EVENTO_DOCUMENTOS_SOLICITADOS:
            continue
        eventos.append(
            {
                "id": f"sistema-docs-solicitados-{row['id']}",
                "kind": "sistema",
                "ocorrido_em": row["created_at"],
                "ator": None,
                "payload": {
                    "evento": EVENTO_DOCUMENTOS_SOLICITADOS,
                    "detalhe": ", ".join(sp.get("itens") or []),
                },
            }
        )
    return eventos
