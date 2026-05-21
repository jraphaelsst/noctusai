"""cloudflare.zones.* tools — zone (domain) list / inspect / create.

Reads (no gate): list / get.
Writes (confirm-gated): create.

Every tool routes through the single `api.request_json` /
`api.request_envelope` HTTP seam (tests patch
`cloudflare.api.request_json` / `request_envelope`). API failure ⇒ a
typed-error envelope, never a fabricated success. `api` is invoked via
the module so `patch("cloudflare.api.request_json")` is observed.
"""
from __future__ import annotations

import logging

from mcp.server import Server
from mcp.types import Tool

from _kit.errors import typed_error

from .. import api
from ..settings import get_settings
from ..types import (
    ZonesCreateInput,
    ZonesCreateOutput,
    ZonesGetInput,
    ZonesGetOutput,
    ZonesListInput,
    ZonesListOutput,
)

logger = logging.getLogger(__name__)

_ZONES_BASE = "/zones"


def _ctx() -> dict:
    s = get_settings()
    return {
        "api_token": s.api_token or "",
        "base_url": s.base_url or "",
        "timeout": s.timeout_seconds,
    }


# ─── Reads ───────────────────────────────────────────────────────────────


async def zones_list(args: dict) -> dict:
    inp = ZonesListInput(**args)
    try:
        env = api.request_envelope(
            "GET", _ZONES_BASE, params={"name": inp.name}, **_ctx()
        )
    except api.CloudflareApiError as e:
        return ZonesListOutput(error=typed_error(e)).model_dump()
    result = env.get("result")
    return ZonesListOutput(
        zones=result if isinstance(result, list) else [],
        result_info=env.get("result_info")
        if isinstance(env.get("result_info"), dict)
        else None,
    ).model_dump()


async def zones_get(args: dict) -> dict:
    inp = ZonesGetInput(**args)
    try:
        data = api.request_json("GET", f"{_ZONES_BASE}/{inp.zone_id}", **_ctx())
    except api.CloudflareApiError as e:
        return ZonesGetOutput(error=typed_error(e)).model_dump()
    return ZonesGetOutput(
        zone=data if isinstance(data, dict) else None
    ).model_dump()


# ─── Writes (confirm-gated) ──────────────────────────────────────────────


async def zones_create(args: dict) -> dict:
    inp = ZonesCreateInput(**args)
    if not inp.confirm:
        return ZonesCreateOutput(
            error=typed_error(api.ConfirmationRequiredError(
                "cloudflare.zones.create",
                "onboards a new domain (zone) to the account "
                "(changes account state / may be billable)",
            )),
        ).model_dump()
    s = get_settings()
    account_id = inp.account_id or s.account_id
    if not account_id:
        return ZonesCreateOutput(
            error=typed_error(api.CloudflareApiError(
                "cloudflare.zones.create needs an account id — pass "
                "account_id or set CLOUDFLARE_ACCOUNT_ID in "
                "mcp/cloudflare/.env.",
                status=424,
            )),
        ).model_dump()
    body = {"name": inp.name, "account": {"id": account_id}, "type": inp.type}
    try:
        data = api.request_json("POST", _ZONES_BASE, body=body, **_ctx())
    except api.CloudflareApiError as e:
        return ZonesCreateOutput(error=typed_error(e)).model_dump()
    return ZonesCreateOutput(
        zone=data if isinstance(data, dict) else None, ok=True
    ).model_dump()


HANDLERS = {
    "cloudflare.zones.list": zones_list,
    "cloudflare.zones.get": zones_get,
    "cloudflare.zones.create": zones_create,
}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(name="cloudflare.zones.list",
             description="List zones (domains) on the account; optional "
             "exact-name filter. READ-ONLY.",
             inputSchema=ZonesListInput.model_json_schema()),
        Tool(name="cloudflare.zones.get",
             description="Inspect one zone — status/name-servers/plan/"
             "account. READ-ONLY.",
             inputSchema=ZonesGetInput.model_json_schema()),
        Tool(name="cloudflare.zones.create",
             description="Onboard a new zone (domain) to the account. "
             "WRITE — confirm-gated (412); needs account id "
             "(arg or CLOUDFLARE_ACCOUNT_ID).",
             inputSchema=ZonesCreateInput.model_json_schema()),
    ]


__all__ = ["register", "tool_descriptors", "HANDLERS"]
