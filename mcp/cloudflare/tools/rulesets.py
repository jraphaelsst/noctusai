"""cloudflare.rulesets.* tools — inspect a zone's rulesets (READ-ONLY).

Closes the "can't see CF cache rules from here" gap (2026-07-08 sw.js debug): a
CloudFlare cache rule can OVERRIDE an origin's `Cache-Control` for a URL/extension
(e.g. force `max-age` on `.js`), which the origin-header view alone can't reveal.
This lists a zone's rulesets and, when `phase` is given, the rules in that phase's
entrypoint — so `http_request_cache_settings` (Cache Rules) is inspectable in-home.

Read-only (no confirm gate). All I/O routes through the single
`api.request_json` / `request_envelope` seam (tests patch `cloudflare.api.*`).
Editing rulesets is deliberately NOT exposed here (a cache-rule change is a
broad, risky prod-config mutation — do it in the dashboard, consciously).
"""
from __future__ import annotations

import logging

from mcp.server import Server
from mcp.types import Tool

from _kit.errors import typed_error

from .. import api
from ..settings import get_settings
from ..types import RulesetsListInput, RulesetsListOutput

logger = logging.getLogger(__name__)

_ZONES_BASE = "/zones"


def _ctx() -> dict:
    s = get_settings()
    return {
        "api_token": s.api_token or "",
        "base_url": s.base_url or "",
        "timeout": s.timeout_seconds,
    }


def _resolve_zone_id(zone_name: str, ctx: dict) -> str:
    env = api.request_envelope(
        "GET", _ZONES_BASE, params={"name": zone_name}, **ctx
    )
    zones = env.get("result") or []
    if not zones:
        raise api.CloudflareApiError(
            f"zone {zone_name!r} not found on this account", status=404
        )
    return zones[0]["id"]


async def rulesets_list(args: dict) -> dict:
    inp = RulesetsListInput(**args)
    ctx = _ctx()
    try:
        zone_id = inp.zone_id or _resolve_zone_id(inp.zone, ctx)
        env = api.request_envelope(
            "GET", f"{_ZONES_BASE}/{zone_id}/rulesets", **ctx
        )
        rulesets = env.get("result") or []
        phase_rules = None
        if inp.phase:
            # The phase entrypoint holds the ACTUAL rules (e.g. cache overrides).
            rules_env = api.request_envelope(
                "GET",
                f"{_ZONES_BASE}/{zone_id}/rulesets/phases/{inp.phase}/entrypoint",
                **ctx,
            )
            result = rules_env.get("result") or {}
            phase_rules = result.get("rules") if isinstance(result, dict) else None
    except api.CloudflareApiError as e:
        return RulesetsListOutput(error=typed_error(e)).model_dump()

    return RulesetsListOutput(
        zone_id=zone_id,
        rulesets=rulesets if isinstance(rulesets, list) else [],
        phase=inp.phase,
        phase_rules=phase_rules,
    ).model_dump()


HANDLERS = {
    "cloudflare.rulesets.list": rulesets_list,
}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(name="cloudflare.rulesets.list",
             description="List a zone's rulesets; with phase= (e.g. "
             "'http_request_cache_settings' for Cache Rules) also return that "
             "phase's entrypoint rules. READ-ONLY. Use to see a CF cache rule "
             "that overrides origin Cache-Control for a URL/extension.",
             inputSchema=RulesetsListInput.model_json_schema()),
    ]


__all__ = ["register", "tool_descriptors", "HANDLERS", "rulesets_list"]
