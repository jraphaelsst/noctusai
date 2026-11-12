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
import math
import logging
import os
import re
import socket
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
    "BREAKER_REASON_RE",
    "DEFAULT_JOB_CALL_CAP",
    "JobBudgetExceeded",
    "MAX_BUDGET_CALLS",
    "call_tally",
    "detach_context",
    "AGGREGATE_SOURCE",
    "DEFAULT_DAILY_QUOTA",
    "is_holdable",
    "job_scope",
    "STARTUP_SOURCE",
    "DEFAULT_STARTUP_RULES",
    "UNATTRIBUTED_SOURCE",
    "guard",
    "refresh_loop",
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
    "install_breaker",
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
#: ONLY named, owned loops can be held: a Worker loop (`worker:<types>`) or a scheduler job (`scheduler:<job>`). `http`,
#: `startup`, `unattributed`, `bg:*`, `job:*`, `egress:*` ... are ALERT-ONLY by construction (tech-lead decision, round 4):
#: request-path or user-facing work can never be refused because of a source it did not name.
BREAKER_SOURCE_RE = re.compile(r"^(?:worker|scheduler):[A-Za-z0-9_.,:\-]{1,100}$")
#: a human-supplied reason: printable, no control characters (log/alert/terminal-injection safe)
BREAKER_REASON_RE = re.compile(r"^[^\x00-\x1f\x7f]{1,300}$")
#: a configured budget can never exceed this (a "budget" of 10**9 is a disabled breaker)
MAX_BUDGET_CALLS = 20_000  # as a RATE: calls per HOUR across every window of a rule; also the absolute per-job hard cap
#: one JOB (inside a Worker handler or a scheduler run): the per-job cap. OBSERVE mode (default): reaching the cap only
#: ALERTS; the job is failed (dead-lettered) at MAX_BUDGET_CALLS. ENFORCE (`NOCTUS_BREAKER_JOB_CAP_ENFORCE=1`): the cap
#: itself fails the job. Never the type or the other tenants; never credited.
# NOC-REMEDIATE[breaker-job-cap-calibration]: tighten the per-type caps (Worker `job_call_caps`) from MEASURED p99 calls per job, then flip the default to enforce — destination: the breaker owner after ~2 weeks of `job-cap:*` alert data — 2026-11-10
DEFAULT_JOB_CALL_CAP = 2000
#: default planning figure for the daily Supabase REST call quota of the Free plan (`NOCTUS_SUPABASE_DAILY_QUOTA`). Supabase
#: publishes an egress quota (5 GB/month), not a call count: this is the incident-derived budget (620k calls/day exhausted it).
DEFAULT_DAILY_QUOTA = 500_000
DEFAULT_AGGREGATE_SHARE = 0.5
AGGREGATE_SOURCE = "*"
DEFAULT_MIN_IDLE_POLL_S = 10.0
MAX_MIN_IDLE_POLL_S = 60.0
DEFAULT_MAX_FREE_WAKE_POLLS = 30
#: sources whose budgets are the safety nets themselves: an env override of any of these is IGNORED (loudly)
NON_OVERRIDABLE_SOURCES = frozenset({"*", "http", "startup", "unattributed"})
#: a re-arm marker outlives a flush-vs-rearm race but not forever (1 day)
MARKER_TTL_S = 86_400
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


def is_holdable(source: str) -> bool:
    """True only for the named, owned loops that may be held: ``worker:*`` and ``scheduler:*``."""
    return source.startswith(("worker:", "scheduler:"))


is_background = is_holdable  # historical name


#: alert-only sources that are not http/startup/unattributed: spawn_background (`bg:*`), per-job (`job:*`), claim
#: phases, non-REST egress (`egress:*`).
DEFAULT_ALERT_RULES: tuple[BudgetRule, ...] = (BudgetRule(300, 600), BudgetRule(3600, 2000))
#: stray unscoped work alerts early (it is exactly the incident shape) but is never held.
DEFAULT_UNATTRIBUTED_RULES: tuple[BudgetRule, ...] = (BudgetRule(300, 300), BudgetRule(3600, 2000))


