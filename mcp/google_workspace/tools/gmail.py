"""google.gmail.* tools — thin wrappers over the seed Gmail adapter.

Tools registered:
- google.gmail.send_message   — WRITE. Required `confirm: bool` gate +
  structured audit log on the side-effect. OAuth-only (no api-key path
  for a user mailbox); requires the gmail.send scope on the real adapter.
- google.gmail.list_messages  — READ. No confirm gate.
- google.gmail.get_message    — READ. No confirm gate.

NO connector logic lives here beyond composition: the value objects,
MIME build, adapter selection (Fake vs Real) and Gmail v1 mapping all
ship in `noctusai_lib.integrations.gmail`. This module only parses the
Pydantic Input, picks Fake (no OAuth trio) vs Real (OAuth-configured)
via `make_gmail_client`, enforces the confirm-then-execute gate + emits
the audit log, and shapes the Pydantic Output.
"""
from __future__ import annotations

import logging

from mcp.server import Server
from mcp.types import Tool

from noctusai_lib.integrations.gmail import (
    GmailClient,
    OAuthGmailCredentials,
    make_gmail_client,
)

from _kit.errors import typed_error

from settings import get_settings
from schemas import (
    GetMessageInput,
    GetMessageOutput,
    GmailMessageModel,
    ListMessagesInput,
    ListMessagesOutput,
    SendMessageInput,
    SendMessageOutput,
    SendResultModel,
)

logger = logging.getLogger(__name__)
_audit = logging.getLogger("google.audit")


def _client_and_kind() -> tuple[GmailClient, str]:
    """Return (client, kind). 'real' when the OAuth trio is configured
    (the lib builds RealGmailClient), else an in-memory 'fake'. Gmail is
    OAuth-only — there is no api-key path for a user mailbox."""
    s = get_settings()
    if s.oauth_configured:
        creds = OAuthGmailCredentials(
            refresh_token=s.oauth_refresh_token,  # type: ignore[arg-type]
            client_id=s.oauth_client_id,  # type: ignore[arg-type]
            client_secret=s.oauth_client_secret,  # type: ignore[arg-type]
        )
        return make_gmail_client(oauth_credentials=creds), "real"
    return make_gmail_client(use_fake=True), "fake"


def _msg_model(m) -> GmailMessageModel:
    return GmailMessageModel(
        id=m.id,
        thread_id=m.thread_id,
        from_=m.from_,
        to=m.to,
        subject=m.subject,
        snippet=m.snippet,
        body_text=m.body_text,
        body_html=m.body_html,
        received_at=m.received_at.isoformat(),
        label_ids=list(m.label_ids),
    )


# ─── Handlers ────────────────────────────────────────────────────────────


async def send_message(args: dict) -> dict:
    inp = SendMessageInput(**args)

    if not inp.confirm:
        return SendMessageOutput(sent=None, adapter="unconfirmed").model_dump() | {
            "error": typed_error(
                PermissionError(
                    "google.gmail.send_message is a WRITE — re-call with "
                    "confirm=true to actually send the email."
                )
            )
        }

    client, kind = _client_and_kind()
    _audit.info(
        "AUDIT google.gmail.send_message adapter=%s to=%r subject=%r confirm=true",
        kind,
        inp.to,
        inp.subject,
    )
    try:
        result = await client.send_message(
            to=inp.to,
            subject=inp.subject,
            body_text=inp.body_text,
            body_html=inp.body_html,
            cc=inp.cc,
            bcc=inp.bcc,
        )
    except Exception as e:  # noqa: BLE001 — re-rendered as typed payload
        _audit.warning(
            "AUDIT google.gmail.send_message FAILED adapter=%s err=%s", kind, e
        )
        return SendMessageOutput(sent=None, adapter=kind).model_dump() | {
            "error": typed_error(e)
        }

    _audit.info(
        "AUDIT google.gmail.send_message OK adapter=%s message_id=%s",
        kind,
        result.message_id,
    )
    return SendMessageOutput(
        sent=SendResultModel(
            message_id=result.message_id, thread_id=result.thread_id
        ),
        adapter=kind,
    ).model_dump()


async def list_messages(args: dict) -> dict:
    inp = ListMessagesInput(**args)
    client, kind = _client_and_kind()
    try:
        res = await client.list_messages(
            query=inp.query, label=inp.label, page_token=inp.page_token
        )
    except Exception as e:  # noqa: BLE001
        return ListMessagesOutput(messages=[], adapter=kind).model_dump() | {
            "error": typed_error(e)
        }
    return ListMessagesOutput(
        messages=[_msg_model(m) for m in res.items],
        next_page_token=res.next_page_token,
        result_size_estimate=res.result_size_estimate,
        adapter=kind,
    ).model_dump()


async def get_message(args: dict) -> dict:
    inp = GetMessageInput(**args)
    client, kind = _client_and_kind()
    try:
        m = await client.get_message(inp.message_id)
    except Exception as e:  # noqa: BLE001
        return GetMessageOutput(message=None, adapter=kind).model_dump() | {
            "error": typed_error(e)
        }
    return GetMessageOutput(
        message=_msg_model(m) if m is not None else None, adapter=kind
    ).model_dump()


# ─── Registration ───────────────────────────────────────────────────────


HANDLERS = {
    "google.gmail.send_message": send_message,
    "google.gmail.list_messages": list_messages,
    "google.gmail.get_message": get_message,
}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(
            name="google.gmail.send_message",
            description=(
                "Send an email from the connected Gmail mailbox. WRITE "
                "side-effect — you MUST pass confirm=true or the call is "
                "refused with a typed error and nothing is sent. OAuth-only "
                "(requires the gmail.send scope); falls back to an in-memory "
                "Fake when the OAuth trio is unconfigured. The `adapter` "
                "field tells you which ran."
            ),
            inputSchema=SendMessageInput.model_json_schema(),
        ),
        Tool(
            name="google.gmail.list_messages",
            description=(
                "List messages in the connected mailbox (Gmail search "
                "syntax via `query`). Read-only — no confirm gate. Each hit "
                "is hydrated to a full message. Fake adapter when OAuth is "
                "unconfigured."
            ),
            inputSchema=ListMessagesInput.model_json_schema(),
        ),
        Tool(
            name="google.gmail.get_message",
            description=(
                "Fetch one message by id, fully hydrated. Read-only. "
                "Returns message=null when missing/deleted."
            ),
            inputSchema=GetMessageInput.model_json_schema(),
        ),
    ]


__all__ = ["register", "tool_descriptors", "HANDLERS"]
