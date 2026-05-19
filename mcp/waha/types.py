"""Pydantic In/Out schemas for the WAHA connector MCP tools.

One In + one Out per tool (n8n/github/vista shape). Out models keep
the raw WAHA object as a `dict`/`list` where full fidelity matters
(session/chat/message payloads) — lossy normalization would hide
state. `waha` imports as a top-level package (PyPI-`mcp`-shadow trick,
`mcp/_kit/README.md`), so `types.py` is safe here.
"""
from __future__ import annotations

from typing import Any, List, Optional

from pydantic import BaseModel, Field, model_validator

# ─── Shared write-gate field (mirrors n8n/types.py `_CONFIRM`) ───────────

_CONFIRM = Field(
    default=False,
    description=(
        "WRITE GATE — must be explicitly true. False/omitted returns a "
        "typed error (status 412) and performs NO side-effect. This is "
        "the confirm-then-execute gate for a state-changing / "
        "outward-facing action."
    ),
)

_SESSION = Field(
    None,
    description="WAHA session name. Omit ⇒ the connector default "
    "('default' unless WAHA_BASE_URL tenant overrides).",
)


def resolve_chat_id(chat_id: Optional[str], phone: Optional[str]) -> str:
    """WAHA chatId: a full id (`5511...@c.us` / `...@g.us`) or a bare
    phone (digits) → `<digits>@c.us`. Raises ValueError if neither given
    (surfaced as a 422 by the Pydantic layer / typed error)."""
    if chat_id:
        return chat_id
    if phone:
        digits = "".join(ch for ch in phone if ch.isdigit())
        if digits:
            return f"{digits}@c.us"
    raise ValueError("provide chat_id (full WAHA id) or phone (digits)")


# ─── waha.session.list / get / me ────────────────────────────────────────


class SessionListInput(BaseModel):
    """List sessions. PURE read."""

    all: bool = Field(
        True, description="Include stopped sessions (WAHA `all=true`)."
    )


class SessionListOutput(BaseModel):
    sessions: List[dict] = Field(default_factory=list)
    error: Optional[dict] = None


class SessionGetInput(BaseModel):
    """Inspect one session (status: WORKING/STARTING/SCAN_QR_CODE/
    STOPPED/FAILED). PURE read."""

    session: Optional[str] = _SESSION


class SessionGetOutput(BaseModel):
    session: Optional[dict] = None
    status: Optional[str] = None
    error: Optional[dict] = None


class SessionMeInput(BaseModel):
    """The connected WhatsApp account for a session. PURE read."""

    session: Optional[str] = _SESSION


class SessionMeOutput(BaseModel):
    me: Optional[dict] = None
    error: Optional[dict] = None


# ─── waha.session.start / stop / restart / logout (WRITE 🔒) ──────────────


class SessionStartInput(BaseModel):
    """Start a session. WRITE — confirm-gated."""

    session: Optional[str] = _SESSION
    confirm: bool = _CONFIRM


class SessionStopInput(BaseModel):
    """Stop a session. WRITE — confirm-gated."""

    session: Optional[str] = _SESSION
    confirm: bool = _CONFIRM


class SessionRestartInput(BaseModel):
    """Restart a session (the fix for a stuck/STOPPED worker). WRITE —
    confirm-gated."""

    session: Optional[str] = _SESSION
    confirm: bool = _CONFIRM


class SessionLogoutInput(BaseModel):
    """Log the session out of WhatsApp. WRITE / HARD-TO-REVERSE
    (drops the WhatsApp pairing — re-pair needs a QR scan) —
    confirm-gated."""

    session: Optional[str] = _SESSION
    confirm: bool = _CONFIRM


class SessionActionOutput(BaseModel):
    session: Optional[str] = None
    ok: bool = False
    status: Optional[str] = None
    result: Optional[Any] = None
    error: Optional[dict] = None


# ─── waha.message.send_text (WRITE 🔒 — OUTWARD-FACING) ───────────────────


