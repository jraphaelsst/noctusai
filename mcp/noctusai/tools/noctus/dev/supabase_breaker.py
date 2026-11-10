"""noctus.dev.supabase_breaker - read / re-arm / trip the Supabase request breaker over prod Redis, independent of Supabase.

The seed breaker (`noctusai_lib.primitives.supabase_breaker`, KB § PATTERNS/backend/supabase-request-breaker.md) keeps its
trips in Redis keys ``noctus:breaker:<product>:<source>`` and the fleet kill switch ``noctus:breaker:fleet``. This tool is
the human surface that works when Supabase is the thing that is down (the platform-admin route needs Supabase for its
role read): it talks to ``noctus-redis`` over the toolkit's throttled SSH chokepoint.

  action=status                         every held key + its state (read-only)
  action=rearm source=<s> [product=<p>] reason=<why> [by=<who>]   DEL the key + audit row. WRITE.
  action=trip  source=<s> [product=<p>] reason=<why> [by=<who>]    SET the key by hand (``source=fleet`` = stop EVERYTHING).

``source`` is ``fleet`` or a background source (``worker:<types>`` / ``scheduler:<job>``; never ``http``); any other needs
``product``. A reason is REQUIRED for rearm/trip. Dry-run by default (``confirm=False`` plans only). The seed breaker
observes a deleted key within ~10 s (a parked worker resumes) and a new key within the same window.

KB § PATTERNS/backend/supabase-request-breaker.md · KB § PATTERNS/architect/mcp-first-scripts.md
"""
from __future__ import annotations

import json
import os
import re
import shlex
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any, Protocol

from . import toolkit_freshness as _toolkit_freshness

PREFIX = "noctus:breaker:"
FLEET_KEY = f"{PREFIX}fleet"
AUDIT_KEY = f"{PREFIX}audit"
_SOURCE_RE = re.compile(r"^(worker|scheduler|gate):[A-Za-z0-9_.,:\-]+$")
_PRODUCT_RE = re.compile(r"^[a-z][a-z0-9\-]{0,40}$")
ACTIONS = ("status", "rearm", "trip")


class RedisOps(Protocol):
    def scan(self) -> list[str]: ...

    def mget(self, keys: list[str]) -> list[str | None]: ...

    def set(self, key: str, value: str) -> None: ...

    def delete(self, key: str) -> None: ...

    def rpush(self, key: str, value: str) -> None: ...


class RedisOpsError(RuntimeError):
    pass


class FakeRedisOps:
    """In-memory Fake of the prod Redis (tests; also the offline default when no host is reachable)."""

    def __init__(self, data: dict[str, str] | None = None) -> None:
        self.data = dict(data or {})
        self.audit: list[str] = []

    def scan(self) -> list[str]:
        return sorted(k for k in self.data if k.startswith(PREFIX))

    def mget(self, keys: list[str]) -> list[str | None]:
        return [self.data.get(k) for k in keys]

    def set(self, key: str, value: str) -> None:
        self.data[key] = value

    def delete(self, key: str) -> None:
        self.data.pop(key, None)

    def rpush(self, key: str, value: str) -> None:
        self.audit.append(value)


class VpsRedisOps:
    """`docker exec noctus-redis redis-cli ...` through the shared throttled + circuit-broken SSH chokepoint."""

    def __init__(self, ssh_host: str = "noctus-vps", container: str = "noctus-redis", runner: Callable | None = None) -> None:
        self._host, self._container, self._runner = ssh_host, container, runner

    def _cli(self, *args: str) -> str:
        from ._vps_ssh import run_remote

        cmd = f"docker exec {shlex.quote(self._container)} redis-cli " + " ".join(shlex.quote(a) for a in args)
        rc, out, err = (self._runner or run_remote)(self._host, cmd)
        if rc != 0 or "NOAUTH" in out or "ERR" in out.split("\n", 1)[0][:4]:
            raise RedisOpsError(f"redis-cli {args[0]} failed (rc={rc}): {(err or out).strip()[:300]}")
        return out

    def scan(self) -> list[str]:
        return [k for k in self._cli("--scan", "--pattern", f"{PREFIX}*").splitlines() if k.strip()]

    def mget(self, keys: list[str]) -> list[str | None]:
        if not keys:
            return []
        # one GET per key: redis-cli's MGET output cannot distinguish an empty line from nil with multi-line values
        return [self._cli("get", k).rstrip("\n") or None for k in keys]

    def set(self, key: str, value: str) -> None:
        self._cli("set", key, value)

    def delete(self, key: str) -> None:
        self._cli("del", key)

    def rpush(self, key: str, value: str) -> None:
        self._cli("rpush", key, value)


def _key(source: str, product: str) -> str:
    if source == "fleet":
        return FLEET_KEY
    return f"{PREFIX}{product}:{source}"


