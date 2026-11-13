"""The owner's own messages reach the agent's thread: the agent must not contradict or repeat what the owner said.

When the owner answers a conversation from the app or from the phone, the live agent (hosted in `agents`) has not seen
it. agents exposes the route for exactly this -- `POST /api/channels/threads/{id}/mensagens` with `role="humano"`
(`AgentsClient.anexar_mensagem`, the same append social-wiring uses for a human attendant): an append WITHOUT a turn, so no
model runs and nothing is sent. Idempotent by the WAHA message id.

Rules:
* only the owner's own text (`from_me`, `source != "api"`): the agent's replies echo through the webhook as `source="api"`
  and are already in its thread; the app's own sends reach here from the send route (no source) and their webhook echo is a
  duplicate that never notifies;
* only a thread agents already has (a conversation the agent never served is never created from a human message);
* the author recorded is the connection's creator (the owner who paired the line) -- agents requires a user id;
* never raises, never blocks the send: the owner's message IS sent either way; a failure is logged by class only.

LGPD: nothing here logs a body, a phone or a chat id.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional
from uuid import UUID

from noctusai_lib.integrations.agents_channel import MAX_MESSAGE_CHARS, AgentsClientError

from app.services.intake import chat_ref

logger = logging.getLogger(__name__)

SOURCE_API = "api"
Forwarder = Callable[[UUID, UUID, Any, Any], Awaitable[None]]


def is_owner_text(message: Any) -> bool:
    """The owner's own typed text: from_me, not API-sourced, a text body."""
    return bool(
        message.from_me and getattr(message, "source", None) != SOURCE_API
        and (message.type or "chat") == "chat" and (message.body or "").strip()
    )


def _at(message: Any) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(message.timestamp).replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def build_human_forwarder(
    *,
    agents_factory: Callable[[], Any],
    owner_user_id: Callable[[UUID, UUID], Optional[str]],
    identity_key: Callable[[], str],
    enabled: Callable[[], bool],
) -> Forwarder:
    """`owner_user_id(org_id, connection_id)` is a blocking lookup (run in a worker thread). `agents_factory()` returns the
    `AgentsClient` (built lazily, once). `enabled()` is the live-reply switch: off => the agent has no thread to inform."""
    import anyio.to_thread

    async def forward(org_id: UUID, connection_id: UUID, chat: Any, message: Any) -> None:
        if not enabled() or not is_owner_text(message):
            return
        try:
            author = await anyio.to_thread.run_sync(lambda: owner_user_id(org_id, connection_id))
            if not author:
                logger.error("assistant: owner message not forwarded connection=%s -- no author user", connection_id)
                return
            client = agents_factory()
            ref = chat_ref(identity_key(), message.chat_id)
            info = await client.buscar_thread(connection_id=str(connection_id), chat_id=ref)
            if info is None:
                return  # the agent never served this conversation
            await client.anexar_mensagem(
                info.thread_id, role="humano", texto=message.body[:MAX_MESSAGE_CHARS],
                provider_message_id=str(message.id)[:256], at=_at(message), autor_user_id=str(author),
            )
        except AgentsClientError as exc:
            logger.error("assistant: owner message not forwarded (%s) connection=%s", type(exc).__name__, connection_id)
        except Exception as exc:  # noqa: BLE001 - never fails the webhook / the send; class only, no content
            logger.error("assistant: owner message forward failed (%s) connection=%s", type(exc).__name__, connection_id)

    return forward
