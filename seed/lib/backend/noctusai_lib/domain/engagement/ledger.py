"""Points ledger — Protocol + Fake + RealSupabase + factory.

Mirrors `noctusai_lib.domain.payments.event_inbox`'s canonical shape:
a `record` call is idempotent-on-insert (a duplicate never raises, and
never double-counts), and the Real implementation is **shape-only at
this phase** — it exercises the canonical Supabase query-builder calls
and the PostgREST `23505` unique-violation code, but ships no
migration. Unlike `EventInbox` (whose table lives in the seed's own
home schema, default `"public"`), this ledger's table lives in the
**consuming product's** schema — engagement points are a per-product
concept with no natural seed-owned home, so `schema_name` and
`table_name` are REQUIRED constructor arguments with no default. This
also avoids a coincidence default before a second consumer (this slice
ships community as the only one) has validated the rule/table shape
(`KB § PATTERNS/architect/seed-canonical-defaults.md`).
"""
from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable

from noctusai_lib.domain.engagement.value_objects import PointAward


@runtime_checkable
class PointsLedger(Protocol):
    """Storage seam for `PointAward`s. Implementations own persistence;
    the domain layer never assumes a schema shape beyond this Protocol.
    """

    def record(self, award: PointAward) -> bool:
        """Persist `award`. Returns `True` iff newly recorded, `False`
        iff `(member_id, idempotency_key)` was already claimed — a
        duplicate insert MUST NOT raise (mirrors `payments.event_inbox
        .EventInbox.claim`'s never-raise-on-duplicate contract) and
        MUST NOT double the member's points. This is the storage-layer
        backstop for the same idempotency guarantee `rules.evaluate`
        already enforces in-process from `history` — a second layer
        matters because two processes can race past `evaluate` with the
        same event before either has recorded it."""
        ...

    def history(
        self, member_id: str, *, source: str | None = None, action: str | None = None
    ) -> list[PointAward]:
        """Awards for `member_id`, optionally narrowed to one `source`
        and/or `action` — the exact shape `rules.evaluate`'s `history`
        parameter expects for cap enforcement."""
        ...

    def totals(self, member_ids: Sequence[str] | None = None) -> dict[str, int]:
        """Total points per member id across every recorded award.
        `member_ids=None` returns totals for every member the ledger
        has awards for. Feeds `leaderboard()` / `evaluate_badges()`."""
        ...


class InMemoryPointsLedger:
    """In-memory `PointsLedger` for dev + tests. Single-process only —
    matches `FakeEventInbox`'s own scope."""

    def __init__(self) -> None:
        self._awards: list[PointAward] = []
        self._claimed: set[tuple[str, str]] = set()

    def record(self, award: PointAward) -> bool:
        key = (award.member_id, award.idempotency_key)
        if key in self._claimed:
            return False
        self._claimed.add(key)
        self._awards.append(award)
        return True

    def history(
        self, member_id: str, *, source: str | None = None, action: str | None = None
    ) -> list[PointAward]:
        return [
            award
            for award in self._awards
            if award.member_id == member_id
            and (source is None or award.source == source)
            and (action is None or award.action == action)
        ]

    def totals(self, member_ids: Sequence[str] | None = None) -> dict[str, int]:
        result: dict[str, int] = {}
        allowed = set(member_ids) if member_ids is not None else None
        for award in self._awards:
            if allowed is not None and award.member_id not in allowed:
                continue
            result[award.member_id] = result.get(award.member_id, 0) + award.points
        return result

    def clear(self) -> None:
        """Reset between test cases."""
        self._awards.clear()
        self._claimed.clear()


