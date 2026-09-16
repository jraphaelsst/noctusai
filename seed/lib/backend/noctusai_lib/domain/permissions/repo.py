"""Permission-grant repository — Protocol + Fake + RealSupabase + factory.

Mirrors the canonical Protocol+Fake+Real+factory shape per
`KB § PATTERNS/backend/seed-fake-real-adapter.md` (same shape as
`noctusai_lib.domain.jobs.repo`). Consumers wire
`make_permission_grant_repository(use_fake=True)` for dev/tests and
`make_permission_grant_repository(supabase_client=client)` in
production.

**Product-agnostic by construction.** ``permission`` is an opaque
string (e.g. ``"photo_curator:edit"``) the CALLER defines — this module
never mentions a product name, a feature, or a resource shape. The
first consumer is a future ``photo_curator`` capability, but nothing
here may couple to it; this seed ships to an external app in Phase 2
and must carry zero product coupling by the time it does.

**Shape-only at this phase.** The Real implementation exercises the
canonical Supabase Python-client RPC call, but the migration that
creates the Core table ``public.user_permission_grants`` and its
``has_permission(p_user_id, p_permission)`` SQL helper is a LATER
slice — applying a migration needs owner consent, out of scope here.
Per-consumer wiring (which grants exist, who can grant them) is
consumer-side and out of scope for the seed.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class PermissionGrantRepository(Protocol):
    """Async repository surface every named-permission consumer depends on.

    Implementations:
    - `FakePermissionGrantRepository` — in-memory grant set for dev + tests.
    - `RealSupabasePermissionGrantRepository` — production-shaped
      Supabase-client-backed implementation. Consumer ships the
      `user_permission_grants` table + `has_permission()` RPC migration.
    """

    async def has_permission(self, *, user_id: Any, permission: str) -> bool:
        """Return True iff `user_id` holds a live grant for `permission`.

        `user_id` is anything `str()`-able (a Supabase auth user id).
        `permission` is an opaque, caller-defined grant name — this
        Protocol imposes no vocabulary on it.
        """


# ---------------------------------------------------------------------------
# Fake implementation
# ---------------------------------------------------------------------------


class FakePermissionGrantRepository:
    """In-memory `PermissionGrantRepository` for dev + tests.

    Grants are stored as a set of `(str(user_id), permission)` pairs.
    Deterministic, single-process, no network.
    """

    def __init__(self, initial_grants: Any = None) -> None:
        """`initial_grants`: an iterable of `(user_id, permission)` pairs
        seeded at construction time, or `None` for an empty grant set."""
        self._grants: set[tuple[str, str]] = {
            (str(user_id), permission) for user_id, permission in (initial_grants or ())
        }

    async def has_permission(self, *, user_id: Any, permission: str) -> bool:
        return (str(user_id), permission) in self._grants

    def grant(self, user_id: Any, permission: str) -> None:
        """Test/dev helper — add a grant. Not part of the Protocol (the
        Real implementation's grant-issuance path is the consumer's
        migration-shipped RPC/admin surface, not this repository)."""
        self._grants.add((str(user_id), permission))

    def revoke(self, user_id: Any, permission: str) -> None:
        """Test/dev helper — remove a grant, if present."""
        self._grants.discard((str(user_id), permission))


# ---------------------------------------------------------------------------
# Real implementation (Supabase-client backed)
# ---------------------------------------------------------------------------


class RealSupabasePermissionGrantRepository:
    """Supabase-client backed `PermissionGrantRepository`.

    **Shape-only at this phase.** Consumer ships a migration creating:

        create table public.user_permission_grants (
            id uuid primary key default gen_random_uuid(),
            user_id uuid not null references auth.users(id),
            permission text not null,
            granted_by uuid references auth.users(id),
            created_at timestamptz not null default now(),
            unique (user_id, permission)
        );

        create or replace function public.has_permission(
            p_user_id uuid,
            p_permission text
        ) returns boolean
        language sql stable security definer
        as $$
            select exists (
                select 1 from public.user_permission_grants
                where user_id = p_user_id and permission = p_permission
            );
        $$;

    Delegating the check to a SQL function (rather than a bare
    `.select()` + row-count check here) keeps the authorization
    predicate in ONE place — the DB — so a future revocation-expiry or
    audit-trail column change never requires touching this Python
    call site.
    """

    def __init__(
        self,
        client: Any,
        *,
        rpc_name: str = "has_permission",
    ) -> None:
        self._client = client
        self._rpc = rpc_name

    async def _execute(self, builder: Any) -> Any:
        """Tiny helper so test mocks can return either a sync result
        (MockSupabaseClient.execute returns a value directly) or an
        awaitable (real async client). Mirrors
        `noctusai_lib.domain.jobs.repo.RealSupabaseJobRepository._execute`.
        """
        result = builder.execute()
        if hasattr(result, "__await__"):
            return await result
        return result

    async def has_permission(self, *, user_id: Any, permission: str) -> bool:
        rpc_builder = self._client.rpc(
            self._rpc,
            {"p_user_id": str(user_id), "p_permission": permission},
        )
        result = await self._execute(rpc_builder)
        return bool(getattr(result, "data", False))


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def make_permission_grant_repository(
    *,
    use_fake: bool = False,
    supabase_client: Any | None = None,
    rpc_name: str = "has_permission",
    initial_grants: Any = None,
) -> PermissionGrantRepository:
    """Construct a `PermissionGrantRepository` for a consumer.

    Args:
        use_fake: when True, return a `FakePermissionGrantRepository`
            regardless of other arguments. Use in dev / tests / when no
            Supabase client is wired yet.
        supabase_client: live Supabase Python client, scoped to the
            `public` schema (`user_permission_grants` is a Core table).
            Required when `use_fake=False`.
        rpc_name: name of the consumer-shipped `has_permission` RPC
            function.
        initial_grants: only used when `use_fake=True` — seeds the
            Fake's grant set. See `FakePermissionGrantRepository`.

    Returns:
        Concrete `PermissionGrantRepository` implementation.
    """
    if use_fake:
        return FakePermissionGrantRepository(initial_grants)
    if supabase_client is None:
        raise RuntimeError(
            "make_permission_grant_repository: supabase_client is required "
            "when use_fake=False"
        )
    return RealSupabasePermissionGrantRepository(supabase_client, rpc_name=rpc_name)


__all__ = [
    "FakePermissionGrantRepository",
    "PermissionGrantRepository",
    "RealSupabasePermissionGrantRepository",
    "make_permission_grant_repository",
]
