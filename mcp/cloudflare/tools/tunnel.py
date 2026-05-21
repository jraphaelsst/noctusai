"""cloudflare.tunnel.* tools — Cloudflare Tunnel (cfd_tunnel) ops.

Account-scoped (`/accounts/{account_id}/cfd_tunnel`) — every tool needs
the connector's CLOUDFLARE_ACCOUNT_ID; missing it is a typed never-faked
424 (we never build a malformed path).

Reads (no gate): list / get / get_config.
Writes (confirm-gated): create / delete / update_config. `delete` is the
STRONGEST gate — IRREVERSIBLE (tunnel + credentials destroyed; any
`cloudflared` running it stops; routes break). `update_config` (PUT)
REPLACES the whole ingress rule set — always `get_config` first as a
rollback snapshot.

Every tool routes through the single `api.request_json` /
`api.request_envelope` HTTP seam (tests patch
`cloudflare.api.request_json` / `request_envelope`). API failure ⇒ a
typed-error envelope, never a fabricated success.
"""
from __future__ import annotations

import logging

from mcp.server import Server
from mcp.types import Tool

from _kit.errors import typed_error

from .. import api
from ..settings import get_settings
from ..types import (
    TunnelConfigOutput,
    TunnelCreateInput,
    TunnelCreateOutput,
    TunnelDeleteInput,
    TunnelDeleteOutput,
    TunnelGetConfigInput,
    TunnelGetInput,
    TunnelGetOutput,
    TunnelListInput,
    TunnelListOutput,
    TunnelUpdateConfigInput,
)

logger = logging.getLogger(__name__)


def _ctx() -> dict:
    s = get_settings()
    return {
        "api_token": s.api_token or "",
        "base_url": s.base_url or "",
        "timeout": s.timeout_seconds,
    }


def _account_id_or_error() -> tuple[str, dict | None]:
    """Return `(account_id, None)` when configured, else `("", error_dict)`
    — the account-scoped tunnel paths cannot be built without it, so we
    surface a typed never-faked 424 rather than a malformed URL."""
    s = get_settings()
    if not s.account_id:
        return "", typed_error(api.CloudflareApiError(
            "cloudflare.tunnel.* is account-scoped — set "
            "CLOUDFLARE_ACCOUNT_ID in mcp/cloudflare/.env.",
            status=424,
        ))
    return s.account_id, None


def _tunnel_base(account_id: str) -> str:
    return f"/accounts/{account_id}/cfd_tunnel"


# ─── Reads ───────────────────────────────────────────────────────────────


async def tunnel_list(args: dict) -> dict:
    TunnelListInput(**args)
    account_id, err = _account_id_or_error()
    if err:
        return TunnelListOutput(error=err).model_dump()
    try:
        env = api.request_envelope("GET", _tunnel_base(account_id), **_ctx())
    except api.CloudflareApiError as e:
        return TunnelListOutput(error=typed_error(e)).model_dump()
    result = env.get("result")
    return TunnelListOutput(
        tunnels=result if isinstance(result, list) else [],
        result_info=env.get("result_info")
        if isinstance(env.get("result_info"), dict)
        else None,
    ).model_dump()


async def tunnel_get(args: dict) -> dict:
    inp = TunnelGetInput(**args)
    account_id, err = _account_id_or_error()
    if err:
        return TunnelGetOutput(error=err).model_dump()
    try:
        data = api.request_json(
            "GET", f"{_tunnel_base(account_id)}/{inp.tunnel_id}", **_ctx()
        )
    except api.CloudflareApiError as e:
        return TunnelGetOutput(error=typed_error(e)).model_dump()
    return TunnelGetOutput(
        tunnel=data if isinstance(data, dict) else None,
        status=(data or {}).get("status") if isinstance(data, dict) else None,
    ).model_dump()


async def tunnel_get_config(args: dict) -> dict:
    inp = TunnelGetConfigInput(**args)
    account_id, err = _account_id_or_error()
    if err:
        return TunnelConfigOutput(error=err).model_dump()
    try:
        data = api.request_json(
            "GET",
            f"{_tunnel_base(account_id)}/{inp.tunnel_id}/configurations",
            **_ctx(),
        )
    except api.CloudflareApiError as e:
        return TunnelConfigOutput(error=typed_error(e)).model_dump()
    return TunnelConfigOutput(
        config=data if isinstance(data, dict) else None, ok=True
    ).model_dump()


# ─── Writes (confirm-gated) ──────────────────────────────────────────────


