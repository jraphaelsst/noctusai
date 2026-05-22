"""supabase.diagnostics.* tools — connector dependency introspection.

`supabase.diagnostics.connection_status` — the gated-capability honesty
signal (CLAUDE.md §1). Probes `GET /v1/projects` (the cheapest authed
read) and classifies the outcome:

- no token (not **configured**)                           → 424
- network failure / host unreachable (not **reachable**)  → 502
- token rejected (401 ∨ 403 → **authenticated** = false)
- 2xx                                                      → ok (authenticated)

Also reports `project_ref_present` (the project-scoped tools default to
it) so the operator can tell at a glance whether project-scoped ops will
work without an explicit ref.

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

_PROBE = "/v1/projects"


async def connection_status(args: dict) -> dict:
    ConnectionStatusInput(**args)
    s = get_settings()
    if not s.configured:
        return ConnectionStatusOutput(
            configured=False,
            root=s.root or None,
            reachable=False,
            authenticated=False,
            project_ref_present=bool(s.project_ref),
            error=typed_error(
                api.SupabaseApiError(
                    "Supabase connector not configured — set "
                    "SUPABASE_ACCESS_TOKEN in mcp/supabase/.env.",
                    status=424,
                )
            ),
        ).model_dump()

    # Single authed probe; the upstream status disambiguates.
    try:
        api.request_json(
            "GET", _PROBE,
            access_token=s.access_token or "", base_url=s.base_url or "",
            timeout=s.timeout_seconds,
        )
    except api.SupabaseApiError as e:
        status = getattr(e, "status", None)
        # 401/403 (rejected) ⇒ reachable but the token did not authenticate.
        if status in (401, 403):
            return ConnectionStatusOutput(
                configured=True, root=s.root, reachable=True,
                authenticated=False,
                project_ref_present=bool(s.project_ref),
                error=typed_error(e),
            ).model_dump()
        # 502 (network/timeout/unparseable) or other upstream ⇒ not
        # reachable; never fabricate a healthy result.
        return ConnectionStatusOutput(
            configured=True, root=s.root, reachable=False,
            authenticated=False,
            project_ref_present=bool(s.project_ref),
            error=typed_error(e),
        ).model_dump()

    return ConnectionStatusOutput(
        configured=True,
        root=s.root,
        reachable=True,
        authenticated=True,
        project_ref_present=bool(s.project_ref),
    ).model_dump()


HANDLERS = {"supabase.diagnostics.connection_status": connection_status}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(
            name="supabase.diagnostics.connection_status",
            description="Introspect the Supabase dependency — configured "
            "(token present)? host reachable? token authenticated? "
            "READ-ONLY. Probes GET /v1/projects; classifies not-configured "
            "(424) / unreachable (502) / token-rejected (401/403) / ok "
            "(2xx); reports project_ref_present. Never faked.",
            inputSchema=ConnectionStatusInput.model_json_schema(),
        ),
    ]


__all__ = ["register", "tool_descriptors", "HANDLERS"]
