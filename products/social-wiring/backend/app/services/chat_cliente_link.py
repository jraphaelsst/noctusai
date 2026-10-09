"""The ONE rule that ties a WhatsApp chat to a card (CONTRACT §2.1).

A chat belongs to the cliente whose `chave_canonica` is the chat's phone in
E.164. The inbox used this rule only to NAME a chat (`_nomear_pelos_clientes`);
the conversation panel, "Pedir documentos" and the media intake need it STORED
(`whatsapp_chats.cliente_id`, migration 220). Both callers share this module —
there is no second copy of the matching rule.

Groups (`@g.us`) and LIDs (`@lid`) are not phone numbers: pattern-matching one
onto a cliente would put a stranger's name on a stranger's conversation.
"""
from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from app.services import table_reads

logger = logging.getLogger(__name__)

_DOMINIOS_TELEFONE = ("c.us", "s.whatsapp.net")


def telefone_do_chat(chat_id: str) -> Optional[str]:
    """The E.164 key (`+5511...`) for a chat id, or None when it is not a phone
    conversation (group, LID, malformed, wrong length)."""
    if not chat_id or "@" not in chat_id:
        return None
    local, _, dominio = chat_id.partition("@")
    if dominio not in _DOMINIOS_TELEFONE:
        return None
    digitos = "".join(c for c in local if c.isdigit())
    # Brazilian mobiles are 12-13 digits with the country code; anything much
    # shorter or longer is not a number this CRM would hold.
    if not (10 <= len(digitos) <= 15):
        return None
    return f"+{digitos}"


def chat_ids_do_telefone(chave_canonica: str) -> list[str]:
    """Both JID spellings a chat for this E.164 key can carry."""
    digitos = "".join(c for c in (chave_canonica or "") if c.isdigit())
    if not (10 <= len(digitos) <= 15):
        return []
    return [f"{digitos}@{d}" for d in _DOMINIOS_TELEFONE]


def clientes_por_chat(
    client: Any, org_id: UUID, chat_ids: list[str]
) -> dict[str, dict]:
    """`{chat_id: {id, nome, chave_canonica}}` for every phone chat that has a
    cliente. Raises on a lookup failure: callers decide whether that is fatal
    (the inbox render swallows it; a link write must not pretend it linked)."""
    por_chave: dict[str, list[str]] = {}
    for cid in chat_ids:
        chave = telefone_do_chat(cid)
        if chave:
            por_chave.setdefault(chave, []).append(cid)
    if not por_chave:
        return {}
    linhas = table_reads.in_batched_rows(
        client, "clientes", org_id, "chave_canonica", sorted(por_chave),
        select="id,nome,chave_canonica",
    )
    out: dict[str, dict] = {}
    for linha in linhas:
        for cid in por_chave.get(str(linha.get("chave_canonica") or ""), []):
            out[cid] = linha
    return out


def vincular_chat(client: Any, org_id: UUID, connection_id: Any, chat_id: str) -> Optional[str]:
    """Resolve and STORE the cliente of one chat (inbound webhook). Returns the
    cliente id or None. Never overwrites an existing link with a miss."""
    achado = clientes_por_chat(client, org_id, [chat_id]).get(chat_id)
    if not achado:
        return None
    client.table("whatsapp_chats").update({"cliente_id": str(achado["id"])}).eq(
        "org_id", str(org_id)
    ).eq("connection_id", str(connection_id)).eq("chat_id", chat_id).execute()
    return str(achado["id"])


def vincular_chats_do_cliente(
    client: Any, org_id: UUID, cliente_id: Any, chave_canonica: Optional[str]
) -> int:
    """A cliente was created / merged / re-keyed: point every chat of its phone at
    it. Returns the number of chat rows matched. Best-effort by contract of the
    callers (a failed link must not fail a merge) — they catch and log."""
    ids = chat_ids_do_telefone(chave_canonica or "")
    if not ids:
        return 0
    res = client.table("whatsapp_chats").update({"cliente_id": str(cliente_id)}).eq(
        "org_id", str(org_id)
    ).in_("chat_id", ids).execute()
    return len(res.data or [])


def reapontar_chats(client: Any, org_id: UUID, de_cliente: Any, para_cliente: Any) -> None:
    """Merge: chats of the absorbed card move to the survivor."""
    client.table("whatsapp_chats").update({"cliente_id": str(para_cliente)}).eq(
        "org_id", str(org_id)
    ).eq("cliente_id", str(de_cliente)).execute()
