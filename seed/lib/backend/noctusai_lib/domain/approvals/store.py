"""The approvals store: row reads (`OrgTableStore`) + the atomic `ApprovalLedger` (Protocol + Fake + Supabase).

The one write that must be atomic -- check the versao is current and undecided, append the event -- is the ledger. The
Supabase one calls the `apr_record` RPC (one transaction, a per-subject advisory lock); the Fake mirrors it over the Fake
table so the SAME suite runs against both.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol, runtime_checkable

from noctusai_lib.domain._organ_common import OrgTableStore, TableSpec, UniqueKey, make_org_table_store

from .config import ApprovalsConfig
from .errors import AlreadyDecided, NotSubmitted, StaleVersion
from .sql import ERR_ALREADY_DECIDED, ERR_NOT_SUBMITTED, ERR_STALE, UQ_DECIDED, UQ_SUBMITTED
from .types import DECISION_EVENTS, EVENT_SUBMITTED

T_EVENTS = "events"


def table_specs(cfg: ApprovalsConfig) -> dict[str, TableSpec]:
    """The logical table with the partial UNIQUE guards the DDL carries (so the Fake refuses what the database refuses)."""
    p = cfg.table_prefix
    key = ("subject_kind", "subject_id", "versao")
    return {
        T_EVENTS: TableSpec(
            cfg.table(T_EVENTS), timestamps=("created_at",),
            unique=(
                UniqueKey(UQ_SUBMITTED.format(p=p), key, where=lambda r: r.get("event") == EVENT_SUBMITTED),
                UniqueKey(UQ_DECIDED.format(p=p), key, where=lambda r: r.get("event") in DECISION_EVENTS),
            ),
            defaults={"actor_id": None, "motivo": None, "note": None},
        )
    }


@runtime_checkable
class ApprovalLedger(Protocol):
    """The atomic write. Returns `{"changed": bool, "event": str | None, "versao": int}` (RPC shape); raises
    `StaleVersion` / `NotSubmitted` / `AlreadyDecided`."""

    def record(self, org_id: str, row: Mapping[str, Any]) -> dict: ...


class FakeApprovalLedger:
    """In-memory ledger over the Fake table: same refusals, same event rows, same idempotence as `apr_record`."""

    def __init__(self, tables: OrgTableStore) -> None:
        self._t = tables

    def record(self, org_id: str, row: Mapping[str, Any]) -> dict:
        kind, subject, versao, event = row["subject_kind"], str(row["subject_id"]), int(row["versao"]), row["event"]
        rows = self._t.select(T_EVENTS, org_id, eq={"subject_kind": kind, "subject_id": subject})
        submitted = [r["versao"] for r in rows if r["event"] == EVENT_SUBMITTED]
        current = max(submitted) if submitted else None
        if event == EVENT_SUBMITTED:
            if current is not None and versao == current:
                return {"changed": False, "event": None, "versao": current}
            if current is not None and versao < current:
                raise StaleVersion(ERR_STALE)
        elif event in DECISION_EVENTS:
            if current is None:
                raise NotSubmitted(ERR_NOT_SUBMITTED)
            if versao != current:
                raise StaleVersion(ERR_STALE)
            if any(r["versao"] == versao and r["event"] in DECISION_EVENTS for r in rows):
                raise AlreadyDecided(ERR_ALREADY_DECIDED)
        else:
            raise ValueError(f"unknown approvals event {event!r}")
        saved = self._t.insert(T_EVENTS, org_id, [{
            "subject_kind": kind, "subject_id": subject, "versao": versao, "event": event,
            "actor_id": row.get("actor_id"), "motivo": row.get("motivo"), "note": row.get("note"),
        }])[0]
        return {"changed": True, "event": event, "versao": versao, "row": saved}


class SupabaseApprovalLedger:
    """The Real ledger: the `apr_record` RPC over a SERVICE-ROLE client (schema-pinned, like the other organs)."""

    def __init__(self, client: Any, cfg: ApprovalsConfig) -> None:
        self._client, self._cfg = client, cfg

    def record(self, org_id: str, row: Mapping[str, Any]) -> dict:
        try:
            data = self._client.rpc(self._cfg.table("record"), {"p_org": str(org_id), "p_row": dict(row)}).execute().data
        except Exception as exc:  # noqa: BLE001 - narrowed below: only the RPC's own refusals are translated, the rest re-raises
            text = str(exc)
            if ERR_STALE in text:
                raise StaleVersion(ERR_STALE) from exc
            if ERR_NOT_SUBMITTED in text:
                raise NotSubmitted(ERR_NOT_SUBMITTED) from exc
            if ERR_ALREADY_DECIDED in text:
                raise AlreadyDecided(ERR_ALREADY_DECIDED) from exc
            raise
        if isinstance(data, list):
            data = data[0] if data else {}
        return dict(data or {})


@dataclass(frozen=True)
class ApprovalStore:
    tables: OrgTableStore
    ledger: ApprovalLedger


def build_approvals_store(cfg: ApprovalsConfig, *, use_fake: bool = False, supabase_client: Any = None) -> ApprovalStore:
    """The Fake store (`use_fake=True`) or the Supabase one. A missing client is a loud error, never a silent Fake."""
    tables = make_org_table_store(table_specs(cfg), use_fake=use_fake, supabase_client=supabase_client)
    if use_fake:
        return ApprovalStore(tables, FakeApprovalLedger(tables))
    return ApprovalStore(tables, SupabaseApprovalLedger(supabase_client, cfg))


__all__ = [
    "ApprovalLedger", "ApprovalStore", "FakeApprovalLedger", "SupabaseApprovalLedger", "T_EVENTS", "build_approvals_store", "table_specs",
]
