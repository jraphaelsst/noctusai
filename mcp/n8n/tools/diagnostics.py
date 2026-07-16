"""n8n.diagnostics.* tools — connector dependency introspection.

`n8n.diagnostics.connection_status` — the gated-capability honesty
signal (CLAUDE.md §1). Surfaces whether the connector is configured
(base_url + api_key) AND the instance is reachable/authenticated, so a
"succeeds-empty" read isn't silently misread as "no data" when the key
is wrong or the host is down. PURE read, never faked.

**Reachability+count decision.** The combined probe is
`client.list_workflows(include_archived=True)` — ONE call, not a
separate `client.ping()` plus a second count round-trip. The seed's
`list_workflows` already follows `nextCursor` internally
(`HttpxN8nClient._list_all_workflows_raw`), so `len(workflows)` is the
TRUE total for free — the exact regression this tool used to guard by
hand-rolling its own cursor loop (`workflow_count` was NOT `min(total,
1)`, the old `limit=1` bug). Reusing the seed's pagination collapses
~35 lines of connector-side cursor-follow that would otherwise be a
second, drifting copy of `HttpxN8nClient._list_all_workflows_raw`.
"""
from __future__ import annotations

import logging

from mcp.server import Server
from mcp.types import Tool

from _kit.errors import typed_error
from noctusai_lib.integrations.n8n import N8nError

from .. import api
from ..client import get_client
from ..settings import get_settings
from ..types import ConnectionStatusInput, ConnectionStatusOutput

logger = logging.getLogger(__name__)


async def connection_status(args: dict) -> dict:
    ConnectionStatusInput(**args)
    s = get_settings()
    if not s.configured:
        return ConnectionStatusOutput(
            configured=False,
            api_root=s.api_root or None,
            reachable=False,
            error=typed_error(
                api.N8nApiError(
                    "n8n connector not configured — set N8N_BASE_URL and "
                    "N8N_API_KEY in mcp/n8n/.env.",
                    status=424,
                )
            ),
        ).model_dump()

    # Authenticated probe + true total in one call — see module docstring.
    try:
        client = get_client()
        workflows = await client.list_workflows(include_archived=True)
    except (api.N8nApiError, N8nError) as e:
        return ConnectionStatusOutput(
            configured=True,
            api_root=s.api_root,
            reachable=False,
            error=typed_error(api.map_seed_error(e)),
        ).model_dump()
    return ConnectionStatusOutput(
        configured=True,
        api_root=s.api_root,
        reachable=True,
        workflow_count=len(workflows),
    ).model_dump()


HANDLERS = {"n8n.diagnostics.connection_status": connection_status}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(
            name="n8n.diagnostics.connection_status",
            description="Introspect the n8n dependency — configured? "
            "instance reachable? key accepted? READ-ONLY. The "
            "gated-capability honesty signal: a wrong key / down host is "
            "reported reachable=false, never faked.",
            inputSchema=ConnectionStatusInput.model_json_schema(),
        ),
    ]


__all__ = ["register", "tool_descriptors", "HANDLERS"]
