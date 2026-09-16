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

**Backing table.** Core migration 046 creates
``public.user_permission_grants`` and ``has_permission(p_user_id,
p_permission)``; the Real implementation checks through the RPC and
administers grants (``list_grants`` / ``add_grant`` / ``remove_grant``)
on the bare table name, so it needs a ``public``-scoped service-role
client.
Per-consumer wiring (which grants exist, who can grant them) is
consumer-side and out of scope for the seed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class PermissionGrant:
    """One live grant — field names == `public.user_permission_grants` columns."""

    user_id: str
    permission: str
    granted_by: str | None = None
    created_at: datetime | None = None

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

    # --- grant administration ------------------------------------------
    # Issuance is authorized by the CALLER (e.g. a platform-admin-only
    # route); the repository only records it.

    async def list_grants(self, *, permission: str) -> list[PermissionGrant]:
        """Every live grant of `permission`, oldest first."""

    async def add_grant(
        self, *, user_id: Any, permission: str, granted_by: Any = None
    ) -> PermissionGrant:
        """Grant `permission` to `user_id`. Idempotent: an existing grant
        is returned unchanged (its original `granted_by` is kept)."""

    async def remove_grant(self, *, user_id: Any, permission: str) -> bool:
        """Revoke. `True` when a grant existed, `False` when it did not."""


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
        self._meta: dict[tuple[str, str], PermissionGrant] = {}

    async def has_permission(self, *, user_id: Any, permission: str) -> bool:
        return (str(user_id), permission) in self._grants

    async def list_grants(self, *, permission: str) -> list[PermissionGrant]:
        return [
            self._meta.get(key) or PermissionGrant(user_id=key[0], permission=key[1])
            for key in sorted(self._grants)
            if key[1] == permission
        ]

    async def add_grant(
        self, *, user_id: Any, permission: str, granted_by: Any = None
    ) -> PermissionGrant:
        key = (str(user_id), permission)
        if key in self._grants:
            return self._meta.get(key) or PermissionGrant(user_id=key[0], permission=permission)
        grant = PermissionGrant(
            user_id=key[0],
            permission=permission,
            granted_by=None if granted_by is None else str(granted_by),
            created_at=datetime.now(timezone.utc),
        )
        self._grants.add(key)
        self._meta[key] = grant
        return grant

    async def remove_grant(self, *, user_id: Any, permission: str) -> bool:
        key = (str(user_id), permission)
        if key not in self._grants:
            return False
        self._grants.discard(key)
        self._meta.pop(key, None)
        return True

    def grant(self, user_id: Any, permission: str) -> None:
        """Test/dev helper — add a grant. Not part of the Protocol (the
        Real implementation's grant-issuance path is the consumer's
        migration-shipped RPC/admin surface, not this repository)."""
        self._grants.add((str(user_id), permission))

    def revoke(self, user_id: Any, permission: str) -> None:
        """Test/dev helper — remove a grant, if present."""
        self._grants.discard((str(user_id), permission))
        self._meta.pop((str(user_id), permission), None)


# ---------------------------------------------------------------------------
# Real implementation (Supabase-client backed)
# ---------------------------------------------------------------------------


class RealSupabasePermissionGrantRepository:
    """Supabase-client backed `PermissionGrantRepository`.

    Core migration 046 ships the table + RPC below (verified byte-for-byte):

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
        table_name: str = "user_permission_grants",
    ) -> None:
        self._client = client
        self._rpc = rpc_name
        self._table = table_name

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

    # --- grant administration ------------------------------------------
    # BARE table name: the client is expected to be `public`-scoped (a
    # schema-qualified name resolves as `<schema>.<schema>.x` under
    # PostgREST — `KB § PATTERNS/backend/postgrest-schema-targeting.md`).
    # The table is written with the service role; its RLS grants
    # authenticated users SELECT on their own rows only.

    async def _rows(self, builder: Any) -> list[dict[str, Any]]:
        data = getattr(await self._execute(builder), "data", None)
        if not data:
            return []
        return data if isinstance(data, list) else [data]

    @staticmethod
    def _grant(row: dict[str, Any]) -> PermissionGrant:
        created = row.get("created_at")
        if isinstance(created, str):
            created = datetime.fromisoformat(created.replace("Z", "+00:00"))
        granted_by = row.get("granted_by")
        return PermissionGrant(
            user_id=str(row["user_id"]),
            permission=row["permission"],
            granted_by=None if granted_by is None else str(granted_by),
            created_at=created,
        )

    async def _find(self, user_id: Any, permission: str) -> PermissionGrant | None:
        rows = await self._rows(
            self._client.table(self._table)
            .select("user_id, permission, granted_by, created_at")
            .eq("user_id", str(user_id))
            .eq("permission", permission)
            .limit(1)
        )
        return self._grant(rows[0]) if rows else None

    async def list_grants(self, *, permission: str) -> list[PermissionGrant]:
        # A grant set is operator-issued and tiny; the explicit limit keeps
        # the read honest instead of silently capping at PostgREST's 1 000.
        rows = await self._rows(
            self._client.table(self._table)
            .select("user_id, permission, granted_by, created_at")
            .eq("permission", permission)
            .order("created_at")
            .limit(_MAX_LISTED_GRANTS)
        )
        if len(rows) >= _MAX_LISTED_GRANTS:
            raise RuntimeError(
                f"list_grants({permission!r}) reached {_MAX_LISTED_GRANTS} rows; "
                "paginate instead of truncating"
            )
        return [self._grant(r) for r in rows]

    async def add_grant(
        self, *, user_id: Any, permission: str, granted_by: Any = None
    ) -> PermissionGrant:
        existing = await self._find(user_id, permission)
        if existing is not None:
            return existing
        row = {"user_id": str(user_id), "permission": permission}
        if granted_by is not None:
            row["granted_by"] = str(granted_by)
        try:
            rows = await self._rows(self._client.table(self._table).insert(row))
        except Exception as exc:
            # A concurrent grant won the UNIQUE (user_id, permission) race:
            # the grant exists, which is what the caller asked for.
            if "23505" not in f"{getattr(exc, 'code', '')} {exc}":
                raise
            concurrent = await self._find(user_id, permission)
            if concurrent is None:
                raise
            return concurrent
        if not rows:
            raise RuntimeError(f"insert into {self._table} returned no row")
        return self._grant(rows[0])

    async def remove_grant(self, *, user_id: Any, permission: str) -> bool:
        rows = await self._rows(
            self._client.table(self._table)
            .delete()
            .eq("user_id", str(user_id))
            .eq("permission", permission)
        )
        return bool(rows)


_MAX_LISTED_GRANTS = 500


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
    "PermissionGrant",
    "PermissionGrantRepository",
    "RealSupabasePermissionGrantRepository",
    "make_permission_grant_repository",
]
