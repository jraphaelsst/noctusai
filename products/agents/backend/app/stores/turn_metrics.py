"""``agents.turn_metrics`` (migration 066): one row per agent turn -- cost, speed, size.

Seed IO shape: Protocol + Fake + Supabase (Real) + factory. Rows are plain dicts keyed by the table's columns
(``created_at`` is a tz-aware ``datetime``). Service-role only; the reader is the platform-admin studio API.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol
from uuid import UUID, uuid4

from app.stores._db_errors import exec_query
from app.stores._util import db_ts, utcnow

__all__ = ["FakeTurnMetricsStore", "SupabaseTurnMetricsStore", "TurnMetricsStore", "get_turn_metrics_store", "LIMITE_LINHAS"]

_SCHEMA = "agents"
#: Hard cap of rows one read pulls for aggregation (the aggregates are computed in the app over this window).
LIMITE_LINHAS = 20000


class TurnMetricsStore(Protocol):
    def registrar(self, row: dict[str, Any]) -> dict[str, Any]: ...

    def listar(
        self, agent_key: str, *, desde: datetime | None = None, ate: datetime | None = None, org_id: UUID | None = None,
        origem: str | None = None, thread_id: UUID | None = None, limite: int = LIMITE_LINHAS,
    ) -> list[dict[str, Any]]:
        """Rows of the agent ``agent_key`` (ALL its org instances; a turn row carries the instance's ``agent_id``) newest first, ``desde <= created_at < ate``."""
        ...


class FakeTurnMetricsStore:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def registrar(self, row):
        out = {"id": uuid4(), "created_at": utcnow(), **row}
        self.rows.append(out)
        return out

    def listar(self, agent_key, *, desde=None, ate=None, org_id=None, origem=None, thread_id=None, limite=LIMITE_LINHAS):
        sel = [
            r for r in self.rows
            if r["agent_key"] == agent_key
            and (desde is None or r["created_at"] >= desde) and (ate is None or r["created_at"] < ate)
            and (org_id is None or str(r["org_id"]) == str(org_id))
            and (origem is None or r["origem"] == origem)
            and (thread_id is None or str(r.get("thread_id")) == str(thread_id))
        ]
        return sorted(sel, key=lambda r: r["created_at"], reverse=True)[:limite]


def _jsonable(row: dict[str, Any]) -> dict[str, Any]:
    return {k: (str(v) if isinstance(v, UUID) else v.isoformat() if isinstance(v, datetime) else v) for k, v in row.items()}


class SupabaseTurnMetricsStore:
    def __init__(self, client: Any) -> None:
        self._client = client

    def _t(self):
        return self._client.schema(_SCHEMA).table("turn_metrics")

    @staticmethod
    def _row(r: dict[str, Any]) -> dict[str, Any]:
        out = dict(r)
        out["created_at"] = db_ts(r["created_at"])
        out["custo_usd"] = float(r.get("custo_usd") or 0)
        return out

    def registrar(self, row):
        resp = exec_query(self._t().insert(_jsonable(row)))
        return self._row(resp.data[0])

    def listar(self, agent_key, *, desde=None, ate=None, org_id=None, origem=None, thread_id=None, limite=LIMITE_LINHAS):
        q = self._t().select("*").eq("agent_key", agent_key)
        if desde is not None:
            q = q.gte("created_at", desde.isoformat())
        if ate is not None:
            q = q.lt("created_at", ate.isoformat())
        if org_id is not None:
            q = q.eq("org_id", str(org_id))
        if origem is not None:
            q = q.eq("origem", origem)
        if thread_id is not None:
            q = q.eq("thread_id", str(thread_id))
        resp = exec_query(q.order("created_at", desc=True).limit(min(limite, LIMITE_LINHAS)))
        return [self._row(r) for r in resp.data or []]


def get_turn_metrics_store(settings: Any) -> TurnMetricsStore:
    if not getattr(settings, "supabase_service_role_key", None):
        return FakeTurnMetricsStore()
    from app.database import get_admin_client

    return SupabaseTurnMetricsStore(get_admin_client())
