"""meta.whatsapp.* tools — WAHA outbound + inbound parse.

Tools registered:
- meta.whatsapp.send_text     — OUTBOUND side-effect, confirm-gated.
- meta.whatsapp.parse_inbound — pure WAHA-payload parse, no side-effect.

Both are thin wrappers over `noctusai_lib.integrations.whatsapp` (the
seed verified to ship `get_whatsapp_client` / `build_send_text_body` /
`parse_waha_inbound_message` / `FakeWahaClient` / `WhatsAppPayloadError`
— `verify-the-seed-ships-it`). Nothing is re-implemented here.

Deferred-config rule: with no `WAHA_BASE_URL`, `get_whatsapp_client`
returns `FakeWahaClient`, so the server boots and tools still answer
deterministically; with creds it returns the real httpx-backed client.
"""
from __future__ import annotations

import logging
from typing import Any

from mcp.server import Server
from mcp.types import Tool

from _kit.errors import typed_error
from noctusai_lib.integrations.whatsapp import (
    WhatsAppPayloadError,
    chat_id_for_phone,
    get_whatsapp_client,
    parse_waha_inbound_message,
)

from ..settings import get_settings
from ..types import (
    ParseInboundInput,
    ParseInboundOutput,
    SendTextInput,
    SendTextOutput,
)

logger = logging.getLogger(__name__)


class ConfirmationRequiredError(RuntimeError):
    """Raised when an outbound tool is invoked without `confirm=true`.

    Carries `status=412` (Precondition Failed) so the connector typed-error
    envelope surfaces a deterministic, branchable code to the host LLM —
    the confirm-then-execute contract (`KB § PATTERNS/llm-bot-security.md`).
    """

    status = 412


def _client():
    s = get_settings()
    return get_whatsapp_client(
        base_url=s.waha_base_url,
        api_key=s.waha_api_key,
    )


# ─── Handlers ────────────────────────────────────────────────────────────


async def send_text(args: dict) -> dict:
    inp = SendTextInput(**args)

    if inp.confirm is not True:
        # NO side-effect performed. Confirm-then-execute gate.
        err = ConfirmationRequiredError(
            "Refusing to send: `confirm` must be true for this outbound "
            "WhatsApp action. No message was sent."
        )
        logger.info(
            "meta.whatsapp.send_text BLOCKED (unconfirmed) "
            "phone_suffix=%s text_len=%d",
            inp.phone[-4:],
            len(inp.text),
        )
        return SendTextOutput(sent=False, error=typed_error(err)).model_dump()

    chat_id = chat_id_for_phone(inp.phone)

    # Structured audit line — emitted BEFORE the side-effect so an
    # attempted-send is recorded even if the provider call then raises
    # (confirm-then-execute audit, PROJECT §7 Q2 / llm-bot-security).
    logger.info(
        "meta.whatsapp.send_text AUDIT confirmed=true chat_id=%s "
        "phone_suffix=%s text_len=%d",
        chat_id,
        inp.phone[-4:],
        len(inp.text),
    )

    client = _client()
    try:
        provider_response: dict[str, Any] = await client.send_text(
            chat_id, inp.text
        )
    except WhatsAppPayloadError as e:
        return SendTextOutput(
            sent=False, chat_id=chat_id, error=typed_error(e)
        ).model_dump()

    return SendTextOutput(
        sent=True,
        chat_id=chat_id,
        provider_response=provider_response,
    ).model_dump()


async def parse_inbound(args: dict) -> dict:
    inp = ParseInboundInput(**args)
    try:
        msg = parse_waha_inbound_message(inp.payload)
    except WhatsAppPayloadError as e:
        return ParseInboundOutput(error=typed_error(e)).model_dump()

    return ParseInboundOutput(
        provider_message_id=msg.provider_message_id,
        chat_id=msg.chat_id,
        from_phone=msg.from_phone,
        text=msg.text,
        session=msg.session,
        from_name=msg.from_name,
        media_url=msg.media.url if msg.media else None,
        media_mimetype=msg.media.mimetype if msg.media else None,
    ).model_dump()


# ─── Registration ───────────────────────────────────────────────────────


HANDLERS = {
    "meta.whatsapp.send_text": send_text,
    "meta.whatsapp.parse_inbound": parse_inbound,
}


def register(server: Server) -> dict:
    """Return this module's {tool_name: handler} map.

    The server aggregates these via `_kit.registry.build_registry`.
    """
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(
            name="meta.whatsapp.send_text",
            description=(
                "Send a WhatsApp text message via WAHA. OUTBOUND "
                "SIDE-EFFECT — you MUST pass `confirm: true` or the tool "
                "refuses and sends nothing (returns a typed error with "
                "status 412). `phone` is digits-only international format."
            ),
            inputSchema=SendTextInput.model_json_schema(),
        ),
        Tool(
            name="meta.whatsapp.parse_inbound",
            description=(
                "Parse a raw WAHA webhook payload into the normalized "
                "inbound message shape. PURE — no side-effect, no confirm "
                "needed. Use to inspect what an inbound WAHA event decodes "
                "to without running a webhook receiver."
            ),
            inputSchema=ParseInboundInput.model_json_schema(),
        ),
    ]


__all__ = ["register", "tool_descriptors", "HANDLERS"]
