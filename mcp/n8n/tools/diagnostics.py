"""n8n.diagnostics.* tools — connector dependency introspection.

`n8n.diagnostics.connection_status` — the gated-capability honesty
signal (CLAUDE.md §1). Surfaces whether the connector is configured
(base_url + api_key) AND the instance is reachable/authenticated, so a
"succeeds-empty" read isn't silently misread as "no data" when the key
is wrong or the host is down. PURE read, never faked.
"""
from __future__ import annotations

import logging

from mcp.server import Server
from mcp.types import Tool

from _kit.errors import typed_error

from .. import api
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

    # Authenticated probe. The FIRST page doubles as the never-faked
    # "configured but key rejected" signal (a 401/403 here). We then
    # follow `nextCursor` to a bounded depth so `workflow_count` is the
    # TRUE total — not `min(total, 1)`, the old `limit=1` bug that made
    # a 10-workflow instance report `workflow_count=1`.
    count = 0
    cursor: str | None = None
    pages = 0
    MAX_PAGES = 50  # 50 * 250 = 12500 workflows — unbounded in practice
    while True:
        params: dict = {"limit": 250}
        if cursor:
            params["cursor"] = cursor
        try:
            data = api.request_json(
                "GET",
                "/workflows",
                params=params,
                base_url=s.base_url or "",
                api_key=s.api_key or "",
                timeout=s.timeout_seconds,
            )
        except api.N8nApiError as e:
            return ConnectionStatusOutput(
                configured=True,
                api_root=s.api_root,
                reachable=False,
                error=typed_error(e),
            ).model_dump()
        if not (isinstance(data, dict) and isinstance(data.get("data"), list)):
            # Reachable + authenticated, but an unexpected body shape —
            # honest: don't fabricate a count we couldn't measure.
            return ConnectionStatusOutput(
                configured=True,
                api_root=s.api_root,
                reachable=True,
                workflow_count=None,
            ).model_dump()
        count += len(data["data"])
        cursor = data.get("nextCursor")
        pages += 1
        if not cursor or pages >= MAX_PAGES:
            break
    return ConnectionStatusOutput(
        configured=True,
        api_root=s.api_root,
        reachable=True,
        workflow_count=count,
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
