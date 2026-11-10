"""Supabase request breaker — count every REST call per SOURCE, stop a runaway background source.

Born 2026-11-10 from the Supabase egress incident (`KB § PATTERNS/backend/polling-request-budget.md`): our own
background loops made ~620k REST calls/day on the Free plan and Supabase cut the whole project off (HTTP 402 on every
call, every product). Nothing noticed until it was dead. Owner: "we stop and ALERT, the process is killed and we
evaluate". This module is the pure core; the IO (Redis state, owner email) is injected — see
`noctusai_lib.integrations.supabase_breaker_io` — and the seed framework wires it for every product.

How it works
------------
* COUNT. The shared httpx transport every seed-built Supabase client rides (`integrations.http_pool.TimingTransport`)
  calls :func:`record_call` once per ``rest`` call. No network, no allocation beyond a 1-second bucket: a contextvar
  read, a lock, an int increment. The SOURCE comes from a contextvar: ``worker:<job types>`` (set by the jobs Worker),
  ``scheduler:<job>`` (set by the seed scheduler wrapper), default ``http`` (request handlers, user traffic).
* BUDGET. A background source trips when its sustained rate exceeds a window budget (default 300 calls / 5 min =
  1/s, or 2,000 / 1 h). ``http`` is NEVER stopped: it only ALERTS above its own threshold (6,000 / 5 min / process).
* TRIP. The source is held in memory at once (it stops even with Redis down), the trip is persisted to Redis
  (``noctus:breaker:<product>:<source>``, no TTL — survives restarts) and the owner is alerted once per trip (a failed
  alert is kept and retried, never swallowed). A held source does not start on boot.
* FLEET KEY ``noctus:breaker:fleet`` holds EVERY background source of EVERY product until a human removes it. Read from
  Redis at most every ``fleet_ttl_s`` (10 s) per process, never from Supabase; an unreadable key fails OPEN, loudly.
* RE-ARM is human-only and needs a reason (:meth:`Breaker.rearm`, the platform-admin route, the MCP tool).

A trip stops the RUNAWAY PROCESS (the source), never the product: the API keeps serving.
"""
from __future__ import annotations

import contextlib
import contextvars
import json
import logging
import os
import re
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Iterator, Optional, Protocol

from noctusai_lib.primitives.not_configured import IntegrationNotConfigured

logger = logging.getLogger(__name__)

__all__ = [
    "BREAKER_AUDIT_KEY",
    "BREAKER_AUDIT_CAP",
    "BREAKER_KEY_PREFIX",
    "BREAKER_SOURCE_RE",
    "BreakerOpen",
    "STARTUP_SOURCE",
    "DEFAULT_STARTUP_RULES",
    "UNATTRIBUTED_SOURCE",
    "guard",
    "BREAKER_FLEET_KEY",
    "DEFAULT_BACKGROUND_RULES",
    "DEFAULT_HTTP_RULE",
    "Breaker",
    "BreakerAlertNotConfigured",
    "BreakerAlerter",
    "BreakerConfig",
    "BreakerStore",
    "BudgetRule",
    "HTTP_SOURCE",
    "InMemoryBreakerStore",
    "RecordingAlerter",
    "UnconfiguredAlerter",
    "configure_breaker",
    "current_source",
    "get_breaker",
    "is_background",
    "record_call",
    "reset_breaker_for_tests",
    "source_scope",
]

