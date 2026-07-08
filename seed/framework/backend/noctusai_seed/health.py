"""Health + readiness endpoints baked into every NoctusAI product.

Every product inheriting `noctusai_seed.create_product_app(...)` exposes:

  - ``GET /_health`` — *liveness*: is the process alive? Always fast.
  - ``GET /_ready``  — *readiness*: are downstream dependencies (DB, vendors,
    Redis) healthy enough to accept traffic? May be slower.

Default behavior is the polite seed default — both endpoints exist and
return ``200`` with an empty ``checks=[]`` array even if the product
never opted in. Products opt-in to richer checks via :class:`HealthEndpointConfig`::

    from noctusai_seed import HealthEndpointConfig, create_product_app

    async def db_ping() -> tuple[bool, str | None]:
        try:
            db.get_admin_client().table("notifications").select("id").limit(1).execute()
            return (True, None)
        except Exception as exc:
            return (False, str(exc))

    app = create_product_app(
        ...,
        health_config=HealthEndpointConfig(readiness_hooks=[db_ping]),
    )

Endpoint shape (both ``/_health`` and ``/_ready``)::

    {
      "ok": true | false,
      "checks": [{"name": "db_ping", "ok": true, "error": null}, ...],
      "timestamp": "2026-05-04T19:23:11.123456+00:00"
    }

When any hook returns ``ok=False`` *or* raises, the endpoint flips its
HTTP status to ``503`` while still returning the full ``checks`` array so
operators can see which probe failed. Hook exceptions are caught + logged
at WARN — never propagated to a 500. Other hooks still run.

Liveness vs readiness split mirrors the Kubernetes convention: liveness
should be cheap (process responsiveness only) so a slow DB doesn't trigger
a pod restart loop; readiness is allowed to be slower because failing it
just removes the pod from the load-balancer rotation.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Awaitable, Callable, Protocol, runtime_checkable

from fastapi import FastAPI
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


@runtime_checkable
class HealthCheckHook(Protocol):
    """Async callable that reports whether one piece of infrastructure is healthy.

    Returns ``(ok, error_message)``:
      - ``(True, None)``  → healthy
      - ``(False, msg)`` → unhealthy with a short human-readable reason

    Hooks SHOULD have a meaningful ``__name__`` (so the JSON ``checks`` array
    surfaces ``"db_ping"`` rather than ``"<lambda>"``). Hooks that raise are
    caught by the seed; the exception is mapped to ``ok=False`` and logged
    at WARN. Network-free hooks are recommended for liveness; readiness may
    do real DB / Redis / vendor pings.
    """

    async def __call__(self) -> tuple[bool, str | None]: ...


@dataclass
class HealthEndpointConfig:
    """Configuration for the seed-baked ``/_health`` + ``/_ready`` endpoints.

    Liveness probes should be FAST + light — only "is the process alive,
    can it answer?". Readiness probes may include DB / Redis / vendor pings
    (allowed to be slower). An empty config (the default) yields endpoints
    that always return ``200`` with ``checks=[]`` — every product gets the
    endpoints by default; opt-in adds real probes.
    """

    liveness_hooks: list[HealthCheckHook] = field(default_factory=list)
    readiness_hooks: list[HealthCheckHook] = field(default_factory=list)


# Sentinel attribute on the FastAPI app object so a second
# `mount_health_endpoints` call raises rather than silently appending
# duplicate routes (FastAPI itself would happily register both, leaving
# the runner with non-deterministic dispatch order).
_MOUNTED_FLAG = "_noctusai_seed_health_mounted"


async def _run_hook(hook: HealthCheckHook) -> dict:
    """Run a single hook safely, normalize result to a JSON-ready dict.

    Catches any exception, logs it at WARN with the hook name, and maps to
    ``{ok: False, error: str(exc)}``. Other hooks still run regardless.
    """
    name = getattr(hook, "__name__", None) or hook.__class__.__name__
    try:
        result = await hook()
    except Exception as exc:  # noqa: BLE001 — hooks are user-supplied; any failure is a probe failure, not a 500
        logger.warning("Health check hook %r raised: %s", name, exc)
        return {"name": name, "ok": False, "error": str(exc)}

    if not isinstance(result, tuple) or len(result) != 2:
        # Defensive: misshapen hook return is itself a probe failure.
        logger.warning(
            "Health check hook %r returned %r (expected (ok, error_message) tuple)",
            name,
            result,
        )
        return {
            "name": name,
            "ok": False,
            "error": f"hook returned {type(result).__name__} (expected tuple)",
        }
    ok, error = result
    return {"name": name, "ok": bool(ok), "error": error if not ok else None}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def mount_health_endpoints(app: FastAPI, config: HealthEndpointConfig) -> None:
    """Register ``/_health`` + ``/_ready`` on the given FastAPI app.

    Idempotency: calling this twice on the same app raises
    ``RuntimeError`` rather than silently registering duplicate routes.
    The seed framework calls this exactly once at the end of
    :func:`noctusai_seed.create_product_app`; products should never call
    it directly.

    Args:
        app: FastAPI application (e.g. the one returned by
            ``create_product_app``).
        config: which liveness + readiness hooks to wire. An empty config
            leaves the endpoints always-200 — the polite default.

    Returns:
        ``None``. Routes are attached to ``app`` in place.
    """
    if getattr(app, _MOUNTED_FLAG, False):
        raise RuntimeError(
            "mount_health_endpoints called twice on the same FastAPI app — "
            "the seed factory mounts this exactly once at the end of "
            "create_product_app(); a second call would register duplicate "
            "/_health + /_ready routes."
        )

    liveness_hooks = list(config.liveness_hooks)
    readiness_hooks = list(config.readiness_hooks)

    @app.get("/_health", tags=["Ops"], include_in_schema=False)
    async def _health():  # pragma: no cover — wired below; covered by TestClient calls
        checks = [await _run_hook(h) for h in liveness_hooks]
        ok = all(c["ok"] for c in checks)
        body = {"ok": ok, "checks": checks, "timestamp": _now_iso()}
        return JSONResponse(body, status_code=200 if ok else 503)

    @app.get("/_ready", tags=["Ops"], include_in_schema=False)
    async def _ready():  # pragma: no cover — same as above
        checks = [await _run_hook(h) for h in readiness_hooks]
        ok = all(c["ok"] for c in checks)
        body = {"ok": ok, "checks": checks, "timestamp": _now_iso()}
        return JSONResponse(body, status_code=200 if ok else 503)

    @app.get("/_version", tags=["Ops"], include_in_schema=False)
    async def _version():  # pragma: no cover — covered by TestClient calls
        # Deploy-provenance: WHAT seed / product / build is ACTUALLY running.
        # Lets anyone verify a deploy landed (compare deployed seed_sha to the
        # source) over plain HTTP — no shell/image access needed. The 2026-07-08
        # base-image-staleness debug needed exactly this signal.
        try:
            from noctusai_seed._version import __version__ as seed_sha
        except Exception:  # noqa: BLE001 — provenance must never 500
            seed_sha = "unknown"
        return JSONResponse({
            "product": getattr(app, "title", None),
            "product_version": getattr(app, "version", None),
            "seed_sha": seed_sha,
            # Baked at image build (Dockerfile `ENV GIT_SHA`); None if unbaked.
            "build_sha": os.environ.get("GIT_SHA") or os.environ.get("NOCTUS_BUILD_SHA"),
            "timestamp": _now_iso(),
        })

    setattr(app, _MOUNTED_FLAG, True)


__all__ = [
    "HealthCheckHook",
    "HealthEndpointConfig",
    "mount_health_endpoints",
]
