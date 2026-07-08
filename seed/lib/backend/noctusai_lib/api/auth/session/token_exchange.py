"""``TokenExchanger`` — refresh→access exchange for cookie sessions.

The security-critical core of the httpOnly-cookie-session migration
(``project-history/roadmaps/erp-httponly-cookie-session-2026-07.md``). A
request authenticated by a ``nai_session`` cookie carries only an opaque
session id; to run a query under the user's RLS the backend needs a live
Supabase **access token**. The exchanger turns the session's stored
**refresh token** into a fresh access token — safely.

Three findings from the 2026-07-07 ``security`` threat model shape this
module; all three are BUILD GATES, not nice-to-haves:

- **SEC-1 — throwaway anon client.** The refresh MUST run on a fresh
  ``create_client(url, anon_key)``, NEVER the shared service-role singleton.
  ``supabase-py`` propagates the session established by ``refresh_session``
  onto the calling client's PostgREST auth layer; run on the shared admin
  client that downgrades EVERY later admin call from ``service_role`` to
  ``authenticated`` **process-wide** until restart — the 2026-05-23 core prod
  login outage. The throwaway client is discarded after the call, so the
  poisoning has nowhere to land. Keeper ``check_auth_session_mutation_on_
  shared_client`` guards consumers; this module keeps the exchange off the
  shared client by construction (the ``refresh_fn`` seam).
- **SEC-2 — no per-request refresh.** Supabase rotates the refresh token on
  every refresh and runs reuse-detection: two concurrent refreshes with the
  same token (every ERP page fires many API calls) look like a replay and
  revoke the WHOLE token family → random forced logouts under load. So we
  (a) cache the access token + expiry in the session record and refresh only
  within ``skew_seconds`` of expiry; (b) serialize refreshes per session with
  a Redis lock (``SET nai_lock:<sid> NX EX``) so only one worker refreshes
  while the others wait and read the freshly-published token; (c) write the
  rotated refresh token back so the next refresh uses the current token.
- **SEC-3** is the store's job (``redis_store.py``): the refresh + cached
  access token are encrypted at rest.

Seed-fake-real shape (``KB § PATTERNS/backend/seed-fake-real-adapter.md``):
Protocol (:class:`TokenExchanger`) + Fake (:class:`FakeTokenExchanger`) +
Real (:class:`SupabaseTokenExchanger`) + factory
(:func:`make_token_exchanger`). Consumers depend on the Protocol; tests use
the Fake; prod wires the Real via the factory.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
import time
from typing import Any, Awaitable, Callable, NamedTuple, Optional, Protocol

from noctusai_lib.api.auth.session.store import SessionStore
from noctusai_lib.api.auth.session.types import InvalidCredentialsError

logger = logging.getLogger(__name__)

# Refresh only when the cached access token is within this many seconds of
# expiry. A minute of skew absorbs clock drift + in-flight requests without
# forcing a refresh on every call.
_DEFAULT_SKEW_SECONDS = 60
# Per-session refresh lock TTL. Long enough for one upstream refresh round
# trip, short enough that a crashed refresher can't wedge a session for long.
_DEFAULT_LOCK_TTL_SECONDS = 5
_LOCK_KEY_PREFIX = "nai_lock:"


class TokenExchangeError(Exception):
    """Raised when a valid access token could not be obtained despite the
    session existing (e.g. persistent lock contention, or a refresh that
    yielded no session). Distinct from :class:`InvalidCredentialsError`
    (no such session) so the caller can 503 vs 401 appropriately."""


class RefreshResult(NamedTuple):
    """The outcome of one upstream refresh call.

    Fields mirror the Supabase ``Session``: ``access_token`` is the freshly
    minted short-lived token, ``refresh_token`` is the ROTATED refresh token
    (Supabase issues a new one each refresh — it MUST be written back), and
    ``expires_at`` is the access token's Unix-epoch expiry.
    """

    access_token: str
    refresh_token: str
    expires_at: int


# A ``refresh_fn`` takes the current refresh token and returns a
# ``RefreshResult``. It is a SYNC callable (the supabase-py SDK is sync) run
# off the event loop via ``asyncio.to_thread``. This is the SEC-1 seam: the
# real implementation runs the refresh on a throwaway anon client; tests
# inject a deterministic fake so no live Supabase is required.
RefreshFn = Callable[[str], RefreshResult]


class TokenExchanger(Protocol):
    """Turn a session id into a valid Supabase access token.

    The one method consumers call. Slice 2 wires it as a per-request
    dependency: resolve the cookie → ``AuthContext`` → ``access_token_for``
    → build an RLS-scoped client with ``make_supabase_client(...,
    access_token=<result>)``.
    """

    async def access_token_for(self, session_id: str) -> str:
        """Return a currently-valid access token for ``session_id``.

        Uses the cached token when it is not near expiry; otherwise refreshes
        upstream under a per-session lock and caches + rotates.

        Raises:
            InvalidCredentialsError: the session does not exist / has expired.
            TokenExchangeError: the token could not be obtained (contention
                timeout, or the refresh returned no session).
        """
        ...


class FakeTokenExchanger:
    """Deterministic in-memory ``TokenExchanger`` for dev + consumer tests.

    Returns a fixed token (or a per-session token from ``tokens``) without
    touching Supabase or Redis. Records the session ids it was asked about in
    ``calls`` so tests can assert the exchange was invoked. Use this to test a
    consumer's RLS-client wiring without standing up a real exchange.
    """

    def __init__(
        self,
        token: str = "fake-access-token",
        *,
        tokens: Optional[dict[str, str]] = None,
    ) -> None:
        self._token = token
        self._tokens = dict(tokens or {})
        self.calls: list[str] = []

    async def access_token_for(self, session_id: str) -> str:
        self.calls.append(session_id)
        return self._tokens.get(session_id, self._token)


class SupabaseTokenExchanger:
    """Real ``TokenExchanger`` — cache-first, lock-serialized, SEC-1/2 safe.

    Args:
        store: the session store (read/write the cached tokens).
        lock_client: a ``redis.asyncio``-compatible client used ONLY for the
            per-session refresh lock. In prod this is the same Redis the store
            uses (different key prefix); tests inject a ``fakeredis`` client.
        refresh_fn: SEC-1 seam — ``refresh_token -> RefreshResult``, run off
            the loop via ``asyncio.to_thread``. Defaults (via the factory) to
            a throwaway-anon-client refresh. Tests inject a fake.
        clock: returns the current Unix time (default ``time.time``); injected
            in tests to drive near-expiry logic deterministically.
        skew_seconds: refresh when within this many seconds of expiry.
        lock_ttl_seconds: TTL of the per-session refresh lock.
        max_attempts: how many acquire/wait cycles before giving up (a wedged
            or crashed refresher releases via lock TTL, so a retry succeeds).
        wait_poll_seconds: poll interval while waiting for another worker's
            refresh to publish.
    """

    def __init__(
        self,
        store: SessionStore,
        *,
        lock_client: Any,
        refresh_fn: RefreshFn,
        clock: Callable[[], float] = time.time,
        skew_seconds: int = _DEFAULT_SKEW_SECONDS,
        lock_ttl_seconds: int = _DEFAULT_LOCK_TTL_SECONDS,
        max_attempts: int = 3,
        wait_poll_seconds: float = 0.05,
    ) -> None:
        self._store = store
        self._lock = lock_client
        self._refresh_fn = refresh_fn
        self._clock = clock
        self._skew = skew_seconds
        self._lock_ttl = lock_ttl_seconds
        self._max_attempts = max(1, max_attempts)
        self._wait_poll = wait_poll_seconds

    @staticmethod
    def _lock_key(session_id: str) -> str:
        return f"{_LOCK_KEY_PREFIX}{session_id}"

    def _is_fresh(self, access_token: Optional[str], expires_at: Optional[int]) -> bool:
        """True when the cached access token exists and is not near expiry."""
        if not access_token or expires_at is None:
            return False
        return self._clock() < (expires_at - self._skew)

    async def access_token_for(self, session_id: str) -> str:
        for _attempt in range(self._max_attempts):
            tokens = await self._store.read_tokens(session_id)
            if tokens is None:
                raise InvalidCredentialsError("no session for that session id")

            # SEC-2 fast path: cached token still good → no upstream call.
            if self._is_fresh(tokens.access_token, tokens.access_expires_at):
                assert tokens.access_token is not None  # narrowed by _is_fresh
                return tokens.access_token

            lock_token = secrets.token_urlsafe(16)
            if await self._acquire_lock(session_id, lock_token):
                try:
                    # Double-check under the lock: a worker we raced with may
                    # have just published a fresh token.
                    tokens = await self._store.read_tokens(session_id)
                    if tokens is None:
                        raise InvalidCredentialsError(
                            "session vanished during refresh"
                        )
                    if self._is_fresh(tokens.access_token, tokens.access_expires_at):
                        assert tokens.access_token is not None
                        return tokens.access_token
                    return await self._refresh_and_store(session_id, tokens.refresh_token)
                finally:
                    await self._release_lock(session_id, lock_token)
            else:
                # Another worker holds the lock — wait for it to publish a
                # fresh token instead of firing a second (replay) refresh.
                published = await self._await_refresh(session_id)
                if published is not None:
                    return published
                # Timed out: the holder likely crashed and its lock expired.
                # Loop and try to become the refresher ourselves.
        raise TokenExchangeError(
            "could not obtain a fresh access token (lock contention) after "
            f"{self._max_attempts} attempts"
        )

    async def _refresh_and_store(self, session_id: str, refresh_token: str) -> str:
        """Run the upstream refresh (SEC-1) and cache + rotate (SEC-2)."""
        try:
            result = await asyncio.to_thread(self._refresh_fn, refresh_token)
        except InvalidCredentialsError:
            raise
        except Exception as exc:  # noqa: BLE001 — surface as a typed exchange error
            logger.warning("token refresh failed for a session: %s", exc)
            raise TokenExchangeError("upstream token refresh failed") from exc
        await self._store.write_tokens(
            session_id,
            refresh_token=result.refresh_token,  # rotated — write it back (SEC-2)
            access_token=result.access_token,
            access_expires_at=result.expires_at,
        )
        return result.access_token

    async def _acquire_lock(self, session_id: str, lock_token: str) -> bool:
        """``SET nai_lock:<sid> <token> NX EX <ttl>`` — True if we won it."""
        acquired = await self._lock.set(
            self._lock_key(session_id), lock_token, nx=True, ex=self._lock_ttl
        )
        return bool(acquired)

    async def _release_lock(self, session_id: str, lock_token: str) -> None:
        """Compare-and-delete: only drop the lock if we still own it.

        If our refresh overran the lock TTL, another worker may now hold the
        key — deleting it blindly would release THEIR lock. So we delete only
        when the stored token still matches ours. (A rare check-then-delete
        race remains but is bounded by the short TTL; the cost is at most one
        extra refresh, never a wrongful unlock of a different session.)
        """
        try:
            current = await self._lock.get(self._lock_key(session_id))
            if current == lock_token:
                await self._lock.delete(self._lock_key(session_id))
        except Exception as exc:  # noqa: BLE001 — never fail a request on unlock
            logger.warning("failed to release refresh lock (will TTL-expire): %s", exc)

    async def _await_refresh(self, session_id: str) -> Optional[str]:
        """Poll the store up to one lock-TTL for another worker's fresh token."""
        deadline = self._clock() + self._lock_ttl
        while self._clock() < deadline:
            await asyncio.sleep(self._wait_poll)
            tokens = await self._store.read_tokens(session_id)
            if tokens is None:
                return None
            if self._is_fresh(tokens.access_token, tokens.access_expires_at):
                return tokens.access_token
        return None


