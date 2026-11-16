"""Every outbound HTTP call of the toolkit goes through here (2026-11-16, http-timeouts-by-construction).

THE INCIDENT. ``migrate_product social-wiring --confirm`` applied its migrations, then HUNG for 45 min
on one CLOSE_WAIT HTTPS socket to the Supabase management API (N=2; N=1, 2026-11-13, held a heavy slot
80 min), and was killed before ``migrations-applied.json`` was written. A per-socket-operation timeout
(urllib ``timeout=``, httpx's default) bounds ONE ``recv``, never the call: a peer that dribbles bytes
or keeps a half-closed socket alive resets it forever. So this helper bounds the WHOLE call.

CONSTRUCTION (what a caller gets by using it, nothing to remember):
  * explicit connect / read timeouts, env-overridable (``NOC_HTTP_CONNECT_TIMEOUT_S`` 10,
    ``NOC_HTTP_READ_TIMEOUT_S`` 60); urllib has one socket timeout, so it gets the read value and
    httpx gets both via ``client_timeout()``;
  * a TOTAL wall-clock deadline per attempt (``NOC_HTTP_TOTAL_DEADLINE_S`` 120) -- the call runs in a
    daemon thread and the caller is released at the deadline with ``HttpDeadlineExceeded`` (a
    ``TimeoutError``), whatever the socket is doing;
  * ONE bounded retry (``retries=1``) on connect/read timeout and 502/503/504/429 via the existing
    ``_transient_retry`` classifier. ``idempotent=False`` retries only provably-unsent failures (DNS,
    refused, 429): a lost response to a non-idempotent write is NEVER blindly re-sent -- the caller
    re-reads state (migrate_product re-checks the ledger) before deciding;
  * telemetry: every timeout / retry / terminal failure is one ``kind=http-timeout`` event
    (host, call site, elapsed, outcome) through ``gate_alignment.record_event``, so hangs are counted.

A longer budget is declared AT THE CALL SITE (``read_timeout=``, ``total_deadline=``), never by
dropping the bound. Backstop: keeper ``check_http_call_without_timeout``.
"""
from __future__ import annotations

import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, TypeVar

T = TypeVar("T")

#: gate id telemetry events are attributed to (declared in the gate-alignment inventory).
GATE_ID = "keeper:check-http-call-without-timeout"
EVENT_KIND = "http-timeout"

# STDLIB-ONLY at import time: ``prod_watchdog`` / ``mq_watchdog`` run in CI with no pip and import this
# through ``_public_edge``. The retry machinery (``_transient_retry`` -> noctusai_lib) is imported lazily,
# and only when a retry is actually requested (``retries=0`` probes never need it).


class HttpDeadlineExceeded(TimeoutError):
    """The whole call (not one socket read) outlived its total deadline."""


def _env_float(name: str, default: float) -> float:
    try:
        v = float(os.environ.get(name, "") or default)
    except ValueError:
        return default
    return v if v > 0 else default


def connect_timeout() -> float:
    return _env_float("NOC_HTTP_CONNECT_TIMEOUT_S", 10.0)


def read_timeout() -> float:
    return _env_float("NOC_HTTP_READ_TIMEOUT_S", 60.0)


def total_deadline() -> float:
    return _env_float("NOC_HTTP_TOTAL_DEADLINE_S", 120.0)


def client_timeout(*, read: float | None = None) -> Any:
    """``httpx.Timeout`` with explicit connect/read/write/pool -- for the toolkit's httpx clients."""
    import httpx

    r = read if read is not None else read_timeout()
    return httpx.Timeout(connect=connect_timeout(), read=r, write=r, pool=connect_timeout())


@dataclass
class Response:
    status: int
    headers: Mapping[str, str] = field(default_factory=dict)
    body: bytes = b""

    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")


def _event(call_site: str, host: str, elapsed: float, outcome: str, reason: str = "") -> None:
    """One telemetry row; never raises, never changes the call's verdict."""
    try:
        from . import gate_alignment

        gate_alignment.record_event(
            GATE_ID, "warn", kind=EVENT_KIND,
            target=f"{host} {call_site} elapsed={elapsed:.1f}s outcome={outcome}",
            reason=reason[:300], source="_http")
    except Exception:  # noqa: BLE001 -- telemetry is best-effort by contract
        pass


