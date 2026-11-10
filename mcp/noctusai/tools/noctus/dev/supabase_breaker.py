"""noctus.dev.supabase_breaker - read / re-arm / trip the Supabase request breaker over prod Redis, independent of Supabase.

The seed breaker (`noctusai_lib.primitives.supabase_breaker`, KB § PATTERNS/backend/supabase-request-breaker.md) keeps its
trips in Redis keys ``noctus:breaker:<product>:<source>`` and the fleet kill switch ``noctus:breaker:fleet``. This tool is
the human surface that works when Supabase is the thing that is down (the platform-admin route needs Supabase for its
role read): it talks to ``noctus-redis`` over the toolkit's throttled SSH chokepoint.

  action=status                         every held key + its state (read-only)
  action=rearm source=<s> [product=<p>] reason=<why> [by=<who>]   DEL the key + audit row. WRITE.
  action=trip  source=<s> [product=<p>] reason=<why> [by=<who>]    SET the key by hand (``source=fleet`` = stop EVERYTHING; ops-only, the platform-admin route refuses it).

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
from pathlib import Path
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any, Protocol

from . import release_steward as _steward
from . import toolkit_freshness as _toolkit_freshness

PREFIX = "noctus:breaker:"
FLEET_KEY = f"{PREFIX}fleet"
AUDIT_KEY = f"{PREFIX}audit"
# parity with noctusai_lib.primitives.supabase_breaker.BREAKER_SOURCE_RE (a test pins it); `fleet` is handled apart
_SOURCE_RE = re.compile(r"^(?:(?:worker|scheduler|gate):[A-Za-z0-9_.,:\-]{1,100}|unattributed|startup)$")
AUDIT_CAP = 1000
_PRODUCT_RE = re.compile(r"^[a-z][a-z0-9\-]{0,40}$")
ACTIONS = ("status", "rearm", "trip")


class RedisOps(Protocol):
    def smembers(self, key: str) -> list[str]: ...

    def srem(self, key: str, member: str) -> None: ...

    def mget(self, keys: list[str]) -> list[str | None]: ...

    def set(self, key: str, value: str) -> None: ...

    def delete(self, key: str) -> None: ...

    def append_audit(self, key: str, value: str, cap: int) -> None: ...


class RedisOpsError(RuntimeError):
    pass


class FakeRedisOps:
    """In-memory Fake of the prod Redis (tests). The per-slug index set mirrors what the products SADD: it is derived
    from the per-source keys present in ``data``."""

    def __init__(self, data: dict[str, str] | None = None) -> None:
        self.data = dict(data or {})
        self.audit: list[str] = []
        self.removed_from_index: set[str] = set()

    def smembers(self, key: str) -> list[str]:
        prefix = key.removesuffix("index")
        return sorted(k for k in self.data if k.startswith(prefix) and k != key and not k.endswith((":index", ":audit"))
                      and k not in self.removed_from_index and k != FLEET_KEY)

    def srem(self, key: str, member: str) -> None:
        self.removed_from_index.add(member)

    def get(self, key: str) -> str | None:
        return self.data.get(key)

    def mget(self, keys: list[str]) -> list[str | None]:
        return [self.data.get(k) for k in keys]

    def set(self, key: str, value: str) -> None:
        self.data[key] = value
        self.removed_from_index.discard(key)

    def delete(self, key: str) -> None:
        self.data.pop(key, None)

    def append_audit(self, key: str, value: str, cap: int) -> None:
        self.audit.append(value)
        del self.audit[:-cap]


OPS_PASS_FILE = "/opt/noctus/noctusai/deploy/fleet/redis-auth/ops.pass"
REDIS_ACL_CONTAINER = "noctus-redis-acl"
REDIS_PLAIN_CONTAINER = "noctus-redis"
_AUTH_ERRORS = ("NOAUTH", "WRONGPASS", "NOPERM")


class VpsRedisOps:
    """`redis-cli` in the Redis container over the shared throttled + circuit-broken SSH chokepoint.

    Branch (probed once per instance): when ``ops.pass`` is readable on the VPS the fleet Redis is behind ACLs
    (feat/redis-acl-lockdown) -> container ``noctus-redis-acl`` and the ``ops`` user, the secret read ON THE VPS into
    ``REDISCLI_AUTH`` (never sent over SSH, never on argv). Otherwise today's unauthenticated ``noctus-redis``. A probe
    that cannot reach the host raises: an ssh failure must never silently select the unauthenticated Redis.
    Key enumeration never SCANs (the ops ACL has no ``+scan``): per-product index sets ``noctus:breaker:<slug>:index``."""

    def __init__(self, ssh_host: str = "noctus-vps", container: str | None = None, runner: Callable | None = None) -> None:
        self._host, self._container, self._runner = ssh_host, container, runner
        self._acl: bool | None = None
        self.warnings: list[str] = []

    def _run(self, cmd: str):
        from ._vps_ssh import run_remote

        return (self._runner or run_remote)(self._host, cmd)

    def _use_acl(self) -> bool:
        if self._acl is None:
            rc, _out, err = self._run(f"test -r {OPS_PASS_FILE}")
            if rc not in (0, 1):
                raise RedisOpsError(f"cannot tell whether the Redis ACL ops.pass exists (rc={rc}): {(err or '').strip()[:200]}")
            self._acl = rc == 0
        return self._acl

    def _cli(self, *args: str) -> str:
        acl = self._use_acl()
        quoted = " ".join(shlex.quote(a) for a in args)
        if acl:
            container = self._container or REDIS_ACL_CONTAINER
            cmd = (f'REDISCLI_AUTH="$(cat {OPS_PASS_FILE})" docker exec -e REDISCLI_AUTH {shlex.quote(container)} '
                   f"redis-cli --no-auth-warning --user ops {quoted}")
        else:
            container = self._container or REDIS_PLAIN_CONTAINER
            cmd = f"docker exec {shlex.quote(container)} redis-cli {quoted}"
        rc, out, err = self._run(cmd)
        text = f"{out}\n{err}"
        denied = next((m for m in _AUTH_ERRORS if m in text), None)
        if rc != 0 or denied or "ERR" in out.split("\n", 1)[0][:4]:
            raise RedisOpsError(f"redis-cli {args[0]} failed (rc={rc}{', ' + denied if denied else ''}): "
                                f"{(err or out).strip()[:300]}")
        return out

    def get(self, key: str) -> str | None:
        return self._cli("get", key).rstrip("\n") or None

    def smembers(self, key: str) -> list[str]:
        return sorted(m for m in self._cli("smembers", key).splitlines() if m.strip())

    def mget(self, keys: list[str]) -> list[str | None]:
        # one GET per key: redis-cli's MGET output cannot distinguish an empty line from nil with multi-line values
        return [self.get(k) for k in keys]

    def set(self, key: str, value: str) -> None:
        self._cli("set", key, value)

    def delete(self, key: str) -> None:
        self._cli("del", key)

    def srem(self, key: str, member: str) -> None:
        self._cli("srem", key, member)

    def append_audit(self, key: str, value: str, cap: int) -> None:
        self._cli("rpush", key, value)
        try:
            self._cli("ltrim", key, str(-cap), "-1")  # capped audit list
        except RedisOpsError as exc:  # the row IS written; a denied/failed cap must be loud, never undo a re-arm
            self.warnings.append(f"audit cap (ltrim) not applied: {exc}")


def _live_slugs() -> list[str]:
    """The catalog-live product slugs (deploy/fleet/build-scope.txt, derived — never a hand list) + core."""
    root = Path(__file__).resolve().parents[5]
    try:
        names = [ln.strip() for ln in (root / "deploy/fleet/build-scope.txt").read_text().splitlines()
                 if ln.strip() and not ln.startswith("#")]
    except OSError as exc:
        raise RedisOpsError(f"cannot list the live products (deploy/fleet/build-scope.txt): {exc}; pass product=") from exc
    return sorted(set(names) | {"core"})


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
            # No SCAN (the ops ACL has no +scan): the fleet key + each product's index set `noctus:breaker:<slug>:index`.
            keys = [FLEET_KEY]
            for slug in ([product] if product else _live_slugs()):
                keys.extend(ops.smembers(f"{PREFIX}{slug}:index"))
            values = ops.mget(keys)
            held = {k: (json.loads(v) if v and v.startswith("{") else v) for k, v in zip(keys, values) if v}
            return {"action": "status", "held": held, "fleet_held": FLEET_KEY in held, "count": len(held),
                    "note": "per-source keys are listed from the per-product index sets (a key set by hand with "
                            "action=trip is indexed by the product when it observes it)"}
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
            if source != "fleet":
                ops.srem(f"{PREFIX}{product}:index", key)  # keep the index honest (ops has +srem, not +scan)
            ops.append_audit(AUDIT_KEY, json.dumps({"op": "rearm", "key": key, "by": who, "reason": reason, "at": when,
                                                    "was": current}), AUDIT_CAP)
            return {**plan, "rearmed": True, **({"warnings": list(ops.warnings)} if getattr(ops, "warnings", None) else {})}
        state = json.dumps({"reason": reason, "rate": 0, "window": 0, "tripped_at": when, "by": f"manual:{who}"})
        plan = {"action": "trip", "key": key, "state": json.loads(state), "already_held": current is not None}
        if not confirm:
            return plan
        ops.set(key, state)
        ops.append_audit(AUDIT_KEY, json.dumps({"op": "trip", "key": key, "by": who, "reason": reason, "at": when}),
                         AUDIT_CAP)
        return {**plan, "tripped": True, **({"warnings": list(ops.warnings)} if getattr(ops, "warnings", None) else {})}
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
        # Steward-class backstop (rearm|trip with confirm=True), same shape as deploy_image / migrate_product: the
        # PreToolUse hook covers the harness; this covers a peer's MCP server. status / dry-runs are never refused.
        refused = _steward.tool_refusal("noctus.dev.supabase_breaker", {"action": action, "confirm": confirm})
        if refused is not None:
            return refused
        return supabase_breaker(action, source=source, product=product, reason=reason, by=by, confirm=confirm,
                                ssh_host=ssh_host, allow_stale_toolkit=allow_stale_toolkit)


__all__ = ["supabase_breaker", "register", "FakeRedisOps", "VpsRedisOps"]