def make_default_refresh_fn(url: str, anon_key: str) -> RefreshFn:
    """Build the SEC-1 refresh seam: refresh on a THROWAWAY anon client.

    Every call constructs a fresh ``create_client(url, anon_key)`` and calls
    ``refresh_session`` on IT — never the shared service-role singleton — so
    the session ``supabase-py`` establishes on the client is discarded with
    the client and cannot poison a long-lived admin connection (SEC-1 / the
    2026-05-23 outage). Blocking (sync SDK); the exchanger runs it via
    ``asyncio.to_thread``.
    """

    def _refresh(refresh_token: str) -> RefreshResult:
        from supabase import create_client

        client = create_client(url, anon_key)  # THROWAWAY — SEC-1
        response = client.auth.refresh_session(refresh_token)
        session = getattr(response, "session", None)
        if session is None or not getattr(session, "access_token", None):
            raise InvalidCredentialsError(
                "supabase refresh_session returned no session (refresh token "
                "expired or revoked)"
            )
        expires_at = session.expires_at
        if expires_at is None:
            # Fall back to now + expires_in when the SDK omits the absolute
            # expiry, so the cache still has a bound.
            expires_at = int(time.time()) + int(getattr(session, "expires_in", 3600))
        return RefreshResult(
            access_token=session.access_token,
            refresh_token=session.refresh_token,
            expires_at=int(expires_at),
        )

    return _refresh


