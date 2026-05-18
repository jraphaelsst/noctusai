"""Pydantic In/Out schemas for the Meta connector MCP tools.

One In + one Out model per tool (vista's `types.py` shape). Out models
are JSON-friendly mirrors of the seed value objects the tool wraps —
the tool never leaks a raw seed dataclass; it maps into these.

Only the SHIPPED WhatsApp slice has schemas here. The Facebook /
Instagram / diagnostics schemas are deliberately absent — their backing
seed package (`noctusai_lib.integrations.meta`) does not exist; see
`mcp/meta/README.md`.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


# ─── meta.whatsapp.send_text ─────────────────────────────────────────────


class SendTextInput(BaseModel):
    """Send a WhatsApp text message via WAHA.

    OUTBOUND SIDE-EFFECT. `confirm` MUST be `True` or the handler returns
    a typed error WITHOUT sending (confirm-then-execute, `KB §
    PATTERNS/llm-bot-security.md`). The host LLM must set it explicitly.
    """

    phone: str = Field(
        ...,
        description="Recipient phone in international format, digits only "
        "(e.g. '5511999998888'). Converted to a WAHA chat_id internally.",
    )
    text: str = Field(..., min_length=1, description="Message body to send.")
    confirm: bool = Field(
        False,
        description="MUST be true to actually send. When false/omitted the "
        "tool returns a typed error and performs NO side-effect — this is "
        "the confirm-then-execute gate for an outbound action.",
    )


class SendTextOutput(BaseModel):
    sent: bool
    chat_id: Optional[str] = None
    provider_response: Optional[dict] = None
    error: Optional[dict] = None


# ─── meta.whatsapp.parse_inbound ─────────────────────────────────────────


class ParseInboundInput(BaseModel):
    """Parse a raw WAHA webhook payload into the normalized inbound shape.

    PURE — no side-effect, no confirm gate. Wraps the seed
    `parse_waha_inbound_message` parser so an agent can inspect what an
    inbound WAHA event would decode to without standing up a webhook.
    """

    payload: dict = Field(
        ..., description="Raw WAHA webhook JSON body (the POST the WAHA "
        "server delivers to a webhook receiver)."
    )


class ParseInboundOutput(BaseModel):
    provider_message_id: Optional[str] = None
    chat_id: Optional[str] = None
    from_phone: Optional[str] = None
    text: Optional[str] = None
    session: Optional[str] = None
    from_name: Optional[str] = None
    media_url: Optional[str] = None
    media_mimetype: Optional[str] = None
    error: Optional[dict] = None


__all__ = [
    "SendTextInput",
    "SendTextOutput",
    "ParseInboundInput",
    "ParseInboundOutput",
]
