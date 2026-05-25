"""Runtime deployment detection for the launcher's "dev" badge.

A product is **deployed** iff its single container is up and reachable on the
shared ``noctus-net`` network at ``http://<slug>:8000/api/health``. This is
environment-accurate *by construction*: in dev (the ``start.sh`` fleet) and in
prod (the VPS) every product container joins ``noctus-net`` under its slug and
serves the seed health endpoint on internal port 8000 (single-container house
model — uvicorn serves API + SPA on one port). core simply probes whatever
fleet it runs alongside, so the same catalog yields "deployed in dev but not
prod" automatically. A catalog product whose container is not currently up →
probe fails → not deployed → the launcher renders a "dev" badge.

The launcher must stay fast and must NEVER fail because a product is down, so:
  * probes run concurrently with a short per-probe timeout,
  * any probe error/timeout/DNS-miss = not deployed (returned, never raised),
  * results are cached for ``_CACHE_TTL_SECONDS`` so repeated dashboard loads
    don't re-probe the whole fleet on every request.

The prober is injected as a FastAPI dependency (``get_fleet_prober`` in the
products router) so tests substitute a fake without monkeypatching our own
code (DI-test-seam).
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Awaitable, Callable

import httpx

logger = logging.getLogger(__name__)

# Internal address of every product container on noctus-net: the
# single-container house model serves API + SPA on port 8000 and the compose
# service name == the product slug.
_INTERNAL_PORT = 8000
_HEALTH_PATH = "/api/health"
_PROBE_TIMEOUT_SECONDS = 1.5
_CACHE_TTL_SECONDS = 60.0

# (slugs) -> {slug: is_deployed}. Injected so tests can supply a fake fleet
# without reaching the network.
FleetProber = Callable[[list[str]], Awaitable[dict[str, bool]]]

# Module-level result cache. Survives across requests within one core process;
# `reset_cache()` clears it for deterministic tests.
_cache: dict[str, object] = {"ts": 0.0, "data": {}}


async def probe_one(slug: str, *, client: httpx.AsyncClient) -> bool:
    """Return True iff ``http://<slug>:8000/api/health`` answers < 400."""
    url = f"http://{slug}:{_INTERNAL_PORT}{_HEALTH_PATH}"
    try:
        resp = await client.get(url)
    except (httpx.HTTPError, OSError) as exc:
        # Down / not-on-network / DNS-miss = simply not deployed. Expected for
        # any product not currently running — debug, not a warning, so a
        # half-up fleet doesn't spam logs on every dashboard load.
        logger.debug("deployment probe miss slug=%s url=%s: %s", slug, url, exc)
        return False
    return resp.status_code < 400


async def probe_fleet(slugs: list[str]) -> dict[str, bool]:
    """Concurrently probe every slug; missing/down products map to False."""
    if not slugs:
        return {}
    async with httpx.AsyncClient(timeout=_PROBE_TIMEOUT_SECONDS) as client:
        results = await asyncio.gather(*(probe_one(s, client=client) for s in slugs))
    return dict(zip(slugs, results))


def reset_cache() -> None:
    """Clear the module-level cache (test determinism)."""
    _cache["ts"] = 0.0
    _cache["data"] = {}


async def get_deployment_status(
    slugs: list[str], *, prober: FleetProber
) -> dict[str, bool]:
    """Return {slug: is_deployed}, served from a short-TTL cache when fresh."""
    now = time.monotonic()
    data = _cache["data"]
    assert isinstance(data, dict)
    fresh = (now - float(_cache["ts"])) < _CACHE_TTL_SECONDS
    if fresh and set(slugs) <= set(data):
        return {s: bool(data.get(s, False)) for s in slugs}
    probed = await prober(slugs)
    _cache["ts"] = now
    _cache["data"] = probed
    return probed
