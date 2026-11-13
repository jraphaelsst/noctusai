"""Per-chat LGPD erasure for the owner's conversations (seed `WhatsAppInbox` `on_delete_chat` hook).

The seed organ erases the chat + its messages (`whatsapp_chats` / `whatsapp_messages`) AFTER this hook succeeds; a
raising hook makes the route answer 502 and erases nothing, so the owner can retry. What this hook erases is the
assistant's OWN data derived from that chat, keyed by the chat's keyed HMAC (`chat_ref`, the only identifier the intake
holds):

* the intake rows + their events, the reply events, the classifier verdicts (`ai_outputs`) and jobs -- one transaction in
  `assistant.apagar_dados_conversa` (migration 022);
* the agent's thread in the agents product, through the channel client's own `delete_conversation_data` (skipped when no
  agent is configured: nothing exists there).

LGPD: nothing here logs a body, a phone or a chat id.
"""
from __future__ import annotations

import logging
from typing import Any, Callable

import anyio.to_thread

logger = logging.getLogger(__name__)


def build_chat_eraser(
    client_factory: Callable[[], Any], identity_key: Callable[[], str], *,
    agents_factory: Callable[[], Any], agent_key: Callable[[], str],
):
    """`async (org_id, connection_id, chat_id, actor) -> None` -- the `on_delete_chat` hook."""
    from app.services.intake import chat_ref

    async def on_delete_chat(org_id, connection_id, chat_id: str, actor: str | None = None) -> None:
        ref = chat_ref(identity_key(), chat_id)

        def _purge_intake() -> int:
            resp = client_factory().rpc("apagar_dados_conversa", {
                "p_org_id": str(org_id), "p_connection_id": str(connection_id), "p_chat_ref": ref,
            }).execute()
            data = getattr(resp, "data", None)
            return int(data or 0)

        erased = await anyio.to_thread.run_sync(_purge_intake)
        agent_erased = False
        key = agent_key()
        if key:
            from noctusai_lib.integrations.agents_channel import DeletionRequest

            result = await agents_factory().delete_conversation_data(
                DeletionRequest(agent_key=key, connection_id=str(connection_id), chat_id=ref)
            )
            agent_erased = bool(getattr(result, "deleted", False))
        logger.info("chat erased connection=%s intake_rows=%s agent_thread=%s", connection_id, erased, agent_erased)

    return on_delete_chat


async def on_agent_pause(org_id, connection_id, chat, paused: bool, actor: str | None = None) -> None:
    """Record only: the organ stores `agent_paused`; the live-reply seam (`guarded_on_message`) honours it."""
    return None