class RealSupabasePointsLedger:
    """Supabase-client backed `PointsLedger`. **Shape-only at this
    phase** — the consuming product ships the migration:

        create table <table_name> (
            member_id text not null,
            source text not null,
            action text not null,
            points integer not null,
            occurred_at timestamptz not null,
            idempotency_key text not null,
            primary key (member_id, idempotency_key)
        );

    The unique `(member_id, idempotency_key)` primary key IS the
    idempotency guarantee — `record` attempts an INSERT and treats a
    `23505` (unique violation) as "already recorded" rather than an
    error, exactly like `payments.event_inbox.RealSupabaseEventInbox
    .claim`.
    """

    def __init__(self, client: Any, *, schema_name: str, table_name: str) -> None:
        self._client = client
        self._schema = schema_name
        self._table = table_name

    def _table_builder(self) -> Any:
        if self._schema == "public":
            return self._client.table(self._table)
        return self._client.schema(self._schema).from_(self._table)

    def record(self, award: PointAward) -> bool:
        builder = self._table_builder().insert(
            {
                "member_id": award.member_id,
                "source": award.source,
                "action": award.action,
                "points": award.points,
                "occurred_at": award.occurred_at.isoformat(),
                "idempotency_key": award.idempotency_key,
            }
        )
        try:
            builder.execute()
        except Exception as exc:  # noqa: BLE001 - narrowed below
            if _is_unique_violation(exc):
                return False
            raise
        return True

    def history(
        self, member_id: str, *, source: str | None = None, action: str | None = None
    ) -> list[PointAward]:
        query = self._table_builder().select("*").eq("member_id", member_id)
        if source is not None:
            query = query.eq("source", source)
        if action is not None:
            query = query.eq("action", action)
        response = query.execute()
        return [_row_to_award(row) for row in (response.data or [])]

    def totals(self, member_ids: Sequence[str] | None = None) -> dict[str, int]:
        query = self._table_builder().select("member_id,points")
        if member_ids is not None:
            query = query.in_("member_id", list(member_ids))
        response = query.execute()
        result: dict[str, int] = {}
        for row in response.data or []:
            result[row["member_id"]] = result.get(row["member_id"], 0) + row["points"]
        return result


def _row_to_award(row: dict[str, Any]) -> PointAward:
    occurred_at = row["occurred_at"]
    if isinstance(occurred_at, str):
        occurred_at = datetime.fromisoformat(occurred_at.replace("Z", "+00:00"))
    if occurred_at.tzinfo is None:
        occurred_at = occurred_at.replace(tzinfo=timezone.utc)
    return PointAward(
        member_id=row["member_id"],
        source=row["source"],
        action=row["action"],
        points=row["points"],
        occurred_at=occurred_at,
        idempotency_key=row["idempotency_key"],
    )


def _is_unique_violation(exc: Exception) -> bool:
    """True iff `exc` is a PostgREST `23505` (unique constraint
    violation). Duplicated from
    `payments.event_inbox._is_unique_violation` (not imported) for the
    same reason that module gives: this is never an HTTP-response path,
    so it must not import the FastAPI-facing
    `noctusai_lib.primitives.exceptions.postgrest_exception_handler`."""
    return getattr(exc, "code", None) == "23505"


def make_points_ledger(
    *,
    use_fake: bool = False,
    supabase_client: Any | None = None,
    schema_name: str | None = None,
    table_name: str | None = None,
) -> PointsLedger:
    """Construct a `PointsLedger`.

    Args:
        use_fake: when True, return `InMemoryPointsLedger` regardless of
            other arguments.
        supabase_client: live Supabase Python client. Required when
            `use_fake=False`.
        schema_name: Postgres schema hosting the points table — the
            CONSUMING product's schema (this seed ships no table of its
            own). Required when `use_fake=False`.
        table_name: table name within `schema_name`. Required when
            `use_fake=False`.

    Raises:
        RuntimeError: `use_fake=False` and `supabase_client`,
            `schema_name`, or `table_name` is missing.
    """
    if use_fake:
        return InMemoryPointsLedger()
    if supabase_client is None:
        raise RuntimeError(
            "make_points_ledger: supabase_client is required when use_fake=False"
        )
    if not schema_name or not table_name:
        raise RuntimeError(
            "make_points_ledger: schema_name and table_name are required when "
            "use_fake=False — this seed ships no canonical engagement-points "
            "table; the consuming product owns the schema + migration"
        )
    return RealSupabasePointsLedger(
        supabase_client, schema_name=schema_name, table_name=table_name
    )


__all__ = [
    "InMemoryPointsLedger",
    "PointsLedger",
    "RealSupabasePointsLedger",
    "make_points_ledger",
]