def _validate(action: str, source: str, product: str, reason: str) -> str | None:
    if action not in ACTIONS:
        return f"action must be one of {ACTIONS}"
    if action == "status":
        return None
    if not source:
        return "source is required (fleet | worker:<types> | scheduler:<job>)"
    if source == "http":
        return "the http source is alert-only: it is never held"
    if source != "fleet":
        if not _SOURCE_RE.match(source):
            return f"source {source!r} is not a background source (worker:<types> | scheduler:<job> | gate:<name> | fleet)"
        if not _PRODUCT_RE.match(product or ""):
            return "product (the product slug) is required for a per-product source"
    if not (reason or "").strip():
        return "reason is required"
    return None


def _default_executor(*, action: str, source: str, product: str, reason: str, by: str, confirm: bool,
                      ssh_host: str, ops: RedisOps | None = None, now: Callable[[], datetime] | None = None) -> dict[str, Any]:
    ops = ops or VpsRedisOps(ssh_host)
    when = (now or (lambda: datetime.now(timezone.utc)))().isoformat()
    who = (by or os.environ.get("USER") or "unknown").strip()
    try:
        if action == "status":
            keys = [k for k in ops.scan() if k != AUDIT_KEY]
            values = ops.mget(keys)
            held = {k: (json.loads(v) if v and v.startswith("{") else v) for k, v in zip(keys, values)}
            return {"action": "status", "held": held, "fleet_held": FLEET_KEY in held, "count": len(held)}
        key = _key(source, product)
        current = ops.mget([key])[0]
        if action == "rearm":
            plan = {"action": "rearm", "key": key, "present": current is not None, "current": current,
                    "by": who, "reason": reason}
            if not confirm:
                return plan
            if current is None:
                return {**plan, "note": "key absent: nothing to re-arm (the source is not held)"}
            ops.delete(key)
            ops.rpush(AUDIT_KEY, json.dumps({"op": "rearm", "key": key, "by": who, "reason": reason, "at": when,
                                             "was": current}))
            return {**plan, "rearmed": True}
        state = json.dumps({"reason": reason, "rate": 0, "window": 0, "tripped_at": when, "by": f"manual:{who}"})
        plan = {"action": "trip", "key": key, "state": json.loads(state), "already_held": current is not None}
        if not confirm:
            return plan
        ops.set(key, state)
        ops.rpush(AUDIT_KEY, json.dumps({"op": "trip", "key": key, "by": who, "reason": reason, "at": when}))
        return {**plan, "tripped": True}
    except RedisOpsError as exc:
        return {"ok": False, "status": "error", "error": str(exc)}


@_toolkit_freshness.refuse_gate("supabase_breaker")
def supabase_breaker(
    action: str = "status",
    *,
    source: str = "",
    product: str = "",
    reason: str = "",
    by: str = "",
    confirm: bool = False,
    ssh_host: str = "noctus-vps",
    executor: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Read / re-arm / trip the Supabase request breaker over prod Redis (no Supabase dependency)."""
    problem = _validate(action, source, product, reason)
    if problem:
        return {"ok": False, "status": "invalid", "error": problem}
    run = executor or _default_executor
    outcome = run(action=action, source=source, product=product, reason=reason, by=by, confirm=confirm,
                  ssh_host=ssh_host)
    if outcome.get("ok") is False:
        return outcome
    if action == "status":
        return {"ok": True, "status": "status", **outcome}
    return {"ok": True, "status": "applied" if confirm else "planned", **outcome}


def register(server) -> None:
    @server.tool(
        name="noctus.dev.supabase_breaker",
        description=(
            "Supabase request breaker, over prod Redis (works when Supabase is down). action=status lists every held "
            "key (noctus:breaker:*, incl. the fleet kill switch); action=rearm source=<fleet|worker:..|scheduler:..> "
            "product=<slug> reason=<required> by=<who> deletes the key so the source restarts; action=trip stops a source "
            "(or ALL background sources with source=fleet) by hand. WRITE (rearm/trip): confirm=False plans, "
            "confirm=True applies and audits. Returns {ok, status, ...}. "
            "KB § PATTERNS/backend/supabase-request-breaker.md"
        ),
    )
    def _supabase_breaker(
        action: str = "status",
        source: str = "",
        product: str = "",
        reason: str = "",
        by: str = "",
        confirm: bool = False,
        ssh_host: str = "noctus-vps",
        allow_stale_toolkit: bool = False,
    ) -> dict:
        return supabase_breaker(action, source=source, product=product, reason=reason, by=by, confirm=confirm,
                                ssh_host=ssh_host, allow_stale_toolkit=allow_stale_toolkit)


__all__ = ["supabase_breaker", "register", "FakeRedisOps", "VpsRedisOps"]
