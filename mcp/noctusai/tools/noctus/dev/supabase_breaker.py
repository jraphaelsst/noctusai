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
_SOURCE_RE = re.compile(r"^(?:worker|scheduler):[A-Za-z0-9_.,:\-]{1,100}$")
_REASON_RE = re.compile(r"^[^\x00-\x1f\x7f]{1,300}$")  # parity with BREAKER_REASON_RE
MARKER_TTL_S = 86_400  # a re-arm marker is read by every process holding the trip: it expires, it is never deleted
MAX_INDEX_MEMBERS = 200
MAX_VALUE_CHARS = 500
AUDIT_CAP = 1000
_PRODUCT_RE = re.compile(r"^[a-z][a-z0-9\-]{0,40}$")
ACTIONS = ("status", "rearm", "trip", "audit")


class RedisOps(Protocol):
    def smembers(self, key: str) -> list[str]: ...

    def srem(self, key: str, member: str) -> None: ...

    def mget(self, keys: list[str]) -> list[str | None]: ...

    def set(self, key: str, value: str, ttl: int | None = None) -> None: ...

    def delete(self, key: str) -> None: ...

    def append_audit(self, key: str, value: str, cap: int) -> None: ...

    def lrange(self, key: str, count: int) -> list[str]: ...


class RedisOpsError(RuntimeError):
    pass


class FakeRedisOps:
    """In-memory Fake of the prod Redis (tests). The per-slug index set mirrors what the products SADD: it is derived
    from the per-source keys present in ``data``."""

    def __init__(self, data: dict[str, str] | None = None) -> None:
        self.data = dict(data or {})
        self.audit: list[str] = []
        self.removed_from_index: set[str] = set()
        self.ttls: dict[str, int | None] = {}
        self.warnings: list[str] = []
        self.fallback: list[str] = []  # services on the app-Redis fallback (tests)
        self.partial: list[str] = []
        self.unverified: list[str] = []

    def fallback_services(self, slugs: list[str]) -> dict[str, list[str]] | None:
        return {"fallback": [s for s in self.fallback if s in slugs],
                "partial_credentials": [s for s in self.partial if s in slugs],
                "unverified": [s for s in self.unverified if s in slugs]}

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

    def set(self, key: str, value: str, ttl: int | None = None) -> None:
        self.data[key] = value
        self.ttls[key] = ttl
        self.removed_from_index.discard(key)

    def delete(self, key: str) -> None:
        self.data.pop(key, None)

    def append_audit(self, key: str, value: str, cap: int) -> None:
        self.audit.append(value)
        del self.audit[:-cap]

    def lrange(self, key: str, count: int) -> list[str]:
        return list(self.audit[-count:])


OPS_PASS_FILE = "/opt/noctus/noctusai/deploy/fleet/redis-auth/ops.pass"
REDIS_ACL_CONTAINER = "noctus-breaker-redis"  # the DEDICATED breaker Redis (feat/redis-acl-lockdown)
REDIS_PLAIN_CONTAINER = "noctus-redis"
_AUTH_ERRORS = ("NOAUTH", "WRONGPASS", "NOPERM")


