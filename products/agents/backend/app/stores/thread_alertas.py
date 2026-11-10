"""``agents.thread_alertas`` (migration 057): what ``sinalizar_alerta`` records (CONTRACT §12.3).

Seed IO shape: Protocol + Fake + Supabase (Real) + factory. Org-scoped on every call.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID, uuid4

from app.stores._db_errors import exec_query
from app.stores._util import db_ts, utcnow

__all__ = [
    "TIPOS_ALERTA", "AlertaRecord", "FakeThreadAlertaStore", "SupabaseThreadAlertaStore", "ThreadAlertaStore",
    "get_thread_alerta_store",
]

_SCHEMA = "agents"
#: ``emergencia`` (migration 079): the alert row IS the recorded emergency marking (the participant also gets an inactivity window).
TIPOS_ALERTA = ("lead_insatisfeito", "erro_agente", "desvio", "outro", "emergencia")


@dataclass(frozen=True)
class AlertaRecord:
    id: UUID
    org_id: UUID
    thread_id: UUID
    agent_id: UUID | None
    tipo: str
    descricao: str
    trecho: str | None
    created_at: datetime


class ThreadAlertaStore(Protocol):
    def registrar(
        self, org_id: UUID, thread_id: UUID, agent_id: UUID | None, *, tipo: str, descricao: str,
        trecho: str | None = None,
    ) -> AlertaRecord: ...

    def listar(self, org_id: UUID, thread_id: UUID) -> list[AlertaRecord]: ...


class FakeThreadAlertaStore:
    def __init__(self) -> None:
        self._rows: list[AlertaRecord] = []

    def registrar(self, org_id, thread_id, agent_id, *, tipo, descricao, trecho=None):
        if tipo not in TIPOS_ALERTA:
            raise ValueError(f"tipo must be one of {TIPOS_ALERTA}")
        rec = AlertaRecord(uuid4(), org_id, thread_id, agent_id, tipo, descricao, trecho, utcnow())
        self._rows.append(rec)
        return rec

    def listar(self, org_id, thread_id):
        return [r for r in self._rows if r.org_id == org_id and r.thread_id == thread_id]


class SupabaseThreadAlertaStore:
    def __init__(self, client: Any) -> None:
        self._client = client

    def _t(self):
        return self._client.schema(_SCHEMA).table("thread_alertas")

    @staticmethod
    def _rec(r: dict[str, Any]) -> AlertaRecord:
        return AlertaRecord(
            UUID(str(r["id"])), UUID(str(r["org_id"])), UUID(str(r["thread_id"])),
            UUID(str(r["agent_id"])) if r.get("agent_id") else None, r["tipo"], r["descricao"], r.get("trecho"),
            db_ts(r["created_at"]))

    def registrar(self, org_id, thread_id, agent_id, *, tipo, descricao, trecho=None):
        resp = exec_query(self._t().insert({
            "org_id": str(org_id), "thread_id": str(thread_id), "agent_id": str(agent_id) if agent_id else None,
            "tipo": tipo, "descricao": descricao, "trecho": trecho}))
        return self._rec(resp.data[0])

    def listar(self, org_id, thread_id):
        resp = (self._t().select("*").eq("org_id", str(org_id)).eq("thread_id", str(thread_id))
                .order("created_at").limit(1000).execute())
        return [self._rec(r) for r in resp.data or []]


def get_thread_alerta_store(settings: Any) -> ThreadAlertaStore:
    if not getattr(settings, "supabase_service_role_key", None):
        return FakeThreadAlertaStore()
    from app.database import get_admin_client

    return SupabaseThreadAlertaStore(get_admin_client())
