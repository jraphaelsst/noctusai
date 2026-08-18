"""`trello.diagnostics.*` tools — connector setup + a cheap live probe.

`connection_status` is the gated-capability-honesty signal (CLAUDE.md
§1): zero API calls, so an agent asking "am I set up?" never spends a
request and an unconfigured connector never produces an upstream error
that reads like an outage.

`probe` is the ONE tool in this connector allowed to spend a real
network call outside the explicit live-read/write surface — `GET
/members/me` is Trello's cheapest authenticated call, so it is the
correct thing to run to answer "does this key+token pair actually
work?" without touching any board/card data.
"""
from __future__ import annotations

from mcp.server import Server
from mcp.types import Tool

from _kit.errors import typed_error

from .. import api, client
from ..settings import get_settings
from ..types import ConnectionStatusInput, ConnectionStatusOutput, ProbeInput, ProbeOutput


async def connection_status(args: dict) -> dict:
    ConnectionStatusInput(**args)
    s = get_settings()
    next_step = None
    if not s.configured:
        next_step = (
            "set TRELLO_API_KEY and TRELLO_TOKEN in mcp/trello/.env — get a "
            "key at https://trello.com/app-key, then generate a token from "
            "the link on that same page"
        )
    return ConnectionStatusOutput(
        ok=s.configured,
        configured=s.configured,
        has_api_key=bool(s.api_key),
        has_token=bool(s.token),
        base_url=s.base_url,
        next_step=next_step,
    ).model_dump()


async def probe(args: dict) -> dict:
    ProbeInput(**args)
    s = get_settings()
    if not s.configured:
        return ProbeOutput(
            probed=False,
            error=typed_error(api.TrelloApiError(
                "Trello connector not configured — set TRELLO_API_KEY and "
                "TRELLO_TOKEN in mcp/trello/.env.",
                status=424,
            )),
        ).model_dump()
    try:
        member = client.get_client().get_me()
    except api.TrelloApiError as e:
        return ProbeOutput(probed=True, error=typed_error(e)).model_dump()
    return ProbeOutput(probed=True, member=member if isinstance(member, dict) else None).model_dump()


HANDLERS = {
    "trello.diagnostics.connection_status": connection_status,
    "trello.diagnostics.probe": probe,
}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(
            name="trello.diagnostics.connection_status",
            description="Is TRELLO_API_KEY/TRELLO_TOKEN configured? "
            "READ, ZERO API CALLS.",
            inputSchema=ConnectionStatusInput.model_json_schema(),
        ),
        Tool(
            name="trello.diagnostics.probe",
            description="GET /members/me — the cheapest authenticated call, "
            "proves the key+token pair actually works. READ, ONE LIVE API "
            "CALL (skipped, with a typed 424, when unconfigured).",
            inputSchema=ProbeInput.model_json_schema(),
        ),
    ]


__all__ = ["HANDLERS", "register", "tool_descriptors"]