@dataclass
class BreakerConfig:
    """Budgets per source. ``overrides`` maps an EXACT source name to its rules; everything else uses the defaults.

    Env ``NOCTUS_BREAKER_BUDGETS`` = JSON ``{"worker:transcricao": [[300, 600], [3600, 4000]]}`` (a per-source
    override, never a way to switch the breaker off — a rule list may not be empty)."""

    background_rules: tuple[BudgetRule, ...] = DEFAULT_BACKGROUND_RULES
    http_rule: BudgetRule = DEFAULT_HTTP_RULE
    overrides: dict[str, tuple[BudgetRule, ...]] = field(default_factory=dict)
    startup_rules: tuple[BudgetRule, ...] = DEFAULT_STARTUP_RULES
    daily_quota: int = DEFAULT_DAILY_QUOTA
    aggregate_share: float = DEFAULT_AGGREGATE_SHARE
    job_cap_enforce: bool = False
    fleet_holds_bg: bool = False  # opt-in: the fleet key also refuses `bg:*` (default off)
    #: PLATFORM floor for an idle poll (`NOCTUS_MIN_IDLE_POLL_S`): a Worker whose consecutive empty polls come closer than
    #: this is a loop with no (or too short a) backoff, whatever cadence it declares for itself.
    min_idle_poll_s: float = DEFAULT_MIN_IDLE_POLL_S
    max_free_wake_polls: int = DEFAULT_MAX_FREE_WAKE_POLLS  # per 5 min: wake-followed empty polls that stay free
    warnings: list[str] = field(default_factory=list)  # config problems found at load: logged + alerted once

    def source_hour_ceiling(self) -> int:
        """No per-source rule may allow more per HOUR than the aggregate alert would: quota x share / 24."""
        return max(1, int(self.daily_quota * self.aggregate_share / 24))

    def aggregate_rules(self) -> tuple[BudgetRule, ...]:
        """Alert when the rolling PROJECTED daily total (last hour x24, last 5 min x288) passes the share of the quota."""
        limit = max(1.0, self.daily_quota * self.aggregate_share)
        return (BudgetRule(3600, max(1, int(limit / 24))), BudgetRule(300, max(1, int(limit / 288))))

    def rules_for(self, source: str) -> tuple[BudgetRule, ...]:
        if source in self.overrides:
            return self.overrides[source]
        if source == AGGREGATE_SOURCE:
            return self.aggregate_rules()
        if source == STARTUP_SOURCE:
            return self.startup_rules
        if source == HTTP_SOURCE:
            return (self.http_rule,)
        if source == UNATTRIBUTED_SOURCE:
            return DEFAULT_UNATTRIBUTED_RULES
        return self.background_rules if is_holdable(source) else DEFAULT_ALERT_RULES

    @classmethod
    def from_env(cls, environ: Optional[dict[str, str]] = None) -> "BreakerConfig":
        env = environ if environ is not None else os.environ
        extra: dict[str, Any] = {}
        warnings: list[str] = []
        try:
            if env.get("NOCTUS_SUPABASE_DAILY_QUOTA", "").strip():
                quota = max(1, int(env["NOCTUS_SUPABASE_DAILY_QUOTA"]))
                if quota > DEFAULT_DAILY_QUOTA:
                    warnings.append(f"NOCTUS_SUPABASE_DAILY_QUOTA={quota:,} is above the default {DEFAULT_DAILY_QUOTA:,}"
                                    + (f"; clamped to {2 * DEFAULT_DAILY_QUOTA:,} (2x the default)"
                                       if quota > 2 * DEFAULT_DAILY_QUOTA else ""))
                extra["daily_quota"] = min(quota, 2 * DEFAULT_DAILY_QUOTA)
            if env.get("NOCTUS_BREAKER_AGGREGATE_SHARE", "").strip():
                share = float(env["NOCTUS_BREAKER_AGGREGATE_SHARE"])
                if not 0 < share <= 1:
                    raise ValueError("share must be in (0, 1]")
                extra["aggregate_share"] = share
            if env.get("NOCTUS_MIN_IDLE_POLL_S", "").strip():
                floor = float(env["NOCTUS_MIN_IDLE_POLL_S"])
                if not math.isfinite(floor):
                    warnings.append(f"NOCTUS_MIN_IDLE_POLL_S={env['NOCTUS_MIN_IDLE_POLL_S']!r} is not a finite number; "
                                    f"using the default {DEFAULT_MIN_IDLE_POLL_S:g} s")
                else:
                    if floor > MAX_MIN_IDLE_POLL_S:
                        warnings.append(f"NOCTUS_MIN_IDLE_POLL_S={floor:g} is above {MAX_MIN_IDLE_POLL_S:g} s; clamped")
                    if floor < DEFAULT_MIN_IDLE_POLL_S:
                        from noctusai_lib.config.deploy_config import is_deploy_context_in

                        deploy = is_deploy_context_in(env)
                        warnings.append(f"NOCTUS_MIN_IDLE_POLL_S={floor:g} is below the default {DEFAULT_MIN_IDLE_POLL_S:g} s"
                                        + ("; clamped to the default in a deploy context" if deploy else ""))
                        floor = DEFAULT_MIN_IDLE_POLL_S if deploy else max(1.0, floor)
                    extra["min_idle_poll_s"] = min(floor, MAX_MIN_IDLE_POLL_S)
        except ValueError as exc:
            warnings.append(f"invalid breaker config ({exc}); using the defaults")
            extra = {}
        truthy = ("1", "true", "yes", "on")
        extra["job_cap_enforce"] = env.get("NOCTUS_BREAKER_JOB_CAP_ENFORCE", "").strip().lower() in truthy
        extra["fleet_holds_bg"] = env.get("NOCTUS_BREAKER_FLEET_HOLDS_BG", "").strip().lower() in truthy
        probe = cls(**extra)
        raw = env.get("NOCTUS_BREAKER_BUDGETS", "").strip()
        overrides: dict[str, tuple[BudgetRule, ...]] = {}
        if raw:
            try:
                parsed = json.loads(raw)
                for src, rules in parsed.items():
                    src = str(src)
                    if src in NON_OVERRIDABLE_SOURCES:
                        warnings.append(f"NOCTUS_BREAKER_BUDGETS: {src!r} is a safety net and cannot be overridden; ignored")
                        continue
                    rule_t = tuple(BudgetRule(int(w), int(m)) for w, m in rules)
                    if not rule_t:
                        raise ValueError("a source override needs at least one rule")
                    ceiling = probe.source_hour_ceiling()
                    for r in rule_t:  # a RATE ceiling derived from the quota (quota x share / 24 per hour)
                        if r.max_calls * 3600 / r.window_s > ceiling:
                            raise ValueError(f"{src}: {r} exceeds the ceiling of {ceiling} calls/hour")
                    # per WINDOW: each override rule against the default rule of the SAME window (a rule on a window the
                    # defaults do not have is compared by hourly rate against the defaults' tightest hourly rate)
                    defaults = probe.rules_for(src)
                    by_window = {d.window_s: d for d in defaults}
                    tightest = min(d.max_calls * 3600 / d.window_s for d in defaults)
                    looser = [r for r in rule_t
                              if (r.max_calls > by_window[r.window_s].max_calls if r.window_s in by_window
                                  else r.max_calls * 3600 / r.window_s > tightest)]
                    if looser:
                        warnings.append(f"NOCTUS_BREAKER_BUDGETS: {src!r} is LOOSER than the default rules for "
                                        f"{', '.join(f'{r.window_s}s={r.max_calls}' for r in looser)}; accepted, alerted")
                    overrides[src] = rule_t
            except Exception as exc:  # noqa: BLE001 -- loud, then the canonical defaults (never a silent partial config)
                warnings.append(f"NOCTUS_BREAKER_BUDGETS is invalid ({type(exc).__name__}: {exc}); using the default budgets")
                overrides = {}
        for w in warnings:
            logger.error("breaker config: %s", w)
        return cls(overrides=overrides, warnings=warnings, **extra)


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

    def set(self, key: str, value: str, ttl: Optional[int] = None) -> None: ...

    def delete(self, key: str) -> None: ...

    def append_audit(self, key: str, value: str, cap: int) -> None: ...

    def lrange(self, key: str, count: int) -> list[str]: ...


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


