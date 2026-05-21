"""hostinger.diagnostics.* tools — connector dependency introspection.

`hostinger.diagnostics.connection_status` — the gated-capability honesty
signal (CLAUDE.md §1). Hostinger is a single public API behind
Cloudflare (no separate unauthenticated liveness endpoint like WAHA's
`/ping`), so the diagnostic attempts the authed `GET virtual-machines`
and classifies the outcome:

- no token (not **configured**)                          → 424
- network failure / host unreachable (not **reachable**) → 502
- token rejected (**authenticated** = false)             → 401/403
- 200                                                     → ok (vm_count)

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

_VPS_BASE = "/api/vps/v1/virtual-machines"


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
                api.HostingerApiError(
                    "Hostinger connector not configured — set "
                    "HOSTINGER_API_TOKEN in mcp/hostinger/.env.",
                    status=424,
                )
            ),
        ).model_dump()

    # Single authed probe; the upstream status disambiguates the states.
    try:
        data = api.request_json(
            "GET", _VPS_BASE,
            api_token=s.api_token or "", base_url=s.base_url or "",
            timeout=s.timeout_seconds,
        )
    except api.HostingerApiError as e:
        status = getattr(e, "status", None)
        if status in (401, 403):
            # Host answered but rejected the token (reachable, not authed).
            # Note: 403 may also be a Cloudflare WAF block — the typed
            # message body carries the upstream detail to disambiguate.
            return ConnectionStatusOutput(
                configured=True, root=s.root, reachable=True,
                authenticated=False, error=typed_error(e),
            ).model_dump()
        # 502 (network/timeout/unparseable) or other upstream 5xx/4xx ⇒
        # treat as not reachable; never fabricate a healthy result.
        return ConnectionStatusOutput(
            configured=True, root=s.root, reachable=False,
            authenticated=False, error=typed_error(e),
        ).model_dump()

    return ConnectionStatusOutput(
        configured=True,
        root=s.root,
        reachable=True,
        authenticated=True,
        vm_count=len(data) if isinstance(data, list) else None,
    ).model_dump()


HANDLERS = {"hostinger.diagnostics.connection_status": connection_status}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(
            name="hostinger.diagnostics.connection_status",
            description="Introspect the Hostinger dependency — configured "
            "(token present)? host reachable? token accepted? READ-ONLY. "
            "Classifies not-configured (424) / unreachable (502) / "
            "token-rejected (401/403) / ok (200); never faked.",
            inputSchema=ConnectionStatusInput.model_json_schema(),
        ),
    ]


__all__ = ["register", "tool_descriptors", "HANDLERS"]
