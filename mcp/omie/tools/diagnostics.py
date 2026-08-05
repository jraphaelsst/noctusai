"""`omie.diagnostics.*` — connector self-inspection.

Omie's failure modes are mostly invisible from a single tool result: a
credential is wrong, a method is one failure away from a 30-minute block,
or the client is already throttling. These tools make that state
observable without guessing.
"""
from __future__ import annotations

from mcp.server import Server
from mcp.types import Tool

from .. import catalog
from ..ratelimit import (
    FAILURE_STREAK_OPEN,
    GLOBAL_PER_MINUTE,
    PER_METHOD_CONCURRENCY,
    PER_METHOD_PER_MINUTE,
    limiter,
)
from ..settings import get_settings
from . import resources as _resources


async def connection_status(args: dict) -> dict:
    """Configuration + catalog + throttle state. Makes no API call."""
    s = get_settings()
    try:
        cat = catalog.status()
        cat_ok = True
    except Exception as e:  # catalog missing/corrupt is reported, not hidden
        cat, cat_ok = {"error": str(e)}, False
    return {
        "ok": s.configured and cat_ok,
        "configured": s.configured,
        "base_url": s.base_url,
        "timeout_seconds": s.timeout_seconds,
        "environments": [e.redacted() for e in s.environments],
        "default_environment": s.default_environment,
        "catalog": cat,
        "catalog_ok": cat_ok,
        "curated_resources": len(_resources.RESOURCES),
        "rate_limits": limiter.snapshot(),
        "next_step": (
            "Set OMIE_ENVIRONMENTS or OMIE_APP_KEY/OMIE_APP_SECRET."
            if not s.configured
            else "Run omie.environments.check to verify credentials live."
        ),
    }


async def rate_limit_status(args: dict) -> dict:
    """Current throttle windows, concurrency, and any open local circuits."""
    return {
        "ok": True,
        "documented_limits": {
            "per_ip_per_minute": GLOBAL_PER_MINUTE,
            "per_ip_appkey_method_per_minute": PER_METHOD_PER_MINUTE,
            "concurrent_per_ip_appkey_method": PER_METHOD_CONCURRENCY,
            "max_records_per_page": 100,
            "server_side_block": "HTTP 425 for ~30 min after 10 consecutive "
                                 "failures on the same IP+app_key+method",
            "source": "ajuda.omie.com.br § Limites de Consumo da API do Omie",
        },
        "client_policy": {
            "throttled_at_percent_of_limit": 90,
            "local_circuit_opens_after_consecutive_failures": FAILURE_STREAK_OPEN,
            "note": "The client throttles before sending and opens a local "
                    "circuit early, so a retry loop cannot walk into Omie's "
                    "30-minute block.",
        },
        "current": limiter.snapshot(),
    }


HANDLERS = {
    "omie.diagnostics.connection_status": connection_status,
    "omie.diagnostics.rate_limit_status": rate_limit_status,
}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(
            name="omie.diagnostics.connection_status",
            description=(
                "Connector health: which Omie environments are configured "
                "(redacted), whether the bundled API catalog loaded, how many "
                "curated resources are exposed, and current throttle state. "
                "Makes no API call — start here when something is misbehaving."
            ),
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="omie.diagnostics.rate_limit_status",
            description=(
                "Omie's documented consumption limits alongside this client's "
                "live throttle counters and any open local circuits. Check this "
                "before a bulk import, or after seeing rate-limit errors."
            ),
            inputSchema={"type": "object", "properties": {}},
        ),
    ]


__all__ = ["register", "tool_descriptors", "HANDLERS"]