class JobBudgetExceeded(RuntimeError):
    """One JOB made more Supabase calls than its absolute cap: that job fails (the Worker dead-letters it with this
    reason; a scheduler run records an error). Never the type, never the other tenants."""

    def __init__(self, calls: int, cap: int) -> None:
        super().__init__(f"job exceeded its Supabase call cap: {calls} calls >= {cap}")
        self.calls, self.cap = calls, cap


class _JobBudget:
    __slots__ = ("count", "cap", "hard", "alerted")

    def __init__(self, cap: int, hard: int) -> None:
        self.count, self.cap, self.hard, self.alerted = 0, cap, hard, False

    @property
    def over(self) -> bool:
        """Past the HARD limit (observe mode: MAX_BUDGET_CALLS; enforce mode: the cap itself)."""
        return self.count >= self.hard


class _Tally:
    __slots__ = ("n",)

    def __init__(self) -> None:
        self.n = 0


_JOB: contextvars.ContextVar[Optional[_JobBudget]] = contextvars.ContextVar("noctus_supabase_job", default=None)
_TALLY: contextvars.ContextVar[Optional[_Tally]] = contextvars.ContextVar("noctus_supabase_tally", default=None)


@contextlib.contextmanager
def job_scope(cap: int = DEFAULT_JOB_CALL_CAP, *, hard: Optional[int] = None) -> Iterator[_JobBudget]:
    """Everything inside is ONE job. At ``cap`` calls an alert fires (once); at ``hard`` calls the next call raises
    :class:`JobBudgetExceeded` (checked in ``guard``) and the Worker dead-letters the job. ``hard`` defaults to the cap in
    ENFORCE mode and to ``MAX_BUDGET_CALLS`` (never lower than the cap) in OBSERVE mode (the default)."""
    cap = min(cap, MAX_BUDGET_CALLS)
    if hard is None:
        enforce = get_breaker()._config.job_cap_enforce
        hard = cap if enforce else MAX_BUDGET_CALLS
    budget = _JobBudget(cap, min(hard, MAX_BUDGET_CALLS))
    token = _JOB.set(budget)
    try:
        yield budget
    finally:
        _JOB.reset(token)


