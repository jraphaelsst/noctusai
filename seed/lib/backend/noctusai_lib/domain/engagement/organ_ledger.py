"""Org-scoped points ledger over the organ's `eng_points` table (`OrgPointsLedger` Real + `FakeOrgPointsLedger` + factory).

Implements the `PointsLedger` Protocol (so `rules.evaluate` / `leaderboard` work unchanged) with two additions the
multi-tenant organ needs: every call is scoped to ONE org, and `totals` takes a `since` / `until` window and reads a SQL SUM
(`<prefix>points_totals`). `record` is idempotent on `(org_id, member_id, idempotency_key)` (23505 => `False`, never a raise).
`erase_member` is the LGPD delete-by-subject (the one gated DELETE path). The older product-schema `RealSupabasePointsLedger`
(no org column) stays for the products that own their own table.
"""
from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any, Optional

from noctusai_lib.domain.engagement.config import EngagementConfig
from noctusai_lib.domain.engagement.ledger import InMemoryPointsLedger, _row_to_award
from noctusai_lib.domain.engagement.sql import POINTS_ERASE_RPC, POINTS_TOTALS_RPC
from noctusai_lib.domain.engagement.value_objects import PointAward
from noctusai_lib.primitives.postgrest_errors import is_unique_violation


class FakeOrgPointsLedger(InMemoryPointsLedger):
    """In-memory org ledger: one instance = one org's rows (the service builds one per org in tests)."""

    def totals(  # type: ignore[override]
        self, member_ids: Sequence[str] | None = None, *, since: Optional[datetime] = None, until: Optional[datetime] = None
    ) -> dict[str, int]:
        result: dict[str, int] = {}
        allowed = set(member_ids) if member_ids is not None else None
        for award in self._awards:
            if allowed is not None and award.member_id not in allowed:
                continue
            if (since is not None and award.occurred_at < since) or (until is not None and award.occurred_at >= until):
                continue
            result[award.member_id] = result.get(award.member_id, 0) + award.points
        return result

    def erase_member(self, member_id: str) -> int:
        gone = [a for a in self._awards if a.member_id == member_id]
        self._awards = [a for a in self._awards if a.member_id != member_id]
        self._claimed = {k for k in self._claimed if k[0] != member_id}
        return len(gone)


class OrgPointsLedger:
    """The Real ledger for ONE org over a service-role client (schema-pinned, or a root client plus `schema=`)."""

    def __init__(self, client: Any, cfg: EngagementConfig, org_id: str, *, schema: Optional[str] = None) -> None:
        self._client = client
        self._cfg = cfg
        self._org = str(org_id)
        self._schema = schema

    def _base(self) -> Any:
        return self._client.schema(self._schema) if self._schema else self._client

    def _table(self) -> Any:
        return self._base().table(self._cfg.table("points"))

    def record(self, award: PointAward) -> bool:
        builder = self._table().insert(
            {
                "org_id": self._org,
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
        except Exception as exc:  # noqa: BLE001 - narrowed: only a unique violation means "already recorded"
            if is_unique_violation(exc):
                return False
            raise
        return True

    def history(self, member_id: str, *, source: str | None = None, action: str | None = None) -> list[PointAward]:
        query = self._table().select("*").eq("org_id", self._org).eq("member_id", member_id)
        if source is not None:
            query = query.eq("source", source)
        if action is not None:
            query = query.eq("action", action)
        return [_row_to_award(row) for row in (query.execute().data or [])]

    def totals(
        self, member_ids: Sequence[str] | None = None, *, since: Optional[datetime] = None, until: Optional[datetime] = None
    ) -> dict[str, int]:
        params: dict[str, Any] = {"p_org": self._org}
        if member_ids is not None:
            if not len(member_ids):
                return {}
            params["p_members"] = [str(m) for m in member_ids]
        if since is not None:
            params["p_since"] = since.isoformat()
        if until is not None:
            params["p_until"] = until.isoformat()
        rows = self._base().rpc(self._cfg.table(POINTS_TOTALS_RPC), params).execute().data or []
        return {str(r["member_id"]): int(r["points"]) for r in rows}

    def erase_member(self, member_id: str) -> int:
        """LGPD delete-by-subject: every ledger row of `member_id` in this org. Returns the rows removed."""
        data = self._base().rpc(self._cfg.table(POINTS_ERASE_RPC), {"p_org": self._org, "p_member": member_id}).execute().data
        return int(data or 0)


def make_org_points_ledger(
    cfg: EngagementConfig,
    *,
    org_id: str | None = None,
    use_fake: bool = False,
    supabase_client: Any = None,
    schema: str | None = None,
) -> OrgPointsLedger | FakeOrgPointsLedger:
    """The Fake (`use_fake=True`) or the Real ledger for `org_id`. A missing client / org is a loud error, never a silent Fake."""
    if use_fake:
        return FakeOrgPointsLedger()
    if supabase_client is None or not org_id:
        raise RuntimeError("make_org_points_ledger: supabase_client and org_id are required when use_fake=False")
    return OrgPointsLedger(supabase_client, cfg, org_id, schema=schema)


__all__ = ["FakeOrgPointsLedger", "OrgPointsLedger", "make_org_points_ledger"]
