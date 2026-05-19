"""waha.diagnostics.* tools — connector dependency introspection.

`waha.diagnostics.connection_status` — the gated-capability honesty
signal (CLAUDE.md §1). Disambiguates the three states the WAHA
dashboard conflates into one error:

- not **configured** (no base_url / api_key) → 424
- configured but host **down** (unauthenticated `/ping` fails)
- host up but key **rejected** (authed `/api/sessions` → 401/403)

PURE read, never faked.
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
            root=s.root or None,
            reachable=False,
            authenticated=False,
            error=typed_error(
                api.WahaApiError(
                    "WAHA connector not configured — set WAHA_BASE_URL "
                    "and WAHA_API_KEY in mcp/waha/.env.",
                    status=424,
                )
            ),
        ).model_dump()

    base = s.base_url or ""
    # 1) Unauthenticated liveness — separates "host down" from "key bad".
    try:
        api.request_json(
            "GET", "/ping", base_url=base, api_key="",
            timeout=s.timeout_seconds, require_auth=False,
        )
        reachable = True
    except api.WahaApiError as e:
        return ConnectionStatusOutput(
            configured=True, root=s.root, reachable=False,
            authenticated=False, error=typed_error(e),
        ).model_dump()

    # 2) Authenticated probe — is the key accepted?
    try:
        data = api.request_json(
            "GET", "/api/sessions", base_url=base, api_key=s.api_key or "",
            params={"all": "true"}, timeout=s.timeout_seconds,
        )
    except api.WahaApiError as e:
        return ConnectionStatusOutput(
            configured=True, root=s.root, reachable=reachable,
            authenticated=False, error=typed_error(e),
        ).model_dump()

    return ConnectionStatusOutput(
        configured=True,
        root=s.root,
        reachable=True,
        authenticated=True,
        session_count=len(data) if isinstance(data, list) else None,
    ).model_dump()


HANDLERS = {"waha.diagnostics.connection_status": connection_status}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(
            name="waha.diagnostics.connection_status",
            description="Introspect the WAHA dependency — configured? "
            "host up (unauth /ping)? key accepted (authed /api/sessions)? "
            "READ-ONLY. Disambiguates the dashboard's conflated "
            "'not connected / wrong key'; never faked.",
            inputSchema=ConnectionStatusInput.model_json_schema(),
        ),
    ]


__all__ = ["register", "tool_descriptors", "HANDLERS"]