def detach_context() -> None:
    """For a task/thread that outlives the job or request that spawned it: drop the per-job budget and call tally it
    would otherwise inherit (its calls are not that job's)."""
    _JOB.set(None)
    _TALLY.set(None)


@contextlib.contextmanager
def call_tally() -> Iterator[_Tally]:
    """Counts the Supabase calls made inside (the Worker uses it to bill an EMPTY poll — claim + gate — to the loop)."""
    tally = _Tally()
    token = _TALLY.set(tally)
    try:
        yield tally
    finally:
        _TALLY.reset(token)


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
        self.audits: dict[str, list[str]] = {}  # per list key, like Redis
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

    def set(self, key: str, value: str, ttl: Optional[int] = None) -> None:
        self._guard()
        self.data[key] = value

    def delete(self, key: str) -> None:
        self._guard()
        self.data.pop(key, None)

    def append_audit(self, key: str, value: str, cap: int) -> None:
        self._guard()
        rows = self.audits.setdefault(key, [])
        rows.append(value)
        del rows[:-cap]

    def lrange(self, key: str, count: int) -> list[str]:
        self._guard()
        return list(self.audits.get(key, [])[-count:])


# --- the breaker -----------------------------------------------------------------------------------------------


_HOST = socket.gethostname()


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
    key_tripped_at: str = ""  # the `tripped_at` of the PERSISTED key (another process may have written it)

    def as_json(self) -> str:
        return json.dumps({"reason": self.reason, "rate": round(self.rate, 3), "window": self.window,
                           "tripped_at": self.tripped_at, "by": self.by})


_CONFIG_ERROR_NAMES = frozenset({"NoPermissionError", "AuthenticationError", "AuthenticationWrongNumberOfArgsError",
                                 "RedisAuthRequired"})


