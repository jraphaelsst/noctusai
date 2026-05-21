"""cloudflare.diagnostics.* tools — connector dependency introspection.

`cloudflare.diagnostics.connection_status` — the gated-capability
honesty signal (CLAUDE.md §1). Probes `GET /user/tokens/verify` (the
canonical token-validity endpoint — returns `{result:{id,status}}`) and
classifies the outcome:

- no token (not **configured**)                           → 424
- network failure / host unreachable (not **reachable**)  → 502
- token rejected (401 ∨ success:false → **authenticated** = false)
- 200 + verified                                          → ok (token_status)

Also reports `account_id_present` (the account-scoped tunnel tools need
it) so the operator can tell at a glance whether tunnel ops will work.

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

_VERIFY = "/user/tokens/verify"


async def connection_status(args: dict) -> dict:
    ConnectionStatusInput(**args)
    s = get_settings()
    if not s.configured:
        return ConnectionStatusOutput(
            configured=False,
            root=s.root or None,
            reachable=False,
            authenticated=False,
            account_id_present=bool(s.account_id),
            error=typed_error(
                api.CloudflareApiError(
                    "Cloudflare connector not configured — set "
                    "CLOUDFLARE_API_TOKEN in mcp/cloudflare/.env.",
                    status=424,
                )
            ),
        ).model_dump()

    # Single authed probe; the upstream status / envelope disambiguates.
    try:
        data = api.request_json(
            "GET", _VERIFY,
            api_token=s.api_token or "", base_url=s.base_url or "",
            timeout=s.timeout_seconds,
        )
    except api.CloudflareApiError as e:
        status = getattr(e, "status", None)
        # 401/403 (rejected) OR a 200 success:false envelope (status=200,
        # cf_code set) ⇒ reachable but the token did not verify.
        if status in (401, 403, 200):
            return ConnectionStatusOutput(
                configured=True, root=s.root, reachable=True,
                authenticated=False,
                account_id_present=bool(s.account_id),
                error=typed_error(e),
            ).model_dump()
        # 502 (network/timeout/unparseable) or other upstream ⇒ not
        # reachable; never fabricate a healthy result.
        return ConnectionStatusOutput(
            configured=True, root=s.root, reachable=False,
            authenticated=False,
            account_id_present=bool(s.account_id),
            error=typed_error(e),
        ).model_dump()

    token_status = (
        data.get("status") if isinstance(data, dict) else None
    )
    return ConnectionStatusOutput(
        configured=True,
        root=s.root,
        reachable=True,
        authenticated=True,
        token_status=token_status,
        account_id_present=bool(s.account_id),
    ).model_dump()


HANDLERS = {"cloudflare.diagnostics.connection_status": connection_status}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(
            name="cloudflare.diagnostics.connection_status",
            description="Introspect the Cloudflare dependency — configured "
            "(token present)? host reachable? token verified? READ-ONLY. "
            "Probes GET /user/tokens/verify; classifies not-configured "
            "(424) / unreachable (502) / token-rejected (401/success:false) "
            "/ ok (200, token_status); reports account_id_present (tunnel "
            "ops need it). Never faked.",
            inputSchema=ConnectionStatusInput.model_json_schema(),
        ),
    ]


__all__ = ["register", "tool_descriptors", "HANDLERS"]