def make_token_exchanger(
    store: SessionStore,
    *,
    supabase_url: Optional[str] = None,
    supabase_anon_key: Optional[str] = None,
    lock_client: Any = None,
    refresh_fn: Optional[RefreshFn] = None,
    clock: Callable[[], float] = time.time,
    skew_seconds: int = _DEFAULT_SKEW_SECONDS,
) -> TokenExchanger:
    """Return the appropriate ``TokenExchanger`` for the environment.

    Prod path (a real Supabase + a lock client, or explicit ``refresh_fn``):
    returns a :class:`SupabaseTokenExchanger`. Everything else — no lock
    client and no Supabase creds — returns a :class:`FakeTokenExchanger`
    (dev / tests), so a product never hard-codes the Fake.

    Args:
        store: the session store the exchanger reads/writes tokens through.
        supabase_url / supabase_anon_key: used to build the default SEC-1
            throwaway-anon-client refresh when ``refresh_fn`` is not given.
        lock_client: ``redis.asyncio`` client for the per-session refresh
            lock (typically the same client the store uses). Required for the
            real path — without a lock the SEC-2 serialization is impossible.
        refresh_fn: override the refresh seam (tests inject a fake; advanced
            consumers can supply their own). When set, wins over the Supabase
            creds.
        clock / skew_seconds: forwarded to the real exchanger.

    Raises:
        ValueError: a lock client was given but there is no way to refresh
            (neither ``refresh_fn`` nor both Supabase creds) — a half-wired
            real path that would fail at first refresh. Fail at construction.
    """
    if lock_client is None:
        # No lock ⇒ cannot serialize refreshes safely ⇒ Fake.
        return FakeTokenExchanger()

    if refresh_fn is None:
        if not (supabase_url and supabase_anon_key):
            raise ValueError(
                "make_token_exchanger: a lock_client was provided but no way "
                "to refresh — pass refresh_fn, or both supabase_url and "
                "supabase_anon_key."
            )
        refresh_fn = make_default_refresh_fn(supabase_url, supabase_anon_key)

    return SupabaseTokenExchanger(
        store,
        lock_client=lock_client,
        refresh_fn=refresh_fn,
        clock=clock,
        skew_seconds=skew_seconds,
    )


__all__ = [
    "TokenExchanger",
    "FakeTokenExchanger",
    "SupabaseTokenExchanger",
    "RefreshResult",
    "RefreshFn",
    "TokenExchangeError",
    "make_default_refresh_fn",
    "make_token_exchanger",
]