HTTP_SOURCE = "http"
#: A Supabase call made outside ANY declared scope (a lifespan `create_task` loop, a bare `Thread(...)`): budgeted and
#: trippable exactly like a background source. Request handlers are `http` EXPLICITLY (SupabaseSourceMiddleware), so
#: "no scope" can never mean "user traffic, never stopped" (security review F5, 2026-11-10).
# NOC-REMEDIATE[breaker-unscoped-loop]: a keeper flagging a lifespan/startup `create_task(` or `Thread(` that makes Supabase calls without `source_scope(...)` — destination: the polling-budget keeper (feat/polling-budget-keeper) — 2026-11-10
UNATTRIBUTED_SOURCE = "unattributed"
#: The seed lifespan STARTUP (organ registration, notification-catalog publish, the product's `lifespan_startup` hook):
#: its own source so a heavy boot can never trip `unattributed` and then have EVERY unscoped call refused (a boot that
#: breaks the app). Budget = a generous short burst, but the hour cap stays the background one, so a loop that inherits
#: this scope from a task created during startup (contextvars copy into tasks) is still bounded.
STARTUP_SOURCE = "startup"
BREAKER_KEY_PREFIX = "noctus:breaker:"
BREAKER_FLEET_KEY = f"{BREAKER_KEY_PREFIX}fleet"
BREAKER_AUDIT_KEY = f"{BREAKER_KEY_PREFIX}audit"
BREAKER_AUDIT_CAP = 1000
#: THE shape of a holdable source name (routes, MCP tool and the Redis key all validate against this one regex;
#: `fleet` and `http` are deliberately NOT in it — the fleet key is ops-only, http is never held).
BREAKER_SOURCE_RE = re.compile(r"^(?:(?:worker|scheduler|gate):[A-Za-z0-9_.,:\-]{1,100}|unattributed|startup)$")
_MAX_WINDOW_S = 3600


@dataclass(frozen=True)
class BudgetRule:
    """At most ``max_calls`` in any sliding ``window_s`` seconds."""

    window_s: int
    max_calls: int

    def __post_init__(self) -> None:
        if not (1 <= self.window_s <= _MAX_WINDOW_S) or self.max_calls < 1:
            raise ValueError(f"BudgetRule needs 1<=window_s<={_MAX_WINDOW_S} and max_calls>=1: {self}")


#: 300 / 5 min = 1 call/s sustained; 2,000 / 1 h = 0.55/s sustained. The canonical answer (owner, 2026-11-10).
DEFAULT_BACKGROUND_RULES: tuple[BudgetRule, ...] = (BudgetRule(300, 300), BudgetRule(3600, 2000))
#: user traffic: ALERT only, never stop.
DEFAULT_HTTP_RULE = BudgetRule(300, 6000)
#: Sized from what boot does: the seed's own boot is ~2 Supabase calls (one batched `scheduler_jobs` upsert, one
#: batched notification-kinds upsert); product recovery hooks are the unknown, so 1,500 calls / 60 s (~750x the seed's
#: own need). Hour cap = the background one.
DEFAULT_STARTUP_RULES: tuple[BudgetRule, ...] = (BudgetRule(60, 1500), BudgetRule(3600, 2000))


def is_background(source: str) -> bool:
    return source != HTTP_SOURCE


@dataclass
class BreakerConfig:
    """Budgets per source. ``overrides`` maps an EXACT source name to its rules; everything else uses the defaults.

    Env ``NOCTUS_BREAKER_BUDGETS`` = JSON ``{"worker:transcricao": [[300, 600], [3600, 4000]]}`` (a per-source
    override, never a way to switch the breaker off — a rule list may not be empty)."""

    background_rules: tuple[BudgetRule, ...] = DEFAULT_BACKGROUND_RULES
    http_rule: BudgetRule = DEFAULT_HTTP_RULE
    overrides: dict[str, tuple[BudgetRule, ...]] = field(default_factory=dict)
    startup_rules: tuple[BudgetRule, ...] = DEFAULT_STARTUP_RULES

    def rules_for(self, source: str) -> tuple[BudgetRule, ...]:
        if source in self.overrides:
            return self.overrides[source]
        if source == STARTUP_SOURCE:
            return self.startup_rules
        return (self.http_rule,) if source == HTTP_SOURCE else self.background_rules

    @classmethod
    def from_env(cls, environ: Optional[dict[str, str]] = None) -> "BreakerConfig":
        raw = (environ if environ is not None else os.environ).get("NOCTUS_BREAKER_BUDGETS", "").strip()
        if not raw:
            return cls()
        try:
            parsed = json.loads(raw)
            overrides = {
                str(src): tuple(BudgetRule(int(w), int(m)) for w, m in rules)
                for src, rules in parsed.items()
            }
            if any(not rules for rules in overrides.values()):
                raise ValueError("a source override needs at least one rule")
        except Exception as exc:  # noqa: BLE001 -- loud, then the canonical defaults (never a silent partial config)
            logger.error("NOCTUS_BREAKER_BUDGETS is invalid (%s: %s) — using the default budgets", type(exc).__name__, exc)
            return cls()
        return cls(overrides=overrides)