class VpsRedisOps:
    """`redis-cli` in the Redis container over the shared throttled + circuit-broken SSH chokepoint.

    Branch (probed once per instance): when ``ops.pass`` is readable on the VPS the fleet Redis is behind ACLs
    (feat/redis-acl-lockdown) -> container ``noctus-breaker-redis`` and the ``ops`` user, the secret read ON THE VPS into
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
        """ONE ssh: is the ACL'd Redis container running, and is the ops credential readable? A running ACL Redis
        REQUIRES the ACL path (never a fallback to the unauthenticated one); an unreadable probe raises."""
        if self._acl is None:
            probe = (f"if docker ps --format '{{{{.Names}}}}' | grep -qx {REDIS_ACL_CONTAINER}; then echo ACL_UP; fi; "
                     f"if test -r {OPS_PASS_FILE}; then echo PASS_OK; fi")
            rc, out, err = self._run(probe)
            if rc != 0:
                raise RedisOpsError(f"cannot probe the Redis containers / ops.pass (rc={rc}): {(err or '').strip()[:200]}")
            acl_up, pass_ok = "ACL_UP" in out, "PASS_OK" in out
            if acl_up and not pass_ok:
                raise RedisOpsError(f"{REDIS_ACL_CONTAINER} is running but the ops credential (ops.pass) is not readable "
                                    "on the VPS: refusing to fall back to the unauthenticated Redis")
            self._acl = acl_up or pass_ok
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
        # Detection uses rc + STDERR only: stdout carries product-written values (a value saying "NOAUTH" must not be
        # read as an auth failure, nor hide one). A non-zero rc may carry the redis error on stdout; a zero rc with
        # non-JSON stdout is judged by what that stdout STARTS with.
        head = (err or "").strip() if err.strip() else (out.strip()[:200] if rc != 0 else "")
        if rc != 0:
            denied = next((m for m in _AUTH_ERRORS if m in head), None)
            raise RedisOpsError(f"redis-cli {args[0]} failed (rc={rc}{', ' + denied if denied else ''}): {head[:300]}")
        denied = next((m for m in _AUTH_ERRORS if m in (err or "")), None)
        if denied:
            raise RedisOpsError(f"redis-cli {args[0]} failed ({denied}): {err.strip()[:300]}")
        if args[0] != "--json":  # writers answer OK / an integer: an error reply with rc 0 is judged by its START only
            lead = out.lstrip()
            bad = next((m for m in (*_AUTH_ERRORS, "ERR ", "(error)", "WRONGTYPE") if lead.startswith(m)), None)
            if bad:
                raise RedisOpsError(f"redis-cli {args[0]} failed ({bad}): {lead[:200]}")
        return out

    def _json(self, *args: str):
        out = self._cli("--json", *args)
        try:
            return json.loads(out)
        except ValueError as exc:
            lead = out.strip()
            denied = next((m for m in _AUTH_ERRORS if lead.startswith(m) or lead.startswith("(error) " + m)), None)
            raise RedisOpsError(
                f"redis-cli {args[0]} returned unparseable output{' (' + denied + ')' if denied else ''}: {lead[:120]!r}"
            ) from exc

    def get(self, key: str) -> str | None:
        return self.mget([key])[0]

    def smembers(self, key: str) -> list[str]:
        return sorted(str(m) for m in (self._json("smembers", key) or []))

    def lrange(self, key: str, count: int) -> list[str]:
        return [str(m) for m in (self._json("lrange", key, str(-count), "-1") or [])]

    def fallback_services(self, slugs: list[str]) -> dict[str, list[str]] | None:
        """One ssh: for each live service container (`noctus-<slug>`) classify its breaker Redis configuration:
        ``fallback`` (no `NOCTUS_BREAKER_REDIS_URL`: breaker on the APP Redis), ``partial_credentials`` (URL set but the
        USERNAME or PASSWORD missing: the client refuses to connect unauthenticated and runs degraded), ``unverified``
        (container missing / not inspectable: NOT assumed healthy). None when the ssh itself fails (a warning is kept)."""
        names = " ".join(shlex.quote(s) for s in slugs if _PRODUCT_RE.match(s))
        if not names:
            return {"fallback": [], "partial_credentials": [], "unverified": []}
        script = (
            f"for s in {names}; do c=noctus-$s; "
            "if ! env=$(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' \"$c\" 2>/dev/null); then "
            "echo \"UNVERIFIED:$s\"; continue; fi; "
            "if ! printf '%s\\n' \"$env\" | grep -q '^NOCTUS_BREAKER_REDIS_URL=.'; then echo \"FALLBACK:$s\"; "
            "elif ! printf '%s\\n' \"$env\" | grep -q '^NOCTUS_BREAKER_REDIS_USERNAME=.' "
            "|| ! printf '%s\\n' \"$env\" | grep -q '^NOCTUS_BREAKER_REDIS_PASSWORD=.'; then echo \"PARTIAL:$s\"; fi; done"
        )
        rc, out, err = self._run(script)
        if rc != 0:
            self.warnings.append(f"could not classify the services' breaker Redis config (rc={rc}): {(err or '').strip()[:120]}")
            return None
        result: dict[str, list[str]] = {"fallback": [], "partial_credentials": [], "unverified": []}
        names_map = {"FALLBACK": "fallback", "PARTIAL": "partial_credentials", "UNVERIFIED": "unverified"}
        for line in out.splitlines():
            kind, _, slug = line.strip().partition(":")
            if kind in names_map and _PRODUCT_RE.match(slug):
                result[names_map[kind]].append(slug)
        return {k: sorted(v) for k, v in result.items()}


    def mget(self, keys: list[str]) -> list[str | None]:
        """ONE ssh, ONE MGET (JSON array: nil stays distinguishable from an empty / multi-line value)."""
        if not keys:
            return []
        values = self._json("mget", *keys)
        if not isinstance(values, list) or len(values) != len(keys):
            raise RedisOpsError("redis-cli mget returned an unexpected shape")
        return [None if v is None else str(v) for v in values]

    def set(self, key: str, value: str, ttl: int | None = None) -> None:
        self._cli("set", key, value, *(("EX", str(ttl)) if ttl else ()))

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


_CTRL = re.compile(r"[\x00-\x1f\x7f]")


def _clean(value: Any) -> Any:
    """Product-written values are DATA: strip control characters, cap the length, before echoing them anywhere."""
    if isinstance(value, str):
        return _CTRL.sub("?", value)[:MAX_VALUE_CHARS]
    if isinstance(value, dict):
        return {str(_clean(k)): _clean(v) for k, v in list(value.items())[:20]}
    if isinstance(value, list):
        return [_clean(v) for v in value[:20]]
    return value


def _parse(v: str | None) -> Any:
    if not v:
        return v
    if v.startswith("{"):
        try:
            return _clean(json.loads(v))
        except ValueError:
            pass
    return _clean(v)


def _members_ok(slug: str, members: list[str]) -> list[str]:
    """Index members are written by a product process: keep only well-formed keys of THAT product, and cap them."""
    prefix = f"{PREFIX}{slug}:"
    good = [m for m in members if m.startswith(prefix) and _SOURCE_RE.match(m[len(prefix):])]
    return good[:MAX_INDEX_MEMBERS]


def _audit_identity(who: str) -> dict[str, Any]:
    """Fields the caller cannot choose: the harness session, the OS user, the host (`claimed_by` is just a claim)."""
    import getpass
    import socket

    try:
        os_user = getpass.getuser()
    except Exception:  # noqa: BLE001 - identity must never block a re-arm
        os_user = "unknown"
    return {"claimed_by": who, "session": os.environ.get("CLAUDE_CODE_SESSION_ID", ""), "os_user": os_user,
            "host": socket.gethostname()}


def _validate(action: str, source: str, product: str, reason: str) -> str | None:
    if action not in ACTIONS:
        return f"action must be one of {ACTIONS}"
    if action in ("status", "audit"):
        return None
    if not source:
        return "source is required (fleet | worker:<types> | scheduler:<job>)"
    if source != "fleet":
        if not _SOURCE_RE.match(source):
            return f"source {source!r} is not a holdable source (worker:<types> | scheduler:<job> | fleet)"
        if not _PRODUCT_RE.match(product or ""):
            return "product (the product slug) is required for a per-product source"
    if not _REASON_RE.match(reason or "") or not reason.strip():
        return "reason is required: printable text, no control characters, max 300"
    return None


def _default_executor(*, action: str, source: str, product: str, reason: str, by: str, confirm: bool,
                      ssh_host: str, ops: RedisOps | None = None, now: Callable[[], datetime] | None = None) -> dict[str, Any]:
    ops = ops or VpsRedisOps(ssh_host)
    when = (now or (lambda: datetime.now(timezone.utc)))().isoformat()
    who = (by or os.environ.get("USER") or "unknown").strip()
    try:
        if action == "status":
            # No SCAN (the ops ACL has no +scan): the fleet key + each product's index set `noctus:breaker:<slug>:index`,
            # filtered to well-formed keys of that product, capped, then ONE MGET for every value.
            keys = [FLEET_KEY]
            for slug in ([product] if product else _live_slugs()):
                keys.extend(_members_ok(slug, ops.smembers(f"{PREFIX}{slug}:index")))
            values = ops.mget(keys)
            held = {k: _parse(v) for k, v in zip(keys, values) if v}
            slugs = [product] if product else _live_slugs()
            cfg = ops.fallback_services(slugs) if hasattr(ops, "fallback_services") else None
            return {"action": "status", "held": held, "fleet_held": FLEET_KEY in held, "count": len(held),
                    "on_app_redis_fallback": None if cfg is None else cfg["fallback"],
                    "breaker_credentials_incomplete": None if cfg is None else cfg["partial_credentials"],
                    "unverified_services": None if cfg is None else cfg["unverified"],
                    **({"warnings": list(ops.warnings)} if getattr(ops, "warnings", None) else {}),
                    "note": "per-source keys are listed from the per-product index sets (a key set by hand with "
                            "action=trip is indexed by the product when it observes it)"}
        if action == "audit":
            lists = [AUDIT_KEY] + ([f"{PREFIX}{product}:audit"] if product else [])
            return {"action": "audit", "rows": {k: [_parse(r) for r in ops.lrange(k, 50)] for k in lists}}
        key = _key(source, product)
        current = ops.mget([key])[0]
        if action == "rearm":
            plan = {"action": "rearm", "key": key, "present": current is not None, "current": _parse(current),
                    "claimed_by": who, "reason": reason}
            if not confirm:
                return plan
            if current is None:
                return {**plan, "note": "key absent: nothing to re-arm (the source is not held)"}
            if source != "fleet":
                # the marker the product processes need to release their local hold (a vanished key alone never does)
                parsed = _parse(current)
                tripped_at = parsed.get("tripped_at") if isinstance(parsed, dict) else None
                ops.set(f"{PREFIX}{product}:rearm:{source}", json.dumps(
                    {"tripped_at": tripped_at, "by": f"ops:{who}", "reason": reason, "at": when}), ttl=MARKER_TTL_S)
            ops.delete(key)
            if source != "fleet":
                ops.srem(f"{PREFIX}{product}:index", key)  # keep the index honest (ops has +srem, not +scan)
            ops.append_audit(AUDIT_KEY, json.dumps({"op": "rearm", "key": key, "reason": reason, "at": when,
                                                    "was": _parse(current), **_audit_identity(who)}), AUDIT_CAP)
            return {**plan, "rearmed": True, **({"warnings": list(ops.warnings)} if getattr(ops, "warnings", None) else {})}
        state = json.dumps({"reason": reason, "rate": 0, "window": 0, "tripped_at": when, "by": f"manual:{who}"})
        plan = {"action": "trip", "key": key, "state": json.loads(state), "already_held": current is not None}
        if not confirm:
            return plan
        ops.set(key, state)
        ops.append_audit(AUDIT_KEY, json.dumps({"op": "trip", "key": key, "reason": reason, "at": when,
                                                **_audit_identity(who)}), AUDIT_CAP)
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
    # Steward-class backstop INSIDE the tool (CLI, fresh-subprocess and peer MCP servers all reach here): rearm|trip with
    # confirm=True from a non-steward session is refused; status / audit / dry-runs never are.
    refused = _steward.tool_refusal("noctus.dev.supabase_breaker", {"action": action, "confirm": confirm})
    if refused is not None:
        return refused
    problem = _validate(action, source, product, reason)
    if problem:
        return {"ok": False, "status": "invalid", "error": problem}
    run = executor or _default_executor
    outcome = run(action=action, source=source, product=product, reason=reason, by=by, confirm=confirm,
                  ssh_host=ssh_host)
    if outcome.get("ok") is False:
        return outcome
    if action in ("status", "audit"):
        return {"ok": True, "status": action, **outcome}
    return {"ok": True, "status": "applied" if confirm else "planned", **outcome}


def register(server) -> None:
    @server.tool(
        name="noctus.dev.supabase_breaker",
        description=(
            "Supabase request breaker, over prod Redis (works when Supabase is down). action=status lists every held "
            "key (noctus:breaker:*, incl. the fleet kill switch); action=rearm source=<fleet|worker:..|scheduler:..> "
            "product=<slug> reason=<required> by=<who> deletes the key so the source restarts; action=audit lists the audit rows; action=trip stops a source "
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
