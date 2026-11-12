"""One process-wide HTTP/1.1 connection pool for every Supabase client.

Why: `supabase.create_client` builds a fresh httpx client (own TLS context, own
connection pool) for PostgREST, Auth and Storage on EVERY call, so a request
that built a user client paid a TCP+TLS handshake (2-3 round-trips, ~50 ms to
Supabase from the Campinas VPS) before its first byte — per request, per client.

How: the clients built through :func:`pooled_client` are thin per-client
``httpx.Client`` objects (own base URL, own default headers, own cookie jar) that
all sit on ONE shared ``httpx.HTTPTransport``. The transport owns the sockets, so
keep-alive connections are reused across clients and requests.

Thread-safety (the clients are used from FastAPI's threadpool AND from
``anyio.to_thread``): ``httpx.HTTPTransport`` wraps ``httpcore.ConnectionPool``,
whose pool bookkeeping is lock-protected and which hands each in-flight request
its own HTTP/1.1 connection. The documented outage (see
``database.force_postgrest_http1``) was HTTP/2 stream multiplexing on one
shared connection; this transport is ``http2=False`` by construction, so a
connection never carries two requests at once. Per-client state (headers,
cookies) is NOT shared — it lives on the per-client wrapper.

``close()`` on a pooled client is a no-op for the transport: closing one
client's wrapper must never tear down the sockets every other client is using.

Disable with ``NOCTUS_HTTP_POOL=0`` (kill switch; reverts to a private pool per
client, i.e. the pre-2026-10-21 behaviour).
"""
from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
import weakref
from typing import Any, Mapping, Optional

import httpx

from noctusai_lib.primitives.supabase_breaker import guard as _breaker_guard
from noctusai_lib.primitives.supabase_breaker import record_call as _breaker_record_call

logger = logging.getLogger(__name__)

#: Seconds an idle pooled connection is kept. Below the idle timeout of the
#: Supabase edge (>= 60 s) so we close first rather than reuse a connection the
#: server already dropped.
KEEPALIVE_EXPIRY_S = 20.0
MAX_CONNECTIONS = 200
MAX_KEEPALIVE_CONNECTIONS = 50

_lock = threading.Lock()
_transport: Optional[httpx.BaseTransport] = None

_SERVICES = ("rest", "auth", "storage")
_EGRESS_LABELS = ("auth", "storage", "functions")  # bounded breaker labels for non-REST egress
_CONNECT_STARTS = ("connection.connect_tcp.started", "connection.connect_unix_socket.started",
                   "connection.start_tls.started")
_CONNECT_ENDS = ("connection.connect_tcp.complete", "connection.connect_unix_socket.complete",
                 "connection.start_tls.complete")
_NEW_CONN_EVENTS = ("connection.connect_tcp.started", "connection.connect_unix_socket.started")


def service_of(url: httpx.URL) -> str:
    """Bounded service label from the URL's first path segment (``/rest/v1/..`` -> ``rest``).
    Never the URL itself or any id."""
    first = url.path.lstrip("/").split("/", 1)[0]
    return first if first in _SERVICES else "other"


class TimingTransport(httpx.BaseTransport):
    """Delegates to ``inner`` and records each call (time to response headers, service, and whether
    it needed a new TCP/TLS connection) into the current request's stats. Our own wrapper: no
    patching of httpx/httpcore. New connections are detected from httpcore's ``trace`` request
    extension; a trace callback already present is chained, never replaced."""

    def __init__(self, inner: httpx.BaseTransport, record: Any = None) -> None:
        self._inner = inner
        self._record = record

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        service = service_of(request.url)
        if service == "rest":
            # Supabase request breaker: the ONE place every seed-built client's PostgREST traffic passes. `guard`
            # refuses a held named loop and a job past its absolute call cap (BreakerOpen / JobBudgetExceeded);
            # the count is in-memory, never raises. Everything that is not a named, owned loop only ALERTS.
            _breaker_guard()
            try:
                _breaker_record_call()
            except Exception:  # noqa: BLE001 -- the safety net must never break a call
                logger.error("supabase breaker: count failed", exc_info=True)
        else:
            try:  # storage / auth / functions egress is counted too (alert-only: `egress:<service>`)
                label = request.url.path.lstrip("/").split("/", 1)[0]
                _breaker_record_call(f"egress:{label if label in _EGRESS_LABELS else 'other'}")
            except Exception:  # noqa: BLE001
                logger.error("supabase breaker: egress count failed", exc_info=True)
        if self._record is None:
            from ..api.request_timing import record_db_call as record
        else:
            record = self._record
        state = {"new": False, "connect_s": 0.0, "t0": None}
        prior = request.extensions.get("trace")

        def trace(event_name: str, info: Any) -> None:
            now = time.perf_counter()
            if event_name in _NEW_CONN_EVENTS:
                state["new"] = True
            if event_name in _CONNECT_STARTS:
                state["t0"] = now
            elif event_name in _CONNECT_ENDS and state["t0"] is not None:
                state["connect_s"] += now - state["t0"]
                state["t0"] = None
            if prior is not None:
                prior(event_name, info)

        request.extensions["trace"] = trace
        start = time.perf_counter()
        try:
            return self._inner.handle_request(request)
        finally:
            try:
                record(service, time.perf_counter() - start, state["new"], state["connect_s"])
            except Exception:  # noqa: BLE001 -- observability must never break a call
                logger.debug("db call timing record failed", exc_info=True)

    def close(self) -> None:
        self._inner.close()