def run_with_deadline(fn: Callable[[], T], deadline_s: float, *, call_site: str = "?", host: str = "?") -> T:
    """Run ``fn`` in a daemon thread; release the caller at ``deadline_s`` with ``HttpDeadlineExceeded``.

    The abandoned thread dies with its own socket timeout (or the process); the caller never waits on it.
    """
    box: dict[str, Any] = {}

    def _run() -> None:
        try:
            box["v"] = fn()
        except BaseException as exc:  # noqa: BLE001 -- re-raised in the caller's thread
            box["e"] = exc

    t = threading.Thread(target=_run, name=f"noc-http:{call_site}", daemon=True)
    started = time.monotonic()
    t.start()
    t.join(deadline_s)
    if t.is_alive():
        elapsed = time.monotonic() - started
        _event(call_site, host, elapsed, "deadline_exceeded", f"no completion within {deadline_s:g}s")
        raise HttpDeadlineExceeded(f"{call_site}: {host} did not finish within {deadline_s:g}s (total deadline)")
    if "e" in box:
        raise box["e"]
    return box["v"]


def _host_of(req: urllib.request.Request | str) -> str:
    url = req if isinstance(req, str) else req.full_url
    return urllib.parse.urlsplit(url).netloc or "?"


def urlopen_read(
    req: urllib.request.Request | str,
    *,
    call_site: str,
    idempotent: bool = True,
    retries: int | None = None,
    read: float | None = None,
    total: float | None = None,
    policy: Any = None,
    sleep: Callable[[float], Any] = time.sleep,
) -> Response:
    """``urllib`` GET/POST with the whole-call bound + one bounded retry. Raises what urllib raises
    (``HTTPError`` for a non-2xx -- callers keep reading ``exc.code`` / ``exc.read()``), or
    ``HttpDeadlineExceeded``. ``retries=0`` for liveness probes (a retry would mask the signal)."""
    host = _host_of(req)
    sock_timeout = read if read is not None else read_timeout()
    deadline = total if total is not None else total_deadline()
    n_retries = 1 if retries is None else retries
    started = time.monotonic()

    def _once() -> Response:
        # Same call shape as every legacy site (``urlopen(req, timeout=...)``) so injected stand-ins keep working.
        with urllib.request.urlopen(req, timeout=sock_timeout) as resp:  # noqa: S310 -- callers pass operator-configured https URLs
            return Response(status=resp.status, headers=dict(resp.headers.items()) if resp.headers else {},
                            body=resp.read())

    def _bounded() -> Response:
        return run_with_deadline(_once, deadline, call_site=call_site, host=host)

    def _on_retry(attempt: int, exc: BaseException) -> None:
        _event(call_site, host, time.monotonic() - started, f"retry_{attempt}", f"{type(exc).__name__}: {exc}")

    try:
        if n_retries <= 0 and policy is None:
            return _bounded()
        from noctusai_lib.domain.jobs.retry_policy import RetryPolicy

        from . import _transient_retry

        pol = policy or RetryPolicy(max_retries=n_retries, backoff_seconds=1.0, backoff_multiplier=3.0,
                                    max_backoff_seconds=30.0)
        return _transient_retry.call_with_transient_retry(
            _bounded, policy=pol, retry_ambiguous=idempotent, sleep=sleep, on_retry=_on_retry)
    except urllib.error.HTTPError:
        raise  # a real HTTP answer: the caller decides; not a hang
    except HttpDeadlineExceeded:
        raise  # already logged by run_with_deadline
    except (TimeoutError, OSError, urllib.error.URLError) as exc:
        _event(call_site, host, time.monotonic() - started, "transport_failed", f"{type(exc).__name__}: {exc}")
        raise


__all__ = ["EVENT_KIND", "GATE_ID", "HttpDeadlineExceeded", "Response", "client_timeout",
           "connect_timeout", "read_timeout", "run_with_deadline", "total_deadline", "urlopen_read"]
