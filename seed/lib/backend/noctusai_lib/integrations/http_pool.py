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

import logging
import os
import threading
from typing import Any, Mapping, Optional

import httpx

logger = logging.getLogger(__name__)

#: Seconds an idle pooled connection is kept. Below the idle timeout of the
#: Supabase edge (>= 60 s) so we close first rather than reuse a connection the
#: server already dropped.
KEEPALIVE_EXPIRY_S = 20.0
MAX_CONNECTIONS = 200
MAX_KEEPALIVE_CONNECTIONS = 50

_lock = threading.Lock()
_transport: Optional[httpx.HTTPTransport] = None


def pool_enabled() -> bool:
    return os.environ.get("NOCTUS_HTTP_POOL", "1").strip().lower() not in ("0", "false", "no", "off")


def shared_transport() -> httpx.HTTPTransport:
    """The process-wide HTTP/1.1 transport (built on first use)."""
    global _transport
    if _transport is None:
        with _lock:
            if _transport is None:
                _transport = httpx.HTTPTransport(
                    http2=False,
                    # Connect-only retries: a refused/timed-out CONNECT is safe to
                    # retry, a request already sent is never replayed.
                    retries=1,
                    limits=httpx.Limits(
                        max_connections=MAX_CONNECTIONS,
                        max_keepalive_connections=MAX_KEEPALIVE_CONNECTIONS,
                        keepalive_expiry=KEEPALIVE_EXPIRY_S,
                    ),
                )
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
        return httpx.Client(http2=False, **kwargs)
    return PooledHttpxClient(transport=shared_transport(), **kwargs)