class SendTextInput(BaseModel):
    """Send a WhatsApp text message. WRITE / OUTWARD-FACING — the
    strongest confirm gate (a real message leaves the system; it cannot
    be unsent). Provide `chat_id` (full WAHA id) OR `phone` (digits)."""

    text: str = Field(..., min_length=1, description="Message body.")
    chat_id: Optional[str] = Field(
        None, description="Full WAHA chatId (`5511...@c.us` / `...@g.us`)."
    )
    phone: Optional[str] = Field(
        None, description="Bare phone (digits) → `<digits>@c.us`."
    )
    session: Optional[str] = _SESSION
    confirm: bool = _CONFIRM

    @model_validator(mode="after")
    def _need_target(self):
        if not self.chat_id and not self.phone:
            raise ValueError("provide chat_id or phone")
        return self


class SendTextOutput(BaseModel):
    sent: bool = False
    message_id: Optional[str] = None
    result: Optional[Any] = None
    error: Optional[dict] = None


# ─── waha.chat.list / waha.message.list ──────────────────────────────────


class ChatListInput(BaseModel):
    """List chats for a session. PURE read."""

    session: Optional[str] = _SESSION
    limit: int = Field(50, ge=1, le=500, description="Max chats.")


class ChatListOutput(BaseModel):
    chats: List[dict] = Field(default_factory=list)
    error: Optional[dict] = None


class MessageListInput(BaseModel):
    """List recent messages in a chat. PURE read. Provide `chat_id` OR
    `phone`."""

    chat_id: Optional[str] = Field(None, description="Full WAHA chatId.")
    phone: Optional[str] = Field(None, description="Bare phone (digits).")
    session: Optional[str] = _SESSION
    limit: int = Field(50, ge=1, le=500, description="Max messages.")

    @model_validator(mode="after")
    def _need_target(self):
        if not self.chat_id and not self.phone:
            raise ValueError("provide chat_id or phone")
        return self


class MessageListOutput(BaseModel):
    messages: List[dict] = Field(default_factory=list)
    error: Optional[dict] = None


# ─── waha.server.version / status / ping ─────────────────────────────────


class ServerVersionInput(BaseModel):
    """WAHA build/engine version. PURE read."""


class ServerVersionOutput(BaseModel):
    version: Optional[dict] = None
    error: Optional[dict] = None


class ServerStatusInput(BaseModel):
    """WAHA server status/uptime. PURE read."""


class ServerStatusOutput(BaseModel):
    status: Optional[dict] = None
    error: Optional[dict] = None


class ServerPingInput(BaseModel):
    """Unauthenticated liveness probe (`GET /ping`). PURE read — the
    "is the host even up" signal independent of the API key."""


class ServerPingOutput(BaseModel):
    pong: bool = False
    raw: Optional[Any] = None
    error: Optional[dict] = None


# ─── waha.diagnostics.connection_status ──────────────────────────────────


class ConnectionStatusInput(BaseModel):
    """Introspect the WAHA dependency. PURE read.

    Gated-capability honesty: distinguishes not-configured vs host-down
    (via unauthenticated `/ping`) vs key-rejected (authed call 401) —
    so the dashboard's conflated "not connected / wrong key" is
    disambiguated.
    """


class ConnectionStatusOutput(BaseModel):
    configured: bool = False
    root: Optional[str] = None
    reachable: Optional[bool] = None
    authenticated: Optional[bool] = None
    session_count: Optional[int] = None
    error: Optional[dict] = None


__all__ = [
    "resolve_chat_id",
    "SessionListInput",
    "SessionListOutput",
    "SessionGetInput",
    "SessionGetOutput",
    "SessionMeInput",
    "SessionMeOutput",
    "SessionStartInput",
    "SessionStopInput",
    "SessionRestartInput",
    "SessionLogoutInput",
    "SessionActionOutput",
    "SendTextInput",
    "SendTextOutput",
    "ChatListInput",
    "ChatListOutput",
    "MessageListInput",
    "MessageListOutput",
    "ServerVersionInput",
    "ServerVersionOutput",
    "ServerStatusInput",
    "ServerStatusOutput",
    "ServerPingInput",
    "ServerPingOutput",
    "ConnectionStatusInput",
    "ConnectionStatusOutput",
]
