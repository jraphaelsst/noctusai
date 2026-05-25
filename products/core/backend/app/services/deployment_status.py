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
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

# Internal address of every product container on noctus-net: the
# single-container house model serves API + SPA on the product's HOUSE port
# (uvicorn `--port <house>` — e.g. 8004 for seed, 8011 for social-wiring, NOT
# a uniform 8000). The compose service name == the product slug. The house
# port is parsed from each product's `url_base` (always `http://localhost:
# <house>` in the stored row; the prod tile-URL override is applied at resolve
# time, not in the row), so the probe is correct in dev AND prod.
_DEFAULT_PORT = 8000  # fallback only (url_base absent / portless)
_HEALTH_PATH = "/api/health"
_PROBE_TIMEOUT_SECONDS = 1.5
_CACHE_TTL_SECONDS = 60.0

# {slug: house_port} -> {slug: is_deployed}. Injected so tests can supply a
# fake fleet without reaching the network.
FleetProber = Callable[[dict[str, int]], Awaitable[dict[str, bool]]]


def house_port_from_url_base(url_base: str | None) -> int:
    """Extract a product container's internal HOUSE port from its url_base.

    `url_base` is `http://localhost:<house>` for every product (e.g.
    `http://localhost:8004`). Returns `_DEFAULT_PORT` when absent / portless
    so a malformed row degrades to a (likely-failing) 8000 probe instead of
    raising — never let the launcher 500 over a bad catalog row.
    """
    if not url_base:
        return _DEFAULT_PORT
    try:
        return urlparse(url_base).port or _DEFAULT_PORT
    except (ValueError, TypeError):
        return _DEFAULT_PORT

# Module-level result cache. Survives across requests within one core process;
# `reset_cache()` clears it for deterministic tests.
_cache: dict[str, object] = {"ts": 0.0, "data": {}}


async def probe_one(slug: str, port: int, *, client: httpx.AsyncClient) -> bool:
    """Return True iff ``http://<slug>:<port>/api/health`` answers < 400."""
    url = f"http://{slug}:{port}{_HEALTH_PATH}"
    try:
        resp = await client.get(url)
    except (httpx.HTTPError, OSError) as exc:
        # Down / not-on-network / DNS-miss = simply not deployed. Expected for
        # any product not currently running — debug, not a warning, so a
        # half-up fleet doesn't spam logs on every dashboard load.
        logger.debug("deployment probe miss slug=%s url=%s: %s", slug, url, exc)
        return False
    return resp.status_code < 400


async def probe_fleet(targets: dict[str, int]) -> dict[str, bool]:
    """Concurrently probe every {slug: house_port}; missing/down → False."""
    if not targets:
        return {}
    items = list(targets.items())
    async with httpx.AsyncClient(timeout=_PROBE_TIMEOUT_SECONDS) as client:
        results = await asyncio.gather(
            *(probe_one(slug, port, client=client) for slug, port in items)
        )
    return {slug: ok for (slug, _port), ok in zip(items, results)}


def reset_cache() -> None:
    """Clear the module-level cache (test determinism)."""
    _cache["ts"] = 0.0
    _cache["data"] = {}


async def get_deployment_status(
    targets: dict[str, int], *, prober: FleetProber
) -> dict[str, bool]:
    """Return {slug: is_deployed}, served from a short-TTL cache when fresh.

    `targets` maps each catalog slug → its container's house port.
    """
    now = time.monotonic()
    data = _cache["data"]
    assert isinstance(data, dict)
    fresh = (now - float(_cache["ts"])) < _CACHE_TTL_SECONDS
    if fresh and set(targets) <= set(data):
        return {s: bool(data.get(s, False)) for s in targets}
    probed = await prober(targets)
    _cache["ts"] = now
    _cache["data"] = probed
    return probed
