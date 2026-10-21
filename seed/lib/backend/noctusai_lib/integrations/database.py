"""
Supabase database client factory for all NoctusAI backends.

Provides a parameterized factory function that each product backend
calls with its own schema and settings. The factory handles both
user-authenticated clients (RLS) and service-role clients (admin).

🔴 EVERY CLIENT IS FORCED ONTO HTTP/1.1 — see `force_postgrest_http1`.

🔴 EVERY CLIENT SHARES ONE KEEP-ALIVE POOL, AND A USER CLIENT HAS NO GOTRUE SESSION
(2026-10-21) — see `http_pool` and `make_supabase_client`. A user JWT goes
straight into the PostgREST/Storage `Authorization` header (RLS reads it), not
through `auth.set_session`, which cost a second Auth `get_user` per request and a
refresh Timer thread per client.
KB § PATTERNS/backend/request-path-latency.md
"""
from __future__ import annotations

import logging
from typing import Optional

import httpx
from postgrest import SyncPostgrestClient
from storage3 import SyncStorageClient
from supabase import create_client, Client, SupabaseAuthClient
from supabase.lib.client_options import ClientOptions

from noctusai_lib.integrations.http_pool import pooled_client

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


class _PooledPostgrest(SyncPostgrestClient):
    """PostgREST client whose session rides the shared HTTP/1.1 pool."""

    def create_session(self, base_url, headers, timeout, verify=True, proxy=None):
        session = pooled_client(base_url=base_url, headers=headers, timeout=timeout)
        setattr(session, _HTTP1_FLAG, True)  # `force_postgrest_http1` stays a no-op
        return session


class _PooledStorage(SyncStorageClient):
    """Storage client whose session rides the shared HTTP/1.1 pool."""

    def _create_session(self, base_url, headers, timeout, verify=True, proxy=None):
        return pooled_client(base_url=base_url, headers=headers, timeout=timeout)


class _PooledSupabaseClient(Client):
    """``supabase.Client`` whose PostgREST / Storage / Auth HTTP sessions share
    ONE process-wide HTTP/1.1 connection pool (see ``http_pool``) instead of
    each building a private pool + TLS context per client.

    Overrides only the three private ``_init_*`` factories ``Client.__init__``
    calls (stable across the pinned supabase 2.9.x); everything else is the
    stock client. :func:`_build_pooled` falls back LOUDLY to a stock client if
    a future supabase changes those hooks.
    """

    @staticmethod
    def _init_postgrest_client(rest_url, headers, schema, timeout=None, verify=True, proxy=None):
        kwargs = {} if timeout is None else {"timeout": timeout}
        return _PooledPostgrest(rest_url, headers=headers, schema=schema, **kwargs)

    @staticmethod
    def _init_storage_client(storage_url, headers, storage_client_timeout=None, verify=True, proxy=None):
        args = () if storage_client_timeout is None else (storage_client_timeout,)
        return _PooledStorage(storage_url, headers, *args)

    @staticmethod
    def _init_supabase_auth_client(auth_url, client_options, verify=True, proxy=None):
        return SupabaseAuthClient(
            url=auth_url,
            auto_refresh_token=client_options.auto_refresh_token,
            persist_session=client_options.persist_session,
            storage=client_options.storage,
            headers=client_options.headers,
            flow_type=client_options.flow_type,
            http_client=pooled_client(),
        )


def _build_pooled(url: str, key: str, options: ClientOptions) -> Client:
    """A pooled client, or (loudly) a stock one if the pooling hooks broke."""
    try:
        client = _PooledSupabaseClient.create(url, key, options)
        client.postgrest  # force the lazy PostgREST build NOW, so a hook failure is seen here
        return client
    except Exception as exc:  # noqa: BLE001 - never break client construction
        logger.warning(
            "supabase: could not build a pooled client (%s: %s) — falling back to a stock "
            "client; every request pays a TLS handshake until this is fixed.",
            type(exc).__name__,
            exc,
        )
        return create_client(url, key, options=options)


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
                      (respects RLS) — the JWT is set on the PostgREST/Storage
                      headers directly; `client.auth` carries NO session.
                      If None, uses the service role key.

    Returns:
        Configured Supabase Client instance
    """
    if access_token:
        # Client authenticated as the user (respects RLS).
        #
        # The user's JWT goes straight into the headers PostgREST/Storage are
        # built from — NOT through `client.auth.set_session`, which (a) calls
        # Supabase Auth `get_user` a SECOND time per request (the request's
        # own token validation already did) and (b) starts a gotrue refresh
        # Timer thread per client. RLS reads `Authorization: Bearer <jwt>`, so
        # it sees the same user either way. `client.auth` carries no session
        # here; nothing in the fleet calls session-bound auth methods on a
        # user-scoped client (token validation uses the service-role client).
        options = _options(schema)
        options.headers["Authorization"] = f"Bearer {access_token}"
        return _finish(url, anon_key, options)
    # Service role client (bypasses RLS — use for server-side operations)
    return _finish(url, service_role_key, _options(schema))


def _options(schema: Optional[str]) -> ClientOptions:
    # No gotrue session is ever established on these clients, so there is
    # nothing to refresh or persist: switch both off so no Timer thread starts.
    kwargs = {"auto_refresh_token": False, "persist_session": False}
    if schema:
        kwargs["schema"] = schema
    return ClientOptions(**kwargs)


def _finish(url: str, key: str, options: ClientOptions) -> Client:
    from noctusai_lib.integrations.http_pool import pool_enabled

    if pool_enabled():
        return _build_pooled(url, key, options)
    return force_postgrest_http1(create_client(url, key, options=options))
