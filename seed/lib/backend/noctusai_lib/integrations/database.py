"""
Supabase database client factory for all NoctusAI backends.

Provides a parameterized factory function that each product backend
calls with its own schema and settings. The factory handles both
user-authenticated clients (RLS) and service-role clients (admin).

🔴 EVERY CLIENT IS FORCED ONTO HTTP/1.1 — see `force_postgrest_http1`.
"""
from __future__ import annotations

import logging
from typing import Optional

import httpx
from supabase import create_client, Client
from supabase.lib.client_options import ClientOptions

logger = logging.getLogger(__name__)

#: Marks a session we have already replaced, so a re-entrant call is a no-op
#: rather than a second pool.
_HTTP1_FLAG = "_noctus_http1_forced"


def force_postgrest_http1(client: Client) -> Client:
    """Replace PostgREST's HTTP/2 session with an HTTP/1.1 one.

    🔴 WHY THIS EXISTS — A REPRODUCED PRODUCTION OUTAGE
    ---------------------------------------------------
    `postgrest/_sync/client.py` hardcodes `http2=True` and exposes no way to
    turn it off (`ClientOptions` has no field for it, checked on
    supabase 2.9.1 / postgrest 0.17.2).

    httpx's SYNC HTTP/2 transport is not safe to share across threads, and
    FastAPI runs every non-async endpoint in a threadpool against ONE cached
    client. Concurrent requests corrupt the shared connection's stream state.

    Measured against the live PostgREST, 8 concurrent threads on one client:

        http2=True   →  3 ok, 5 errors
                        RuntimeError: deque mutated during iteration
                        RemoteProtocolError: ConnectionTerminated
        http2=False  →  8 ok, 0 errors   (repeated three times)

    In production this took `GET /api/funil` down completely: it fires six
    batched follow-up reads while the SPA loads other endpoints in parallel,
    so it lost the race every time — 4 of 4 requests returned 500 with
    `httpx.LocalProtocolError: Received pseudo-header in trailer`. The error
    surfaced from `pipeline/configs.py`, which was innocent; the bug was one
    layer down and shared by every product.

    HTTP/1.1 costs nothing here. PostgREST is one hop away inside the
    network, httpx keeps a keep-alive pool either way, and the requests are
    small. What HTTP/2 was buying was multiplexing on a connection we cannot
    safely multiplex on.

    Idempotent, and NEVER silent: if the session cannot be replaced (a future
    postgrest changes shape), the client is returned working but unpatched
    and the reason is logged at WARNING. Swallowing that would leave the
    outage in place with nothing to find.
    """
    try:
        postgrest = client.postgrest
        session = postgrest.session
    except Exception as exc:  # noqa: BLE001 - never break client construction
        logger.warning(
            "supabase: could not reach postgrest session to force HTTP/1.1 "
            "(%s: %s) — the client works, but the HTTP/2 thread-safety bug "
            "is NOT mitigated on it.",
            type(exc).__name__,
            exc,
        )
        return client

    if getattr(session, _HTTP1_FLAG, False):
        return client

    try:
        replacement = httpx.Client(
            base_url=session.base_url,
            headers=session.headers,
            timeout=session.timeout,
            follow_redirects=True,
            http2=False,
        )
        setattr(replacement, _HTTP1_FLAG, True)
        postgrest.session = replacement
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "supabase: could not install the HTTP/1.1 session (%s: %s) — the "
            "client works, but the HTTP/2 thread-safety bug is NOT mitigated "
            "on it.",
            type(exc).__name__,
            exc,
        )
        return client

    # Closed only AFTER the swap succeeded: closing first would leave the
    # client without a usable session if the constructor above raised.
    try:
        session.close()
    except Exception:  # noqa: BLE001
        # The replacement is already in place; a pool that failed to close is
        # a leaked socket, not a broken client. Logged, not raised.
        logger.debug("supabase: old postgrest session did not close cleanly")

    return client


def make_supabase_client(
    url: str,
    anon_key: str,
    service_role_key: str,
    schema: Optional[str] = None,
    access_token: Optional[str] = None,
) -> Client:
    """
    Create a Supabase client with the given configuration.

    Args:
        url: Supabase project URL
        anon_key: Supabase anon/public key
        service_role_key: Supabase service role key (admin access)
        schema: PostgreSQL schema to target (e.g., "erp", "personal-finance").
                None uses the default "public" schema.
        access_token: If provided, creates a client authenticated as this user
                      (respects RLS). If None, uses the service role key.

    Returns:
        Configured Supabase Client instance
    """
    options = ClientOptions(schema=schema) if schema else ClientOptions()

    if access_token:
        # Client authenticated as the user (respects RLS)
        client = create_client(url, anon_key, options=options)
        client.auth.set_session(access_token, "")
        return force_postgrest_http1(client)
    else:
        # Service role client (bypasses RLS — use for server-side operations)
        return force_postgrest_http1(
            create_client(url, service_role_key, options=options)
        )
