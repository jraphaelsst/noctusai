"""The two seams between the WhatsApp inbox organ and the leads organ.

* `on_new_chat` -- the inbox fires it exactly ONCE per chat first created by an inbound message to a non-group
  number; every such number becomes a lead (stage `lead`, origin `whatsapp`). Deleting that lead does NOT bring it
  back: the chat row persists, and the claim that fires `on_new_chat` is never re-won. That is intended -- Monica
  deletes numbers that are not leads.
* `on_message` -- every newly stored message, inbound AND outbound, refreshes the lead card's preview.
  A chat without a lead (deleted, or a group) is left alone: `touch_last_message` never recreates one.

Both build the leads service per call over the schema-pinned admin client (the same store the `/api/leads` router
uses), so a test patch of the database reaches them.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from noctusai_lib.domain.leads import LeadsService, build_leads_store

from app.crm import LEADS_CONFIG
from app.dependencies import get_admin_client

#: preview of a message that carries no text (image, audio, ...)
MEDIA_PREVIEW = "[mídia]"


def leads_service() -> LeadsService:
    return LeadsService(build_leads_store(get_admin_client(), table=LEADS_CONFIG.table), LEADS_CONFIG)


async def on_new_chat(org_id: UUID, connection_id: UUID, chat: Any) -> None:
    await leads_service().upsert_from_whatsapp(org_id, connection_id, chat)


async def on_message(org_id: UUID, connection_id: UUID, chat: Any, message: Any) -> None:
    preview = (getattr(message, "body", "") or "").strip() or MEDIA_PREVIEW
    await leads_service().touch_last_message(
        org_id, connection_id, chat.chat_id, preview=preview, at=getattr(message, "timestamp", None)
    )