def _is_config_error(exc: BaseException) -> bool:
    """A Redis refusal of OUR credentials / ACL is configuration, not a transient outage."""
    text = str(exc)
    return (type(exc).__name__ in _CONFIG_ERROR_NAMES
            or any(m in text for m in ("NOPERM", "WRONGPASS", "NOAUTH", "invalid username-password")))


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
        self._indexed: set[str] = set()
        self.degraded: Optional[str] = None
        self._degraded_transient = False
        self._alert_only_at: dict[str, float] = {}
        self.sent_alerts = 0

    # ---- configuration ----------------------------------------------------------------------------------------

    @property
    def store(self) -> Optional[BreakerStore]:
        return self._store

    @property
    def key_prefix(self) -> str:
        return f"{BREAKER_KEY_PREFIX}{self.slug}:"

    def marker_key(self, source: str) -> str:
        """The re-arm marker a human re-arm leaves: `{tripped_at, by, reason}` of the trip it released."""
        return f"{self.key_prefix}rearm:{source}"

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

    def _account(self, src: str, n: int, now: int) -> Optional[tuple[BudgetRule, int]]:
        """Add ``n`` to ``src``'s sliding window; return the worst violated rule, if any."""
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
                self._bases[src] = [sum(c for sec, c in dq if sec > now - r.window_s) for r in rules]
                dq.append([now, 0])
            dq[-1][1] += n
            cur = dq[-1][1]
            for rule, base in zip(self._rules[src], self._bases[src]):
                total = base + cur
                if total > rule.max_calls and (verdict is None or total / rule.window_s > verdict[1] / verdict[0].window_s):
                    verdict = (rule, total)
        return verdict

    def record_call(self, source: Optional[str] = None, n: int = 1) -> None:
        """Count ``n`` Supabase calls (default 1). In-memory only: no network, O(rules); the budget is checked on EVERY
        call against running per-window bases (rebuilt once per second), so a tight loop trips at exactly budget+1.
        A HOLDABLE source (worker loop / scheduler job) trips; every other source only ALERTS. Every call also feeds the
        per-process AGGREGATE (`*`): alert when the projected daily total passes the quota share."""
        src = source or _SOURCE.get()
        tally = _TALLY.get()
        if tally is not None:
            tally.n += n
        job = _JOB.get()
        if job is not None:
            job.count += n
            if job.count >= job.cap and not job.alerted:
                job.alerted = True  # once per job: observe-mode cap reached (the hard limit is separate)
                self._alert_only(f"job-cap:{src}", f"one job reached its call cap ({job.count} >= {job.cap}; "
                                 f"{'enforced' if job.hard <= job.cap else 'observe mode: hard limit ' + str(job.hard)})",
                                 0.0, 0)
        now = int(self._clock())
        verdict = self._account(src, n, now)
        agg = self._account(AGGREGATE_SOURCE, n, now) if src != AGGREGATE_SOURCE else None
        if agg is not None and not self._cooling(AGGREGATE_SOURCE):
            rule, count = agg
            self._alert_only(AGGREGATE_SOURCE, f"projected daily total ~{int(count * 86400 / rule.window_s):,} calls "
                             f"({count} in {rule.window_s}s) passes {self._config.aggregate_share:.0%} of the "
                             f"{self._config.daily_quota:,}/day quota", count / rule.window_s, rule.window_s)
        if verdict is None:
            return
        rule, count = verdict
        reason = f"{count} Supabase calls in {rule.window_s}s exceeds the budget of {rule.max_calls}"
        rate = count / rule.window_s
        if is_holdable(src):
            self.trip(src, reason=reason, rate=rate, window=rule.window_s)
        elif not self._cooling(src):
            self._alert_only(src, reason, rate, rule.window_s)

    def job_hard_limit(self, cap: int) -> int:
        """The call count at which a job is FAILED: the cap itself in ENFORCE mode, else MAX_BUDGET_CALLS (observe)."""
        cap = min(cap, MAX_BUDGET_CALLS)
        return cap if self._config.job_cap_enforce else MAX_BUDGET_CALLS

    def is_open(self, source: str) -> bool:
        """Hot-path hold check (in-memory, lock-free dict reads, no IO). Only holdable sources can be open."""
        if not is_holdable(source):
            return self._fleet is not None and self._config.fleet_holds_bg and source.startswith("bg:")
        return source in self._trips or self._fleet is not None or source in self._remote_held

    def guard(self, source: Optional[str] = None) -> None:
        """Raise :class:`BreakerOpen` when the (current) HOLDABLE source is held, and :class:`JobBudgetExceeded` when
        the current job is past its absolute call cap. Everything else passes."""
        src = source or _SOURCE.get()
        if self.is_open(src):
            hold = self.hold_reason(src) or {}
            raise BreakerOpen(src, str(hold.get("reason", "")))
        job = _JOB.get()
        if job is not None and job.count >= job.hard:
            raise JobBudgetExceeded(job.count, job.hard)

    def count(self, source: str, window_s: int) -> int:
        """Calls recorded for ``source`` in the last ``window_s`` seconds (diagnostics/tests)."""
        now = int(self._clock())
        with self._lock:
            return sum(n for sec, n in self._buckets.get(source, ()) if sec > now - window_s)

    # ---- trip -------------------------------------------------------------------------------------------------

    def trip(self, source: str, *, reason: str, rate: float = 0.0, window: int = 0, by: str = "auto") -> bool:
        """Hold ``source`` (idempotent). Returns True when this call created the trip."""
        if by != "auto" and not BREAKER_REASON_RE.match(reason or ""):
            raise ValueError("reason must be printable text without control characters (max 300)")
        if not is_holdable(source):
            raise ValueError(f"{source!r} is alert-only: only worker:* and scheduler:* sources can be held")
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

    def audit(self, op: str, key: str, *, by: str, reason: str, tripped_at: Optional[str] = None,
              required: bool = False) -> None:
        """Audit row (who/why/when) on the capped Redis list; the MCP tool writes the same shape. Best effort, except
        ``required=True`` (a re-arm): a failed append RAISES so the caller does not go on to delete the key."""
        row = {"op": op, "key": key, "claimed_by": by, "reason": reason, "at": _iso(self._wall()),
               "host": _HOST, "pid": os.getpid()}
        if tripped_at:
            row["tripped_at"] = tripped_at  # the nonce other processes match against the persisted key
        if self._store is None:
            if required:
                raise RuntimeError("no breaker store: cannot append the mandatory re-arm audit row")
            return
        try:
            # inside THIS product's Redis namespace (its ACL user cannot write the global ops audit list)
            self._store.append_audit(f"{self.key_prefix}audit", json.dumps(row), BREAKER_AUDIT_CAP)
        except Exception:  # noqa: BLE001 -- loud; mandatory for a re-arm, best effort otherwise
            logger.error("breaker: audit row not written for %s %s", op, key, exc_info=True)
            if required:
                raise

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
                if _is_config_error(exc):
                    self.set_degraded(f"the breaker Redis refused this service's credentials/ACL ({type(exc).__name__}): "
                                      "trips are NOT persisted")
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

    def _cooling(self, source: str) -> bool:
        """Cheap pre-check (no lock, no string work) so a source already over its threshold costs nothing per call."""
        last = self._alert_only_at.get(source)
        return last is not None and self._clock() - last < self._http_cooldown

    def _alert_only(self, source: str, reason: str, rate: float, window: int) -> None:
        """Alert (never stop) for a source that is not a named, owned loop. One alert per source per cooldown."""
        now = self._clock()
        with self._lock:
            last = self._alert_only_at.get(source)
            if last is not None and now - last < self._http_cooldown:
                return
            self._alert_only_at[source] = now
        logger.error("breaker: %s %s in %s — ALERT only, this source is never stopped", source, reason, self.slug)
        self._io(self._alert, f"alert-only:{self.slug}:{source}:{int(self._wall())}",
                 f"[NoctusAI] Supabase traffic high: {self.slug} {source}",
                 f"Product: {self.slug}\nSource: {source} (alert-only: request handlers, boot and unattributed work "
                 f"are never stopped)\nReason: {reason}\nRate: {rate:.2f} calls/s over {window}s\n"
                 "Evaluate whether this is a loop (a create_task / Thread without source_scope or spawn_background) "
                 "or a real traffic spike.")

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
            if self._fleet is not None and self._config.fleet_holds_bg and source.startswith("bg:"):
                return {"source": source, "scope": "fleet", **self._fleet}
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
        with self._lock:
            marker_sources = sorted(s for s, t in self._trips.items() if t.persisted)
        keys = ([BREAKER_FLEET_KEY] + [self.key_for(s) for s in sources]
                + [self.marker_key(s) for s in marker_sources])
        try:
            values = self._store.mget(keys)
        except Exception as exc:  # noqa: BLE001 -- fail OPEN by design, never silently
            if _is_config_error(exc):
                with self._lock:
                    self._last_refresh = self._clock()
                self.set_degraded(f"the breaker Redis refused this service's credentials/ACL ({type(exc).__name__}): "
                                  "configuration, not an outage — breaker state is NOT being read or persisted")
                return
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
            if self.degraded and self._degraded_transient:
                logger.warning("breaker: a transient degraded state (%s) cleared: the first refresh succeeded", self.degraded)
                self.degraded, self._degraded_transient = None, False
            fleet_raw = values[0]
            per_source = dict(zip(sources, values[1:1 + len(sources)]))
            markers = dict(zip(marker_sources, values[1 + len(sources):]))
            self._fleet = _parse_trip("fleet", fleet_raw) if fleet_raw else None
            if self._fleet is not None:
                self._fleet.pop("source", None)
            self._remote_held = {s: _parse_trip(s, v) for s, v in per_source.items() if v and s not in self._trips}
            for s_, v_ in per_source.items():  # remember the PERSISTED key's tripped_at (multi-process / deploy overlap)
                if v_ and s_ in self._trips:
                    self._trips[s_].key_tripped_at = str(_parse_trip(s_, v_).get("tripped_at") or "")
            settled = self._clock() - 2 * self._fleet_ttl
            vanished = [s for s, t in self._trips.items()
                        if t.persisted and t.persisted_at <= settled and per_source.get(s) is None]
            woke: list[Callable[[], None]] = []
            to_index: list[str] = []
            rewrite: list[Trip] = []
            unmarked: list[Trip] = []
            for s in vanished:
                trip = self._trips[s]
                marker = _parse_trip(s, markers[s]) if markers.get(s) else None
                if marker is not None and marker.get("tripped_at") == (trip.key_tripped_at or trip.tripped_at):
                    # a human re-armed THIS trip elsewhere (the matching marker proves it): release
                    del self._trips[s]
                    self._alerted = {a for a in self._alerted if not a.startswith(f"trip:{self.slug}:{s}:")}
                    logger.warning("breaker: %s re-armed by %s — the source may start again", s, marker.get("by"))
                    woke.extend(self._subs.get(s, ()))
                else:
                    unmarked.append(trip)  # decided below, outside the lock (it may need a network read)
            for s, rem in self._remote_held.items():
                if s not in self._trips:
                    woke.extend(self._subs.get(s, ()))
                    to_index.append(s)
            if self._fleet is not None:
                for subs in self._subs.values():
                    woke.extend(subs)
        for trip in unmarked:
            # A re-arm by a PRODUCT process (the platform-admin route) cannot write the read-only marker key; it leaves a
            # `rearm` row carrying the released trip's `tripped_at` in the product's own audit list instead.
            if self._audit_shows_rearm(trip):
                with self._lock:
                    if self._trips.get(trip.source) is trip:
                        del self._trips[trip.source]
                        self._alerted = {a for a in self._alerted
                                         if not a.startswith(f"trip:{self.slug}:{trip.source}:")}
                        woke.extend(self._subs.get(trip.source, ()))
                logger.warning("breaker: %s re-armed (audit row matches the persisted trip) — the source may start again",
                               trip.source)
            else:
                # the key vanished with NO matching marker or audit row (flush / eviction / tampering): a persisted hold
                # is never silently released — rewrite the key and alert
                rewrite.append(trip)
        for src in to_index:  # network: outside the lock
            self._index_observed(src)
        self._repersist_unpersisted()  # Redis is reachable again: in-memory-only trips become visible to the fleet
        for trip in rewrite:
            logger.critical("breaker: the key for held source %s VANISHED without a re-arm marker — rewriting it "
                            "(a persisted hold is never silently released)", trip.source)
            try:
                self._store.set(self.key_for(trip.source), trip.as_json())
                trip.persisted_at = self._clock()
            except Exception:  # noqa: BLE001 -- still held in memory; the alert below says so
                logger.error("breaker: could not rewrite the vanished key for %s", trip.source, exc_info=True)
            self._io(self._alert, f"vanished:{self.slug}:{trip.source}:{int(self._wall())}",
                     f"[NoctusAI] Supabase breaker key VANISHED: {self.slug} {trip.source}",
                     f"The held-source key for {trip.source} disappeared without a re-arm marker (Redis flush, "
                     "eviction or tampering). The hold was kept and the key rewritten. Investigate before re-arming.")
        for cb in woke:
            self._call_sub(cb)

    def _audit_shows_rearm(self, trip: Trip) -> bool:
        if self._store is None or not hasattr(self._store, "lrange"):
            return False
        want = trip.key_tripped_at or trip.tripped_at
        key = self.key_for(trip.source)
        try:
            rows = self._store.lrange(f"{self.key_prefix}audit", BREAKER_AUDIT_CAP)
        except Exception:  # noqa: BLE001 -- unreadable audit = no proof of a re-arm: the hold stays
            logger.error("breaker: could not read the audit list to verify a re-arm of %s", trip.source, exc_info=True)
            return False
        for raw in reversed(rows):  # newest first, up to the whole capped list, filtered by key
            try:
                row = json.loads(raw)
            except (TypeError, ValueError):
                continue
            if not (isinstance(row, dict) and row.get("key") == key and row.get("tripped_at") == want):
                continue
            if row.get("op") == "rearm_aborted":
                return False  # the NEWEST row for this key+nonce says the re-arm did not complete
            if row.get("op") == "rearm":
                # An audit row is writable by the product's own Redis identity: it is a SIGNAL, not a security boundary
                # (RO on `rearm:*` is not one either). Every release by this path is announced loudly.
                info = {k: row.get(k) for k in ("claimed_by", "host", "pid", "at", "reason")}
                self._emit_event({"event": "breaker.released_by_audit_row", "product": self.slug, "source": trip.source,
                                  **info})
                self._io(self._alert, f"audit-release:{self.slug}:{trip.source}:{want}",
                         f"[NoctusAI] Supabase breaker RELEASED by an audit row: {self.slug} {trip.source}",
                         f"{trip.source} was released because the product audit list carries a matching `rearm` row "
                         f"(claimed_by={info['claimed_by']}, host={info['host']}, pid={info['pid']}, at={info['at']}, "
                         f"reason={info['reason']!r}). Verify a human did this.")
                return True
        return False

    def probe(self) -> bool:
        """Boot probe: one GET of the fleet key. A failure degrades the breaker (config refusal or unreachable) instead
        of surfacing only at the first trip."""
        if self._store is None:
            self.set_degraded("no breaker store configured")
            return False
        try:
            self._store.get(BREAKER_FLEET_KEY)
            return True
        except Exception as exc:  # noqa: BLE001 -- classified, never swallowed
            kind = ("refused this service's credentials/ACL" if _is_config_error(exc) else "is unreachable")
            self.set_degraded(f"the breaker Redis {kind} at boot ({type(exc).__name__}: {str(exc)[:120]})",
                              transient=not _is_config_error(exc))
            return False

    def announce_config_warnings(self) -> None:
        """Alert (once per distinct warning) about env that tried to loosen the safety nets (quota above default ...)."""
        for w in self._config.warnings:
            self._io(self._alert, f"config:{self.slug}:{w}", f"[NoctusAI] Supabase breaker CONFIG warning: {self.slug}",
                     f"{self.slug}: {w}")

    def set_degraded(self, reason: str, *, transient: bool = False) -> None:
        """The breaker is running without something it needs (e.g. no Redis: trips are not persisted and the fleet key
        cannot be read). ONE alert, and `/api/health` reports `breaker_degraded`. A ``transient`` degraded state (the
        Redis was unreachable at boot) clears on the first successful refresh; a configuration refusal stays sticky."""
        with self._lock:
            if self.degraded == reason:
                return
            self.degraded = reason
            self._degraded_transient = transient
        logger.critical("SUPABASE BREAKER DEGRADED for %s: %s", self.slug, reason)
        self._io(self._alert, f"degraded:{self.slug}:{reason}",
                 f"[NoctusAI] Supabase breaker DEGRADED: {self.slug}",
                 f"{self.slug}: {reason}. Trips are held in memory only and the fleet kill switch cannot be read by "
                 "this process.")

    def _repersist_unpersisted(self) -> None:
        with self._lock:
            pending = [t for t in self._trips.values() if not t.persisted]
        for trip in pending:
            try:
                self._store.set(self.key_for(trip.source), trip.as_json())
                trip.persisted, trip.persisted_at = True, self._clock()
                logger.warning("breaker: re-persisted the in-memory-only trip for %s now that Redis is back", trip.source)
            except Exception:  # noqa: BLE001 -- still held in memory; retried on the next refresh
                logger.error("breaker: could not re-persist the trip for %s", trip.source, exc_info=True)

    def _index_observed(self, source: str) -> None:
        """A key an operator set by hand (ops has no SADD) is added to this product's index when first observed, so
        `noctus.dev.supabase_breaker status` can list it. Best effort, once per source."""
        if source in self._indexed or self._store is None or not hasattr(self._store, "index"):
            return
        self._indexed.add(source)
        try:
            self._store.index(self.key_for(source))
        except Exception:  # noqa: BLE001 -- listing aid only; the hold itself is already honoured
            logger.error("breaker: could not index operator-set key for %s", source, exc_info=True)

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
        if not BREAKER_REASON_RE.match(reason) or not reason.strip():
            raise ValueError("reason must be printable text without control characters (max 300)")
        if source == "fleet":
            raise ValueError("the fleet key is re-armed by ops only (noctus.dev.supabase_breaker): a product's Redis "
                             "identity can read it, never delete it")
        key = BREAKER_FLEET_KEY if source == "fleet" else self.key_for(source)
        with self._lock:
            local = self._trips.get(source)
        persisted_ts = ""
        audited = False
        if self._store is not None:
            try:
                # `rearm:*` is READ-ONLY for a product's Redis identity (only ops writes markers): other processes learn of
                # a re-arm from the `rearm` AUDIT row, which carries the `tripped_at` of the PERSISTED key. That GET is
                # LOAD-BEARING: on error we raise BEFORE the audit row or the DEL (the route answers 502).
                raw = self._store.get(key)
                if raw:
                    persisted_ts = str(_parse_trip(source, raw).get("tripped_at") or "")
                nonce = persisted_ts or ((local.key_tripped_at or local.tripped_at) if local is not None else "")
                # the row goes in BEFORE the DEL and is MANDATORY: if it cannot be written the key stays and this raises
                self.audit("rearm", key, by=by, reason=reason, tripped_at=nonce or None, required=True)
                audited = True
                try:
                    # NOC-REMEDIATE[breaker-rearm-cas]: row-append + DEL is not atomic; a compare-and-delete needs WATCH/MULTI/EXEC, which the product ACL (feat/redis-acl-lockdown) does not grant — add it there, then adopt it here (feat/supabase-breaker) — 2026-11-10
                    self._store.delete(key)
                except Exception:
                    # the row says "re-armed" but the key survived: a compensating row makes the newest row for this
                    # key+nonce say so, and `_audit_shows_rearm` honours the newest
                    with contextlib.suppress(Exception):
                        self.audit("rearm_aborted", key, by=by, reason=f"DEL failed after the audit row: {reason}"[:300],
                                   tripped_at=nonce or None)
                    raise
            except Exception:
                if local is None or local.persisted or audited:
                    raise  # the key may still exist: never pretend it was released
                logger.warning("breaker: Redis unreachable; releasing the in-memory-only trip for %s", source)
        with self._lock:
            self._trips.pop(source, None)
            self._remote_held.pop(source, None)
            if source == "fleet":
                self._fleet = None
            self._alerted = {a for a in self._alerted if not a.startswith(f"trip:{self.slug}:{source}:")}
            woke = list(self._subs.get(source, ())) if source != "fleet" else [c for s in self._subs.values() for c in s]
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
                "degraded": self.degraded,
                "pending_alerts": len(self.pending_alerts),
                "sent_alerts": self.sent_alerts,
            }


async def refresh_loop(stop_event: Any = None, *, interval_s: float = 10.0) -> None:
    """Seed-owned ticker: one cached Redis MGET per process every ``interval_s`` so a process WITHOUT a Worker or
    scheduler still sees the fleet key / re-arms / vanished keys. Never Supabase; fails open (see ``refresh``)."""
    import asyncio

    breaker = get_breaker()
    while stop_event is None or not stop_event.is_set():
        # poll-budget: 10s; 1 calls/tick; worst 8640/day; idle=same (one Redis MGET per process, never Supabase)
        await asyncio.to_thread(breaker.refresh)
        if stop_event is None:
            await asyncio.sleep(interval_s)
            continue
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_s)
        except asyncio.TimeoutError:
            pass


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
    b.announce_config_warnings()
    return b


def install_breaker(breaker: "Breaker") -> "Breaker":
    """Replace the process breaker (tests and embedding hosts that need their own clock/store)."""
    global _breaker
    with _breaker_lock:
        _breaker = breaker
    return breaker


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
