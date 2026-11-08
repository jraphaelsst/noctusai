"""`SupabaseGoalRepository` -- the Real `GoalRepository` over the organ's `goals` / `goal_contributions` tables.

Org-scoped (the repository is built for ONE org; a goal of another org is a `LookupError`, like a missing one).
`goal_from_row` is the single row -> `Goal` mapping the service reuses for progress.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Mapping, Optional

from noctusai_lib.domain._organ_common import OrgTableStore, make_org_table_store
from noctusai_lib.domain.metas.config import MetasConfig
from noctusai_lib.domain.metas.repository import GoalRepository, InMemoryGoalRepository
from noctusai_lib.domain.metas.store import metas_table_specs
from noctusai_lib.domain.metas.value_objects import (
    Contribution,
    Goal,
    GoalStatus,
    Period,
    PeriodKind,
    Target,
)


def to_date(value: Any) -> Optional[date]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def goal_from_row(row: Mapping[str, Any], *, period: Optional[Mapping[str, Any]] = None, contributions: tuple[Contribution, ...] = ()) -> Goal:
    """A `goals` row (+ its period row, + contributions) as the seed's `Goal` value object."""
    if period is not None:
        kind, start, end = PeriodKind(period["kind"]), to_date(period["starts_on"]), to_date(period["ends_on"])
    else:
        kind = PeriodKind.OPEN_ENDED
        start = to_date(row.get("starts_on")) or to_date(row.get("created_at")) or date.today()
        end = to_date(row.get("ends_on"))
    return Goal(
        id=str(row["id"]),
        target=Target(float(row["target"])),
        current=float(row.get("current") or 0),
        period=Period(kind=kind, start=start, end=end),
        status=GoalStatus(row.get("status") or "pending"),
        contributions=contributions,
    )


class SupabaseGoalRepository:
    """`GoalRepository` backed by an `OrgTableStore` (Supabase in production), scoped to `org_id`."""

    def __init__(self, store: OrgTableStore, cfg: MetasConfig, org_id: str) -> None:
        self._store = store
        self._cfg = cfg
        self._org = str(org_id)

    def _load(self, row: Mapping[str, Any]) -> Goal:
        period = self._store.get("periods", self._org, row["period_id"]) if row.get("period_id") else None
        contribs = tuple(
            Contribution(amount=float(c["amount"]), at=to_date(c["at"]))
            for c in self._store.select("goal_contributions", self._org, eq={"goal_id": row["id"]}, order=(("at", False),))
        )
        return goal_from_row(row, period=period, contributions=contribs)

    def fetch_goal(self, goal_id: str) -> Goal:
        row = self._store.get("goals", self._org, goal_id)
        if row is None:
            raise LookupError(f"goal not found: {goal_id!r}")
        return self._load(row)

    def list_goals(self, *, status: GoalStatus | None = None) -> list[Goal]:
        rows = self._store.select("goals", self._org, eq={"status": status.value} if status else None, order=(("created_at", False),))
        return [self._load(r) for r in rows]

    def update_goal(self, goal_id: str, *, current: float | None = None, status: GoalStatus | None = None) -> Goal:
        patch: dict[str, Any] = {}
        if current is not None:
            patch["current"] = current
        if status is not None:
            patch["status"] = status.value
        row = self._store.update("goals", self._org, goal_id, patch) if patch else self._store.get("goals", self._org, goal_id)
        if row is None:
            raise LookupError(f"goal not found: {goal_id!r}")
        return self._load(row)

    def record_contribution(self, goal_id: str, contribution: Contribution) -> None:
        if self._store.get("goals", self._org, goal_id) is None:
            raise LookupError(f"goal not found: {goal_id!r}")
        self._store.insert(
            "goal_contributions", self._org, [{"goal_id": str(goal_id), "amount": contribution.amount, "at": contribution.at.isoformat()}]
        )


def make_goal_repository(
    cfg: MetasConfig,
    *,
    org_id: str | None = None,
    use_fake: bool = False,
    supabase_client: Any = None,
    schema: str | None = None,
) -> GoalRepository:
    """`InMemoryGoalRepository` (`use_fake=True`) or the Supabase one for `org_id`. No silent Fake on a missing client."""
    if use_fake:
        return InMemoryGoalRepository()
    if supabase_client is None or not org_id:
        raise RuntimeError("make_goal_repository: supabase_client and org_id are required when use_fake=False")
    store = make_org_table_store(metas_table_specs(cfg), supabase_client=supabase_client, schema=schema)
    return SupabaseGoalRepository(store, cfg, org_id)


__all__ = ["SupabaseGoalRepository", "goal_from_row", "make_goal_repository", "to_date"]
