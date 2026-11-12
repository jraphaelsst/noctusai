"""Binds the live reply to the product: settings -> `LiveReplier`, the webhook's `on_message` seam, the boot check.

The seed ingest awaits `on_message` inside the webhook request and swallows its exceptions; an agent turn takes seconds,
so the seam only SCHEDULES the reply (a held task) and returns -- the webhook acks WAHA at once, and the reply cannot
fail the ack. The intake row + its `recebida` event were already committed by then (same transaction, `append_intake`)."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Optional
from uuid import UUID

import anyio.to_thread

from noctusai_lib.integrations.agents_channel import make_agents_client
from noctusai_lib.integrations.whatsapp import get_whatsapp_client, parse_line_policy

from app.config import settings
from app.live.numeros import numeros_do_dono
from app.live.registro import RegistroResposta
from app.live.resposta import LiveReplier, ReplyConfig

logger = logging.getLogger(__name__)


class LiveReplyConfigError(RuntimeError):
    """The live reply is switched on but the deploy cannot run it: refuse to boot instead of half-answering."""


def assert_live_reply_config(s: Any = settings) -> None:
    """No-op while `ASSISTANT_REPLY_ENABLED` is off. When on: every piece the path needs must be present, and the line
    must be declared `send: enabled` (a disabled / undeclared line would refuse every send at runtime)."""
    if not s.assistant_reply_enabled:
        return
    needed = {
        "ASSISTANT_AGENT_KEY": s.assistant_agent_key,
        "ASSISTANT_AGENTS_BASE_URL": s.assistant_agents_base_url,
        "ASSISTANT_AGENTS_TOKEN": s.assistant_agents_token,
        "ASSISTANT_WAHA_BASE_URL": s.assistant_waha_base_url,
        "ASSISTANT_WAHA_LINE_POLICY": s.assistant_waha_line_policy,
        "ASSISTANT_IDENTITY_HMAC_KEY": s.assistant_identity_hmac_key,
        "ENCRYPTION_KEY": s.encryption_key,
    }
    missing = [k for k, v in needed.items() if not v]
    if missing:
        raise LiveReplyConfigError(f"ASSISTANT_REPLY_ENABLED is on but these are not set: {', '.join(missing)}")
    if not parse_line_policy(s.assistant_waha_line_policy).send_enabled:
        raise LiveReplyConfigError("ASSISTANT_REPLY_ENABLED is on but the WAHA line policy is not `send: enabled`")


def build_replier(connection_store_factory: Callable[[], Any], admin_client_factory: Callable[[], Any]) -> LiveReplier:
    async def waha_for(org_id: UUID, connection_id: UUID):
        rec = await anyio.to_thread.run_sync(
            lambda: connection_store_factory().get_connection(connection_id=connection_id, org_id=org_id, decrypt=True)
        )
        if rec is None or not rec.app_enabled:
            raise LookupError("connection unavailable")
        return get_whatsapp_client(base_url=rec.base_url or None, api_key=rec.api_key, session=rec.session_name)

    return LiveReplier(
        # allow_fake=False: a missing token/url means NO reply (declared refusal), never a scripted fake.
        agents=make_agents_client(
            token=settings.assistant_agents_token, base_url=settings.assistant_agents_base_url, allow_fake=False,
        ),
        waha_for=waha_for,
        registro=RegistroResposta(admin_client_factory),
        config=ReplyConfig(
            enabled=settings.assistant_reply_enabled, agent_key=settings.assistant_agent_key,
            max_age_s=settings.assistant_reply_max_age_seconds,
            paragraph_delay_s=settings.assistant_reply_paragraph_delay_seconds,
            debounce_s=settings.assistant_reply_debounce_seconds,
            owner_numbers=numeros_do_dono(settings.assistant_owner_numbers),
        ),
        identity_key=lambda: settings.assistant_identity_hmac_key,
    )


_tasks: set[asyncio.Task] = set()


def build_on_message(replier_factory: Callable[[], LiveReplier]):
    """The webhook's `on_message(org_id, connection_id, chat, message)` seam. Schedules; never awaits the turn."""
    holder: list[LiveReplier] = []  # ONE replier per process: the debounce buffers live in it

    async def on_message(org_id: UUID, connection_id: UUID, chat: Any, message: Any) -> None:
        if not settings.assistant_reply_enabled or message.from_me:
            return
        if not holder:
            holder.append(replier_factory())
        task = asyncio.ensure_future(holder[0].responder(org_id, connection_id, message))
        _tasks.add(task)
        task.add_done_callback(_tasks.discard)

    return on_message


async def drain() -> None:
    """Wait for the in-flight replies (graceful shutdown, tests)."""
    if _tasks:
        await asyncio.gather(*list(_tasks), return_exceptions=True)