def pool_enabled() -> bool:
    return os.environ.get("NOCTUS_HTTP_POOL", "1").strip().lower() not in ("0", "false", "no", "off")


def shared_transport() -> httpx.BaseTransport:
    """The process-wide HTTP/1.1 transport (built on first use)."""
    global _transport
    if _transport is None:
        with _lock:
            if _transport is None:
                _transport = TimingTransport(httpx.HTTPTransport(
                    http2=False,
                    # Connect-only retries: a refused/timed-out CONNECT is safe to
                    # retry, a request already sent is never replayed.
                    retries=1,
                    limits=httpx.Limits(
                        max_connections=MAX_CONNECTIONS,
                        max_keepalive_connections=MAX_KEEPALIVE_CONNECTIONS,
                        keepalive_expiry=KEEPALIVE_EXPIRY_S,
                    ),
                ))
    return _transport


def reset_shared_transport() -> None:
    """Close and drop the shared transport (tests; a fork-safe re-init)."""
    global _transport
    with _lock:
        old, _transport = _transport, None
    if old is not None:
        old.close()


class PooledHttpxClient(httpx.Client):
    """An ``httpx.Client`` riding the shared transport; ``close()`` leaves the
    transport (and every sibling client) alone."""

    def close(self) -> None:  # noqa: D401 - intentional no-op, see module docstring
        return None

    def aclose(self) -> None:  # gotrue/storage call `aclose` on their sync client
        return None


def pooled_client(
    *,
    base_url: Any = "",
    headers: Optional[Mapping[str, str]] = None,
    timeout: Any = None,
    follow_redirects: bool = True,
) -> httpx.Client:
    """A per-client ``httpx.Client`` on the shared pool (or a private HTTP/1.1
    client when the kill switch is on)."""
    kwargs: dict[str, Any] = dict(
        base_url=base_url,
        headers=headers,
        follow_redirects=follow_redirects,
    )
    if timeout is not None:
        kwargs["timeout"] = timeout
    if not pool_enabled():
        # Kill switch: private pool per client, still timed (each call is a new connection by design).
        return httpx.Client(transport=TimingTransport(httpx.HTTPTransport(http2=False)), **kwargs)
    return PooledHttpxClient(transport=shared_transport(), **kwargs)


# ─── async pool (Vista and other asyncio vendor clients) ─────────────────────
_async_clients: "weakref.WeakKeyDictionary[Any, httpx.AsyncClient]" = weakref.WeakKeyDictionary()


def shared_async_client() -> Optional[httpx.AsyncClient]:
    """ONE keep-alive ``httpx.AsyncClient`` per running event loop (an async client is bound to its loop, so it is
    keyed by loop -- a test's `asyncio.run` never inherits a closed loop's sockets). ``None`` when the pool is off
    (``NOCTUS_HTTP_POOL=0``) or there is no running loop: the caller then builds a per-call client as before.

    The caller passes `timeout` per request, never relies on the client default; callers never close this client."""
    if not pool_enabled():
        return None
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return None
    with _lock:
        client = _async_clients.get(loop)
        if client is None:
            client = httpx.AsyncClient(
                http2=False,
                limits=httpx.Limits(
                    max_connections=MAX_CONNECTIONS,
                    max_keepalive_connections=MAX_KEEPALIVE_CONNECTIONS,
                    keepalive_expiry=KEEPALIVE_EXPIRY_S,
                ),
            )
            _async_clients[loop] = client
    return client