# --- source attribution ----------------------------------------------------------------------------------------

_SOURCE: contextvars.ContextVar[str] = contextvars.ContextVar("noctus_supabase_source", default=UNATTRIBUTED_SOURCE)


def current_source() -> str:
    return _SOURCE.get()


@contextlib.contextmanager
def source_scope(source: str) -> Iterator[None]:
    """Attribute every Supabase call made inside the block (and in threads/tasks it spawns) to ``source``."""
    token = _SOURCE.set(source)
    try:
        yield
    finally:
        _SOURCE.reset(token)


# --- IO seams (implementations in integrations/supabase_breaker_io.py) ------------------------------------------


class BreakerStore(Protocol):
    """Sync key/value store for trip state. Every method may raise on an unreachable backend."""

    def get(self, key: str) -> Optional[str]: ...

    def mget(self, keys: list[str]) -> list[Optional[str]]: ...

    def set(self, key: str, value: str) -> None: ...

    def delete(self, key: str) -> None: ...

    def append_audit(self, key: str, value: str, cap: int) -> None: ...


class BreakerAlerter(Protocol):
    """Sends the owner alert through a channel that does NOT depend on Supabase. Raises on failure."""

    def send(self, subject: str, body: str) -> None: ...


class BreakerOpen(RuntimeError):
    """Raised by the HTTP transport when the current background source is HELD: the call is refused before it leaves
    the process, so a job already in flight fails fast instead of running on until it returns. The jobs Worker treats
    it as "release the job", never as a failure that burns retries."""

    def __init__(self, source: str, reason: str = "") -> None:
        super().__init__(f"supabase breaker is OPEN for {source!r}: {reason or 'held until a human re-arms'}")
        self.source = source
        self.reason = reason


class BreakerAlertNotConfigured(RuntimeError, IntegrationNotConfigured):
    """The alert channel has no credentials/recipient (named in the message)."""


class UnconfiguredAlerter:
    """Default until the framework installs a real one: every send fails LOUDLY (and is kept for retry)."""

    def send(self, subject: str, body: str) -> None:
        raise BreakerAlertNotConfigured("no breaker alerter installed (configure_breaker not called)")


