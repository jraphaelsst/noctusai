"""Metas stores -- `OrgTableStore` over the organ's tables + the one SQL aggregate (`event_totals`).

`metas_table_specs(cfg)` is the physical map + the UNIQUE guards the DDL carries (so the Fake refuses what the
database refuses). `FakeMetasStore` computes `event_totals` in Python for tests; `SupabaseMetasStore` calls the
`<prefix>event_totals` SQL function -- rankings and closings read a SQL SUM, never a Python loop over rows.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Optional, Protocol, Sequence, runtime_checkable

from noctusai_lib.domain._organ_common import (
    FakeOrgTableStore,
    OrgTableStore,
    SupabaseOrgTableStore,
    TableSpec,
    UniqueKey,
)
from noctusai_lib.domain.metas.config import MetasConfig
from noctusai_lib.domain.metas.sql import (
    EVENT_TOTALS_RPC,
    UQ_CLOSINGS_KEY,
    UQ_EVENTS_DEDUPE,
    UQ_GOALS_KEY,
    UQ_MEMBERS_ACTIVE,
    UQ_RULES_KEY,
    UQ_SETTINGS_ORG,
    UQ_TEAMS_NAME,
)


def metas_table_specs(cfg: MetasConfig) -> dict[str, TableSpec]:
    p = cfg.table_prefix
    return {
        "periods": TableSpec(cfg.table("periods"), defaults={"status": "open"}),
        "teams": TableSpec(
            cfg.table("teams"),
            unique=(UniqueKey(UQ_TEAMS_NAME.format(p=p), ("name",)),),
            defaults={"active": True},
        ),
        "team_members": TableSpec(
            cfg.table("team_members"),
            unique=(UniqueKey(UQ_MEMBERS_ACTIVE.format(p=p), ("team_id", "user_id"), where=lambda r: r.get("left_at") is None),),
            defaults={"role": "member", "left_at": None},
        ),
        "goals": TableSpec(
            cfg.table("goals"),
            unique=(
                UniqueKey(
                    UQ_GOALS_KEY.format(p=p),
                    ("scope", "subject_id", "period_id", "category"),
                    where=lambda r: r.get("period_id") is not None,
                    nulls_equal=("subject_id",),
                ),
            ),
            defaults={"current": 0, "status": "pending"},
        ),
        "goal_contributions": TableSpec(cfg.table("goal_contributions")),
        "settings": TableSpec(cfg.table("settings"), unique=(UniqueKey(UQ_SETTINGS_ORG.format(p=p), ("org_id",)),)),
        "rules": TableSpec(
            cfg.table("rules"),
            unique=(UniqueKey(UQ_RULES_KEY.format(p=p), ("period_id", "event_type", "modality"), nulls_equal=("period_id",)),),
            defaults={"modality": "default"},
        ),
        "events": TableSpec(
            cfg.table("events"),
            unique=(UniqueKey(UQ_EVENTS_DEDUPE.format(p=p), ("dedupe_key",)),),
            defaults={"points": 0, "fraction": 1, "manual_adjustment": False, "modality": "default"},
        ),
        "closings": TableSpec(
            cfg.table("closings"),
            unique=(UniqueKey(UQ_CLOSINGS_KEY.format(p=p), ("period_id", "member_id")),),
            timestamps=("created_at", "closed_at"),
        ),
    }


@runtime_checkable
class MetasStore(OrgTableStore, Protocol):
    def event_totals(
        self,
        org_id: str,
        start: date,
        end: date,
        *,
        members: Optional[Sequence[str]] = None,
        team_id: Optional[str] = None,
    ) -> list[dict]:
        """One row per member with events in `[start, end]`: `{member_id, team_id, points, value, counts}`."""
        ...


class FakeMetasStore(FakeOrgTableStore):
    """In-memory `MetasStore` (single process; mirrors the SQL aggregate)."""

    def __init__(self, cfg: MetasConfig) -> None:
        super().__init__(metas_table_specs(cfg))

    def event_totals(
        self,
        org_id: str,
        start: date,
        end: date,
        *,
        members: Optional[Sequence[str]] = None,
        team_id: Optional[str] = None,
    ) -> list[dict]:
        rows = self.select(
            "events",
            org_id,
            gte={"occurred_on": start.isoformat()},
            lte={"occurred_on": end.isoformat()},
            in_={"member_id": members} if members is not None else None,
            eq={"team_id": team_id} if team_id else None,
            order=(("occurred_on", False),),
        )
        out: dict[str, dict] = {}
        for r in rows:
            agg = out.setdefault(str(r["member_id"]), {"member_id": str(r["member_id"]), "team_id": None, "points": 0.0, "value": 0.0, "counts": {}})
            agg["points"] += float(r.get("points") or 0)
            agg["value"] += float(r.get("value") or 0)
            agg["counts"][r["event_type"]] = agg["counts"].get(r["event_type"], 0) + 1
            if r.get("team_id"):
                agg["team_id"] = str(r["team_id"])  # rows ascend by date: the latest team wins, like the SQL
        return list(out.values())


class SupabaseMetasStore(SupabaseOrgTableStore):
    """The Real `MetasStore` over a service-role client."""

    def __init__(self, client: Any, cfg: MetasConfig, *, schema: Optional[str] = None) -> None:
        super().__init__(client, metas_table_specs(cfg), schema=schema)
        self._cfg = cfg

    def event_totals(
        self,
        org_id: str,
        start: date,
        end: date,
        *,
        members: Optional[Sequence[str]] = None,
        team_id: Optional[str] = None,
    ) -> list[dict]:
        base = self._client.schema(self._schema) if self._schema else self._client
        params: dict[str, Any] = {"p_org": str(org_id), "p_from": start.isoformat(), "p_to": end.isoformat()}
        if members is not None:
            if not len(members):
                return []
            params["p_members"] = [str(m) for m in members]
        if team_id:
            params["p_team"] = str(team_id)
        rows = base.rpc(self._cfg.table(EVENT_TOTALS_RPC), params).execute().data or []
        return [dict(r, member_id=str(r["member_id"]), points=float(r["points"] or 0), value=float(r["value"] or 0), counts=r.get("counts") or {}) for r in rows]


def build_metas_store(
    cfg: MetasConfig,
    *,
    use_fake: bool = False,
    supabase_client: Any = None,
    schema: Optional[str] = None,
) -> MetasStore:
    """The Fake (`use_fake=True`) or the Supabase store. A missing client is a loud error, never a silent Fake."""
    if use_fake:
        return FakeMetasStore(cfg)
    if supabase_client is None:
        raise RuntimeError("build_metas_store: supabase_client is required when use_fake=False")
    return SupabaseMetasStore(supabase_client, cfg, schema=schema)


__all__ = ["FakeMetasStore", "MetasStore", "SupabaseMetasStore", "build_metas_store", "metas_table_specs"]