async def tunnel_create(args: dict) -> dict:
    inp = TunnelCreateInput(**args)
    if not inp.confirm:
        return TunnelCreateOutput(
            error=typed_error(api.ConfirmationRequiredError(
                "cloudflare.tunnel.create",
                f"creates a new Cloudflare Tunnel '{inp.name}' "
                "(returns a runnable token — treat as secret)",
            )),
        ).model_dump()
    account_id, err = _account_id_or_error()
    if err:
        return TunnelCreateOutput(error=err).model_dump()
    body = {"name": inp.name, "config_src": inp.config_src}
    try:
        data = api.request_json(
            "POST", _tunnel_base(account_id), body=body, **_ctx()
        )
    except api.CloudflareApiError as e:
        return TunnelCreateOutput(error=typed_error(e)).model_dump()
    return TunnelCreateOutput(
        tunnel=data if isinstance(data, dict) else None, ok=True
    ).model_dump()


async def tunnel_delete(args: dict) -> dict:
    inp = TunnelDeleteInput(**args)
    if not inp.confirm:
        return TunnelDeleteOutput(
            tunnel_id=inp.tunnel_id,
            error=typed_error(api.ConfirmationRequiredError(
                "cloudflare.tunnel.delete",
                "STRONGEST GATE — IRREVERSIBLE: destroys the tunnel + its "
                "credentials (any cloudflared running it stops; routes "
                "through it break)",
            )),
        ).model_dump()
    account_id, err = _account_id_or_error()
    if err:
        return TunnelDeleteOutput(tunnel_id=inp.tunnel_id, error=err).model_dump()
    try:
        data = api.request_json(
            "DELETE", f"{_tunnel_base(account_id)}/{inp.tunnel_id}", **_ctx()
        )
    except api.CloudflareApiError as e:
        return TunnelDeleteOutput(
            tunnel_id=inp.tunnel_id, error=typed_error(e)
        ).model_dump()
    return TunnelDeleteOutput(
        tunnel_id=inp.tunnel_id, ok=True, result=data
    ).model_dump()


async def tunnel_update_config(args: dict) -> dict:
    inp = TunnelUpdateConfigInput(**args)
    if not inp.confirm:
        return TunnelConfigOutput(
            error=typed_error(api.ConfirmationRequiredError(
                "cloudflare.tunnel.update_config",
                "REPLACES the tunnel's whole ingress rule set (PUT — "
                "get_config first as a rollback snapshot)",
            )),
        ).model_dump()
    account_id, err = _account_id_or_error()
    if err:
        return TunnelConfigOutput(error=err).model_dump()
    body = {"config": {"ingress": inp.ingress}}
    try:
        data = api.request_json(
            "PUT",
            f"{_tunnel_base(account_id)}/{inp.tunnel_id}/configurations",
            body=body, **_ctx(),
        )
    except api.CloudflareApiError as e:
        return TunnelConfigOutput(error=typed_error(e)).model_dump()
    return TunnelConfigOutput(
        config=data if isinstance(data, dict) else None, ok=True
    ).model_dump()


HANDLERS = {
    "cloudflare.tunnel.list": tunnel_list,
    "cloudflare.tunnel.get": tunnel_get,
    "cloudflare.tunnel.get_config": tunnel_get_config,
    "cloudflare.tunnel.create": tunnel_create,
    "cloudflare.tunnel.delete": tunnel_delete,
    "cloudflare.tunnel.update_config": tunnel_update_config,
}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(name="cloudflare.tunnel.list",
             description="List Cloudflare Tunnels (cfd_tunnel) on the "
             "account. READ-ONLY. Account-scoped.",
             inputSchema=TunnelListInput.model_json_schema()),
        Tool(name="cloudflare.tunnel.get",
             description="Inspect one tunnel — status/connections/type. "
             "READ-ONLY. Account-scoped.",
             inputSchema=TunnelGetInput.model_json_schema()),
        Tool(name="cloudflare.tunnel.get_config",
             description="Read a tunnel's ingress configuration "
             "(hostname → service routing). READ-ONLY. Account-scoped.",
             inputSchema=TunnelGetConfigInput.model_json_schema()),
        Tool(name="cloudflare.tunnel.create",
             description="Create a remotely-managed Cloudflare Tunnel. "
             "WRITE — confirm-gated (412). Account-scoped.",
             inputSchema=TunnelCreateInput.model_json_schema()),
        Tool(name="cloudflare.tunnel.delete",
             description="Delete a tunnel — STRONGEST gate: IRREVERSIBLE "
             "(tunnel + credentials destroyed). WRITE — confirm-gated "
             "(412). Account-scoped.",
             inputSchema=TunnelDeleteInput.model_json_schema()),
        Tool(name="cloudflare.tunnel.update_config",
             description="Replace a tunnel's ingress rules (PUT — full "
             "replace; get_config first). WRITE — confirm-gated (412). "
             "Account-scoped.",
             inputSchema=TunnelUpdateConfigInput.model_json_schema()),
    ]


__all__ = ["register", "tool_descriptors", "HANDLERS"]