class RecordingAlerter:
    """Test/dev Fake: records alerts; ``fail`` makes the next sends raise."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []
        self.fail = False

    def send(self, subject: str, body: str) -> None:
        if self.fail:
            raise RuntimeError("alert channel down")
        self.sent.append((subject, body))


class InMemoryBreakerStore:
    """Test/dev Fake of the Redis store. ``down`` makes every call raise (an unreachable Redis)."""

    def __init__(self) -> None:
        self.data: dict[str, str] = {}
        self.audit: list[str] = []
        self.down = False
        self.calls = 0

    def _guard(self) -> None:
        self.calls += 1
        if self.down:
            raise ConnectionError("redis unreachable")

    def get(self, key: str) -> Optional[str]:
        self._guard()
        return self.data.get(key)

    def mget(self, keys: list[str]) -> list[Optional[str]]:
        self._guard()
        return [self.data.get(k) for k in keys]

    def set(self, key: str, value: str) -> None:
        self._guard()
        self.data[key] = value

    def delete(self, key: str) -> None:
        self._guard()
        self.data.pop(key, None)

    def append_audit(self, key: str, value: str, cap: int) -> None:
        self._guard()
        self.audit.append(value)
        del self.audit[:-cap]


# --- the breaker -----------------------------------------------------------------------------------------------


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


@dataclass
class Trip:
    source: str
    reason: str
    rate: float
    window: int
    tripped_at: str
    by: str = "auto"
    persisted: bool = False
    persisted_at: float = 0.0  # monotonic; guards a refresh that raced the write

    def as_json(self) -> str:
        return json.dumps({"reason": self.reason, "rate": round(self.rate, 3), "window": self.window,
                           "tripped_at": self.tripped_at, "by": self.by})


def _parse_trip(source: str, raw: str) -> dict[str, Any]:
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return {"source": source, **data}
    except (TypeError, ValueError):
        pass
    return {"source": source, "reason": f"unparseable breaker state: {raw[:120]!r}", "by": "unknown"}


class Breaker:
    """Per-process breaker. One instance per process (see :func:`get_breaker`); tests build their own."""

    def __init__(
        self,
        *,
        slug: str = "unknown",
        config: Optional[BreakerConfig] = None,
        store: Optional[BreakerStore] = None,
        alerter: Optional[BreakerAlerter] = None,
        event_sink: Optional[Callable[[dict[str, Any]], None]] = None,
        clock: Callable[[], float] = time.monotonic,
        wall: Callable[[], float] = time.time,
        sync_io: bool = False,
        fleet_ttl_s: float = 10.0,
        http_alert_cooldown_s: float = 3600.0,
    ) -> None:
        self.slug = slug
        self._config = config or BreakerConfig()
        self._store = store
        self._alerter: BreakerAlerter = alerter or UnconfiguredAlerter()
        self._event_sink = event_sink
        self._clock = clock
        self._wall = wall
        self._sync_io = sync_io  # tests: do the store write + alert inline instead of on a daemon thread
        self._fleet_ttl = fleet_ttl_s
        self._http_cooldown = http_alert_cooldown_s

        self._lock = threading.RLock()
        self._buckets: dict[str, deque[list[int]]] = {}  # source -> deque of [second, count]
        self._rules: dict[str, tuple[BudgetRule, ...]] = {}
        self._bases: dict[str, list[int]] = {}
        self._trips: dict[str, Trip] = {}
        self._remote_held: dict[str, dict[str, Any]] = {}
        self._known: set[str] = set()
        self._fleet: Optional[dict[str, Any]] = None
        self._last_refresh: Optional[float] = None
        self._store_down = False
        self._subs: dict[str, list[Callable[[], None]]] = {}
        self.pending_alerts: list[tuple[str, str, str]] = []  # (dedupe_key, subject, body)
        self._alerted: set[str] = set()
        self._http_alerted_at: Optional[float] = None
        self.sent_alerts = 0

    # ---- configuration ----------------------------------------------------------------------------------------

    @property
    def key_prefix(self) -> str:
        return f"{BREAKER_KEY_PREFIX}{self.slug}:"

    def key_for(self, source: str) -> str:
        return f"{self.key_prefix}{source}"

    def configure(self, *, slug: Optional[str] = None, store: Optional[BreakerStore] = None,
                  alerter: Optional[BreakerAlerter] = None,
                  event_sink: Optional[Callable[[dict[str, Any]], None]] = None,
                  config: Optional[BreakerConfig] = None) -> None:
        with self._lock:
            if slug is not None:
                self.slug = slug
            if store is not None:
                self._store = store
            if alerter is not None:
                self._alerter = alerter
            if event_sink is not None:
                self._event_sink = event_sink
            if config is not None:
                self._config = config

    # ---- counting (the hot path) ------------------------------------------------------------------------------

    def record_call(self, source: Optional[str] = None) -> None:
        """Count ONE Supabase REST call. In-memory only: no network, O(rules); the budget is checked on EVERY call
        against running per-window bases (rebuilt once per second), so a tight loop trips at exactly budget+1."""
        src = source or _SOURCE.get()
        now = int(self._clock())
        verdict: Optional[tuple[BudgetRule, int]] = None
        with self._lock:
            dq = self._buckets.get(src)
            if dq is None:
                dq = self._buckets[src] = deque()
            if not dq or dq[-1][0] != now:
                horizon = now - _MAX_WINDOW_S
                while dq and dq[0][0] <= horizon:
                    dq.popleft()
                rules = self._config.rules_for(src)
                self._rules[src] = rules
                self._bases[src] = [sum(n for sec, n in dq if sec > now - r.window_s) for r in rules]
                dq.append([now, 0])
            dq[-1][1] += 1
            cur = dq[-1][1]
            for rule, base in zip(self._rules[src], self._bases[src]):
                total = base + cur
                if total > rule.max_calls and (verdict is None or total / rule.window_s > verdict[1] / verdict[0].window_s):
                    verdict = (rule, total)
        if verdict is None:
            return
        rule, count = verdict
        reason = f"{count} Supabase calls in {rule.window_s}s exceeds the budget of {rule.max_calls}"
        rate = count / rule.window_s
        if is_background(src):
            self.trip(src, reason=reason, rate=rate, window=rule.window_s)
        else:
            self._alert_http(reason, rate, rule.window_s)

    def credit(self, source: str, calls: int) -> None:
        """Refund ``calls`` from ``source``'s window: PRODUCTIVE work earns its own headroom. The jobs Worker credits a
        job type per processed job, so a busy-but-productive worker (backlog drain, webhook surge) is never tripped
        while a loop that burns calls without finishing work still is."""
        if calls <= 0:
            return
        now = int(self._clock())
        with self._lock:
            dq = self._buckets.setdefault(source, deque())
            if not dq or dq[-1][0] != now:
                self._rules[source] = self._config.rules_for(source)
                self._bases[source] = [sum(n for sec, n in dq if sec > now - r.window_s) for r in self._rules[source]]
                dq.append([now, 0])
            dq[-1][1] -= calls

    def is_open(self, source: str) -> bool:
        """Hot-path hold check (in-memory, lock-free dict reads, no IO). ``http`` is never open."""
        if source == HTTP_SOURCE:
            return False
        return source in self._trips or self._fleet is not None or source in self._remote_held

    def guard(self, source: Optional[str] = None) -> None:
        """Raise :class:`BreakerOpen` when the (current) background source is held."""
        src = source or _SOURCE.get()
        if self.is_open(src):
            hold = self.hold_reason(src) or {}
            raise BreakerOpen(src, str(hold.get("reason", "")))

    def count(self, source: str, window_s: int) -> int:
        """Calls recorded for ``source`` in the last ``window_s`` seconds (diagnostics/tests)."""
        now = int(self._clock())
        with self._lock:
            return sum(n for sec, n in self._buckets.get(source, ()) if sec > now - window_s)

    # ---- trip -------------------------------------------------------------------------------------------------

    def trip(self, source: str, *, reason: str, rate: float = 0.0, window: int = 0, by: str = "auto") -> bool:
        """Hold ``source`` (idempotent). Returns True when this call created the trip."""
        if not is_background(source):
            raise ValueError("the http source is alert-only: it can never be tripped")
        with self._lock:
            if source in self._trips:
                return False
            trip = Trip(source=source, reason=reason, rate=rate, window=window,
                        tripped_at=_iso(self._wall()), by=by)
            self._trips[source] = trip
            self._known.add(source)
            subs = list(self._subs.get(source, ()))
        logger.critical("SUPABASE BREAKER TRIPPED source=%s product=%s: %s — the source is STOPPED until a human "
                        "re-arms it (platform-admin route or noctus.dev.supabase_breaker rearm)",
                        source, self.slug, reason)
        for cb in subs:
            self._call_sub(cb)
        if by != "auto":
            self.audit("trip", self.key_for(source), by=by, reason=reason)
        self._io(self._persist_and_alert, trip)
        return True

    def audit(self, op: str, key: str, *, by: str, reason: str) -> None:
        """Best-effort audit row (who/why/when) on the capped Redis list; the MCP tool writes the same shape."""
        row = {"op": op, "key": key, "by": by, "reason": reason, "at": _iso(self._wall())}
        if self._store is None:
            return
        try:
            self._store.append_audit(BREAKER_AUDIT_KEY, json.dumps(row), BREAKER_AUDIT_CAP)
        except Exception:  # noqa: BLE001 -- the audit must not undo a trip/re-arm; loud, not silent
            logger.error("breaker: audit row not written for %s %s", op, key, exc_info=True)

    def _persist_and_alert(self, trip: Trip) -> None:
        store_error: Optional[str] = None
        if self._store is None:
            store_error = "no breaker store configured"
        else:
            try:
                self._store.set(self.key_for(trip.source), trip.as_json())
                trip.persisted = True
                trip.persisted_at = self._clock()
            except Exception as exc:  # noqa: BLE001 -- never block the trip; named in the alert, logged loudly
                store_error = f"{type(exc).__name__}: {exc}"
        if store_error:
            logger.error("breaker: trip for %s is held IN MEMORY ONLY (Redis write failed: %s) — it will not survive "
                         "a restart and other processes do not see it", trip.source, store_error)
        self._emit_event({"event": "breaker.tripped", "product": self.slug, "source": trip.source,
                          "reason": trip.reason, "rate": trip.rate, "window": trip.window, "by": trip.by,
                          "persisted": trip.persisted})
        subject = f"[NoctusAI] Supabase breaker TRIPPED: {self.slug} {trip.source}"
        body = (f"Product: {self.slug}\nSource: {trip.source}\nReason: {trip.reason}\n"
                f"Rate: {trip.rate:.2f} calls/s over {trip.window}s\nTripped at: {trip.tripped_at}\nBy: {trip.by}\n\n"
                f"The runaway source is STOPPED; the API keeps serving. Evaluate, fix, then re-arm: "
                f"noctus.dev.supabase_breaker action=rearm source={trip.source} product={self.slug} reason=...\n"
                + (f"\nWARNING: the trip was NOT persisted to Redis ({store_error}); it is held in this process only."
                   if store_error else ""))
        self._alert(f"trip:{self.slug}:{trip.source}:{trip.tripped_at}", subject, body)

    def _alert_http(self, reason: str, rate: float, window: int) -> None:
        now = self._clock()
        with self._lock:
            if self._http_alerted_at is not None and now - self._http_alerted_at < self._http_cooldown:
                return
            self._http_alerted_at = now
        logger.error("breaker: http (user traffic) %s in %s — ALERT only, never stopped", reason, self.slug)
        self._io(self._alert, f"http:{self.slug}:{int(self._wall())}",
                 f"[NoctusAI] Supabase http traffic high: {self.slug}",
                 f"Product: {self.slug}\nSource: http (request handlers; never stopped)\nReason: {reason}\n"
                 f"Rate: {rate:.2f} calls/s over {window}s\nEvaluate whether this is a loop or a real traffic spike.")

    # ---- alert (dedupe + retry; failure is loud and kept) ------------------------------------------------------

    def _alert(self, dedupe_key: str, subject: str, body: str) -> bool:
        with self._lock:
            if dedupe_key in self._alerted:
                return True
            self._alerted.add(dedupe_key)
        try:
            self._alerter.send(subject, body)
            self.sent_alerts += 1
            return True
        except Exception as exc:  # noqa: BLE001 -- kept for retry and logged at CRITICAL: an unseen alert is the incident
            logger.critical("breaker: OWNER ALERT NOT SENT (%s: %s) — kept for retry; subject=%r",
                            type(exc).__name__, exc, subject)
            with self._lock:
                self.pending_alerts.append((dedupe_key, subject, body))
            self._ensure_retry_thread()
            return False

    def flush_pending_alerts(self) -> int:
        """Retry every alert that failed. Returns how many are STILL pending."""
        with self._lock:
            batch, self.pending_alerts = self.pending_alerts, []
        for dedupe_key, subject, body in batch:
            with self._lock:
                self._alerted.discard(dedupe_key)
            self._alert(dedupe_key, subject, body)
        with self._lock:
            return len(self.pending_alerts)

    _retry_thread: Optional[threading.Thread] = None

    def _ensure_retry_thread(self) -> None:
        if self._sync_io:
            return
        with self._lock:
            if self._retry_thread is not None and self._retry_thread.is_alive():
                return

            def _loop() -> None:
                delay = 30.0
                while True:
                    time.sleep(delay)
                    if self.flush_pending_alerts() == 0:
                        return
                    delay = min(delay * 2, 900.0)

            self._retry_thread = threading.Thread(target=_loop, name="breaker-alert-retry", daemon=True)
            self._retry_thread.start()

    def _emit_event(self, event: dict[str, Any]) -> None:
        logger.warning("breaker_event %s", json.dumps(event, default=str, sort_keys=True))
        sink = self._event_sink
        if sink is None:
            return
        try:
            sink(event)
        except Exception:  # noqa: BLE001 -- best effort: Supabase may be the thing that is down
            logger.error("breaker: event sink failed for %s", event.get("event"), exc_info=True)

    def _io(self, fn: Callable[..., Any], *args: Any) -> None:
        if self._sync_io:
            fn(*args)
            return
        threading.Thread(target=fn, args=args, name="breaker-io", daemon=True).start()

    @staticmethod
    def _call_sub(cb: Callable[[], None]) -> None:
        try:
            cb()
        except Exception:  # noqa: BLE001 -- a broken subscriber must not stop the others
            logger.error("breaker: subscriber failed", exc_info=True)

    # ---- hold state -------------------------------------------------------------------------------------------

    def register_source(self, source: str) -> None:
        with self._lock:
            self._known.add(source)

    def subscribe(self, source: str, callback: Callable[[], None]) -> Callable[[], None]:
        """``callback`` fires (from any thread) when ``source`` becomes held. Returns an unsubscribe function."""
        with self._lock:
            self._subs.setdefault(source, []).append(callback)

        def _off() -> None:
            with self._lock:
                with contextlib.suppress(ValueError, KeyError):
                    self._subs[source].remove(callback)

        return _off

    def hold_reason(self, source: str) -> Optional[dict[str, Any]]:
        """Why ``source`` is held, from the in-process view (no IO), or None. ``http`` is never held."""
        if not is_background(source):
            return None
        with self._lock:
            trip = self._trips.get(source)
            if trip is not None:
                return {"source": source, "scope": "source", "reason": trip.reason, "by": trip.by,
                        "tripped_at": trip.tripped_at, "persisted": trip.persisted}
            if self._fleet is not None:
                return {"source": source, "scope": "fleet", **self._fleet}
            remote = self._remote_held.get(source)
            if remote is not None:
                return {"scope": "source", **remote}
        return None

    def refresh(self, force_sources: tuple[str, ...] = ()) -> None:
        """Re-read the fleet key + every known source's key from Redis (ONE MGET). Fails OPEN: an unreadable store
        keeps whatever was last known, logs, and alerts once per outage."""
        if self._store is None:
            return
        with self._lock:
            sources = sorted(self._known | set(force_sources) | set(self._trips))
        keys = [BREAKER_FLEET_KEY] + [self.key_for(s) for s in sources]
        try:
            values = self._store.mget(keys)
        except Exception as exc:  # noqa: BLE001 -- fail OPEN by design, never silently
            with self._lock:
                self._last_refresh = self._clock()
                first = not self._store_down
                self._store_down = True
            if first:
                logger.critical("breaker: cannot read the breaker keys from Redis (%s: %s) — failing OPEN: background "
                                "sources keep running and the FLEET key cannot be honoured until Redis is back",
                                type(exc).__name__, exc)
                self._io(self._alert, f"redis-down:{self.slug}:{int(self._wall())}",
                         f"[NoctusAI] Supabase breaker BLIND: {self.slug} cannot read Redis",
                         f"{self.slug} cannot read its breaker keys ({type(exc).__name__}: {exc}). Background sources "
                         "keep running (fail open); the fleet kill switch is NOT being honoured by this process.")
            return
        with self._lock:
            self._last_refresh = self._clock()
            if self._store_down:
                logger.warning("breaker: Redis reachable again for %s", self.slug)
            self._store_down = False
            fleet_raw, per_source = values[0], dict(zip(sources, values[1:]))
            self._fleet = _parse_trip("fleet", fleet_raw) if fleet_raw else None
            if self._fleet is not None:
                self._fleet.pop("source", None)
            self._remote_held = {s: _parse_trip(s, v) for s, v in per_source.items() if v and s not in self._trips}
            settled = self._clock() - 2 * self._fleet_ttl
            released = [s for s, t in self._trips.items()
                        if t.persisted and t.persisted_at <= settled and per_source.get(s) is None]
            woke: list[Callable[[], None]] = []
            for s in released:  # a human re-armed it elsewhere (MCP tool): the key is gone -> local trip released
                del self._trips[s]
                self._alerted = {a for a in self._alerted if not a.startswith(f"trip:{self.slug}:{s}:")}
                logger.warning("breaker: %s re-armed (key removed) — the source may start again", s)
                woke.extend(self._subs.get(s, ()))
            for s, rem in self._remote_held.items():
                if s not in self._trips:
                    woke.extend(self._subs.get(s, ()))
            if self._fleet is not None:
                for subs in self._subs.values():
                    woke.extend(subs)
        for cb in woke:
            self._call_sub(cb)

    def _due(self) -> bool:
        with self._lock:
            return self._last_refresh is None or self._clock() - self._last_refresh >= self._fleet_ttl

    async def check(self, source: str, *, force: bool = False) -> Optional[dict[str, Any]]:
        """Async gate for a background loop: the hold reason, or None. Refreshes from Redis (in a thread) when the
        cache is older than ``fleet_ttl_s`` or ``force`` (boot)."""
        if is_background(source):
            self.register_source(source)
            if force or self._due():
                import asyncio

                # poll-budget: 10s; 1 calls/tick; worst 8640/day; idle=same (one Redis MGET per process, cached, never Supabase)
                await asyncio.to_thread(self.refresh, (source,))
        return self.hold_reason(source)

    def check_sync(self, source: str, *, force: bool = False) -> Optional[dict[str, Any]]:
        if is_background(source):
            self.register_source(source)
            if force or self._due():
                # poll-budget: 10s; 1 calls/tick; worst 8640/day; idle=same (one Redis MGET per process, cached, never Supabase)
                self.refresh((source,))
        return self.hold_reason(source)

    # ---- re-arm (human only) ----------------------------------------------------------------------------------

    def rearm(self, source: str, *, by: str, reason: str) -> dict[str, Any]:
        """Release ``source`` (or the fleet key with ``source='fleet'``). A human, with a reason — never automatic."""
        if not (by or "").strip() or not (reason or "").strip():
            raise ValueError("re-arm needs who (by) and why (reason)")
        key = BREAKER_FLEET_KEY if source == "fleet" else self.key_for(source)
        with self._lock:
            local = self._trips.get(source)
        if self._store is not None:
            try:
                self._store.delete(key)
            except Exception:
                if local is None or local.persisted:
                    raise  # the key may still exist: never pretend it was released
                logger.warning("breaker: Redis unreachable; releasing the in-memory-only trip for %s", source)
        with self._lock:
            self._trips.pop(source, None)
            self._remote_held.pop(source, None)
            if source == "fleet":
                self._fleet = None
            self._alerted = {a for a in self._alerted if not a.startswith(f"trip:{self.slug}:{source}:")}
            woke = list(self._subs.get(source, ())) if source != "fleet" else [c for s in self._subs.values() for c in s]
        self.audit("rearm", key, by=by, reason=reason)
        self._emit_event({"event": "breaker.rearmed", "product": self.slug, "source": source, "by": by,
                          "reason": reason})
        for cb in woke:
            self._call_sub(cb)
        return {"ok": True, "source": source, "key": key, "by": by, "reason": reason}

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "product": self.slug,
                "fleet": dict(self._fleet) if self._fleet else None,
                "held": {s: {"reason": t.reason, "by": t.by, "tripped_at": t.tripped_at, "persisted": t.persisted}
                         for s, t in self._trips.items()},
                "held_remote": dict(self._remote_held),
                "known_sources": sorted(self._known),
                "store_down": self._store_down,
                "pending_alerts": len(self.pending_alerts),
                "sent_alerts": self.sent_alerts,
            }


# --- process singleton -----------------------------------------------------------------------------------------

_breaker: Optional[Breaker] = None
_breaker_lock = threading.Lock()


def get_breaker() -> Breaker:
    """The process-wide breaker (built on first use with the env budgets, an in-memory store and an alerter that
    fails loudly until the framework installs the real ones)."""
    global _breaker
    if _breaker is None:
        with _breaker_lock:
            if _breaker is None:
                _breaker = Breaker(config=BreakerConfig.from_env(), store=InMemoryBreakerStore())
    return _breaker


def configure_breaker(**kwargs: Any) -> Breaker:
    """Install the product's slug / Redis store / alerter / event sink on the process breaker."""
    b = get_breaker()
    b.configure(**kwargs)
    return b


def reset_breaker_for_tests() -> None:
    global _breaker
    with _breaker_lock:
        _breaker = None


def guard(source: Optional[str] = None) -> None:
    """Module-level hot-path gate the HTTP transport calls BEFORE a REST call leaves the process."""
    get_breaker().guard(source)


def record_call(source: Optional[str] = None) -> None:
    """Module-level hot-path entry the HTTP transport calls (one lookup + the breaker's O(1) count)."""
    get_breaker().record_call(source)
