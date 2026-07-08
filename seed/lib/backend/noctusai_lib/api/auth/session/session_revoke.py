"""``SessionRevoker`` — upstream (GoTrue) session revocation for logout.

SEC-4 of the httpOnly-cookie-session threat model
(``project-history/roadmaps/erp-httponly-cookie-session-2026-07.md``): a
logout (or password change) MUST **revoke the Supabase session upstream**,
not merely delete the server-side session row + clear the cookie. Otherwise
the refresh token held in the (now-deleted) session record is still VALID at
Supabase — anyone who captured it (a leaked Redis read before deletion, a
proxy log) can keep minting access tokens after the user "logged out". Real
logout = the refresh token family is dead at GoTrue.

Shape mirrors the :class:`~noctusai_lib.api.auth.session.token_exchange`
seam — Protocol + Fake + Real + factory
(``KB § PATTERNS/backend/seed-fake-real-adapter.md``):

- **SEC-1 reuse.** The revoke runs on a THROWAWAY ``create_client(url,
  anon_key)`` (``make_default_revoke_fn``), never the shared admin singleton
  — same process-wide-RLS-poison reason as the exchanger.
- **Best-effort-but-logged (SEC-4).** The upstream call can fail (network,
  an already-expired token). Logout MUST still clear the cookie + delete the
  session row regardless, so :meth:`SupabaseSessionRevoker.revoke` never
  raises into the logout path — it logs the failure and returns ``False`` (no
  silent swallow: the caller can surface/metric the miss). ``True`` means the
  upstream revoke was confirmed.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Callable, Optional, Protocol

logger = logging.getLogger(__name__)

# A ``revoke_fn`` takes the session's (rotated) refresh token and revokes the
# session upstream, raising on failure. SYNC (the supabase-py SDK is sync),
# run off the event loop via ``asyncio.to_thread``. SEC-1 seam: the real one
# runs on a throwaway anon client; tests inject a deterministic fake.
RevokeFn = Callable[[str], None]


class SessionRevoker(Protocol):
    """Revoke a Supabase session upstream at logout (SEC-4)."""

    async def revoke(self, refresh_token: str) -> bool:
        """Best-effort upstream revoke. Returns ``True`` on confirmed
        revocation, ``False`` on a logged failure. NEVER raises — logout must
        proceed (clear cookie + delete row) even when the upstream call
        fails."""
        ...


class FakeSessionRevoker:
    """Deterministic in-memory ``SessionRevoker`` for dev + consumer tests.

    Records every refresh token it was asked to revoke in ``revoked`` and
    returns ``succeed`` (default ``True``) without touching Supabase. Set
    ``succeed=False`` to simulate an upstream failure and assert the caller
    still completes the logout.
    """

    def __init__(self, *, succeed: bool = True) -> None:
        self._succeed = succeed
        self.revoked: list[str] = []

    async def revoke(self, refresh_token: str) -> bool:
        self.revoked.append(refresh_token)
        return self._succeed


class SupabaseSessionRevoker:
    """Real ``SessionRevoker`` — revokes on a throwaway anon client (SEC-1).

    Args:
        revoke_fn: SEC-1 seam — ``refresh_token -> None`` (raises on failure),
            run off the loop via ``asyncio.to_thread``. Defaults (via the
            factory) to a throwaway-anon-client GoTrue sign-out. Tests inject a
            fake.
    """

    def __init__(self, revoke_fn: RevokeFn) -> None:
        self._revoke_fn = revoke_fn

    async def revoke(self, refresh_token: str) -> bool:
        if not refresh_token:
            # Nothing to revoke (e.g. a session created before token capture) —
            # not a failure, just a no-op.
            return True
        try:
            await asyncio.to_thread(self._revoke_fn, refresh_token)
            return True
        except Exception as exc:  # noqa: BLE001 — SEC-4: log, never raise into logout
            logger.warning(
                "upstream session revoke failed (logout proceeds anyway): %s",
                exc,
            )
            return False


def make_default_revoke_fn(url: str, anon_key: str) -> RevokeFn:
    """Build the SEC-1/SEC-4 revoke seam: sign out on a THROWAWAY anon client.

    Establishes the session on a fresh ``create_client(url, anon_key)`` from
    the stored refresh token, then calls GoTrue ``sign_out`` (scope ``local``
    — revoke THIS session's token family, not every device the user is on).
    The throwaway client is discarded, so the session it briefly held cannot
    poison a long-lived admin connection (SEC-1). Blocking; the revoker runs
    it via ``asyncio.to_thread``.
    """

    def _revoke(refresh_token: str) -> None:
        from supabase import create_client

        client = create_client(url, anon_key)  # THROWAWAY — SEC-1
        # Establish the session from the refresh token so sign_out has a
        # session to revoke, then kill it upstream.
        client.auth.refresh_session(refresh_token)
        try:
            from gotrue.types import SignOutOptions

            client.auth.sign_out(SignOutOptions(scope="local"))
        except ImportError:  # pragma: no cover - older gotrue without the type
            client.auth.sign_out()

    return _revoke


def make_session_revoker(
    *,
    supabase_url: Optional[str] = None,
    supabase_anon_key: Optional[str] = None,
    revoke_fn: Optional[RevokeFn] = None,
) -> SessionRevoker:
    """Return the appropriate ``SessionRevoker`` for the environment.

    Real path (explicit ``revoke_fn`` OR both Supabase creds) →
    :class:`SupabaseSessionRevoker`. Otherwise (dev / tests) →
    :class:`FakeSessionRevoker`, so a product never hard-codes the Fake.

    Raises:
        ValueError: never — a fully-unconfigured call returns the Fake. (The
            exchanger's factory raises on a half-wired real path because it
            has a lock_client signal; the revoker has no such half-state.)
    """
    if revoke_fn is None and supabase_url and supabase_anon_key:
        revoke_fn = make_default_revoke_fn(supabase_url, supabase_anon_key)
    if revoke_fn is not None:
        return SupabaseSessionRevoker(revoke_fn)
    return FakeSessionRevoker()


__all__ = [
    "SessionRevoker",
    "FakeSessionRevoker",
    "SupabaseSessionRevoker",
    "RevokeFn",
    "make_default_revoke_fn",
    "make_session_revoker",
]
