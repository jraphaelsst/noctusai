"""cloudflare.cache.* tools — edge cache purge.

Write (confirm-gated): purge. Purging drops cached responses at the CF edge
so the next request re-fetches from origin — the fix for "stale content is
being served fleet-wide after a deploy". The canonical case (2026-07-08): a
retired PWA service worker (`sw.js`) sat in CF's edge cache (`cf-cache-status:
HIT`, age ~79min), shielding the new self-destroying worker from clients; the
origin `no-cache` header does NOT evict an already-cached edge copy, so an
explicit purge is required. See
``KB § PATTERNS/frontend/spa-cache-and-service-worker.md``.

Requires the API token to carry ``Zone > Cache Purge > Purge`` (the
zone/DNS/tunnel token does NOT by default — a purge without it 401s). All I/O
routes through the single ``api.request_json`` / ``request_envelope`` seam
(tests patch ``cloudflare.api.*``).
"""
from __future__ import annotations

import logging

from mcp.server import Server
from mcp.types import Tool

from _kit.errors import typed_error

from .. import api
from ..settings import get_settings
from ..types import CachePurgeInput, CachePurgeOutput

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
    """Look up a zone id by exact name; raise CloudflareApiError if absent."""
    env = api.request_envelope(
        "GET", _ZONES_BASE, params={"name": zone_name}, **ctx
    )
    zones = env.get("result") or []
    if not zones:
        raise api.CloudflareApiError(
            f"zone {zone_name!r} not found on this account", status=404
        )
    return zones[0]["id"]


async def cache_purge(args: dict) -> dict:
    inp = CachePurgeInput(**args)
    if not inp.confirm:
        target = "the ENTIRE zone" if inp.purge_everything else "the listed URLs"
        return CachePurgeOutput(
            error=typed_error(api.ConfirmationRequiredError(
                "cloudflare.cache.purge",
                f"purges {target} from the Cloudflare edge cache (a "
                "production action — a brief cache-cold period as assets "
                "re-fetch from origin)",
            )),
        ).model_dump()

    if inp.purge_everything and inp.files:
        return CachePurgeOutput(
            error=typed_error(api.CloudflareApiError(
                "cloudflare.cache.purge: pass EITHER files OR "
                "purge_everything, not both.",
                status=422,
            )),
        ).model_dump()
    if not inp.purge_everything and not inp.files:
        return CachePurgeOutput(
            error=typed_error(api.CloudflareApiError(
                "cloudflare.cache.purge: nothing to purge — pass `files` "
                "(URL list) or `purge_everything=true`.",
                status=422,
            )),
        ).model_dump()

    ctx = _ctx()
    try:
        zone_id = inp.zone_id or _resolve_zone_id(inp.zone, ctx)
        body = (
            {"purge_everything": True}
            if inp.purge_everything
            else {"files": inp.files}
        )
        api.request_json("POST", f"{_ZONES_BASE}/{zone_id}/purge_cache",
                         body=body, **ctx)
    except api.CloudflareApiError as e:
        return CachePurgeOutput(error=typed_error(e)).model_dump()

    return CachePurgeOutput(
        ok=True,
        zone_id=zone_id,
        purged_files=None if inp.purge_everything else list(inp.files or []),
        purged_everything=inp.purge_everything,
    ).model_dump()


HANDLERS = {
    "cloudflare.cache.purge": cache_purge,
}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(name="cloudflare.cache.purge",
             description="Purge the Cloudflare edge cache for a zone — by URL "
             "list (default, safe) or the whole zone (purge_everything). "
             "WRITE — confirm-gated (412). Needs the token's "
             "'Zone > Cache Purge > Purge' permission. Use after a deploy when "
             "stale content (e.g. a retired sw.js) is edge-cached.",
             inputSchema=CachePurgeInput.model_json_schema()),
    ]


__all__ = ["register", "tool_descriptors", "HANDLERS"]
