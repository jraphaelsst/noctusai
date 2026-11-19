"""The append-only ``agents.sw_canal_eventos`` log of the channel to social-wiring (migration 090).

Intent-named events (EOA): ``sw_canal_provisionado`` / ``sw_canal_renovado`` / ``sw_canal_provisionamento_falhou`` /
``sw_canal_conexao_testada`` / ``sw_canal_chamada_concluida``. No field can hold a token value: the columns are the
outcome (``ok`` + ``codigo`` + a short pt-BR ``mensagem``), the actor and the token's id / expiry.

Seed IO shape: ``SwCanalEventStore`` Protocol + ``FakeSwCanalEventStore`` + ``SupabaseSwCanalEventStore`` + factory.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from app.stores._db_errors import exec_query
from app.stores._util import db_ts, utcnow

__all__ = [
    "EVENTOS", "EventoCanal", "FakeSwCanalEventStore", "SupabaseSwCanalEventStore", "SwCanalEventStore",
    "get_sw_canal_event_store",
]

_SCHEMA = "agents"
_TABLE = "sw_canal_eventos"
EVENTOS = (
    "sw_canal_provisionado", "sw_canal_renovado", "sw_canal_provisionamento_falhou",
    "sw_canal_conexao_testada", "sw_canal_chamada_concluida",
)
_MAX_MENSAGEM = 300


@dataclass(frozen=True)
class EventoCanal:
    evento: str
    ok: bool
    em: datetime
    codigo: str | None = None
    mensagem: str | None = None
    ator: UUID | None = None
    token_id: UUID | None = None
    expira_em: datetime | None = None


class SwCanalEventStore(Protocol):
    def registrar(
        self, evento: str, *, ok: bool, codigo: str | None = None, mensagem: str | None = None,
        ator: UUID | None = None, token_id: UUID | None = None, expira_em: datetime | None = None,
    ) -> None:
        """Append one event. Raises on a write failure: the caller decides (the channel never swallows it)."""
        ...

    def ultimo(self, *, ok: bool) -> EventoCanal | None:
        """The newest event that succeeded (``ok=True``) or failed (``ok=False``)."""
        ...


def _clip(mensagem: str | None) -> str | None:
    return mensagem[:_MAX_MENSAGEM] if mensagem else mensagem


class FakeSwCanalEventStore:
    def __init__(self) -> None:
        self.itens: list[EventoCanal] = []
        self.falhar = False

    def registrar(
        self, evento: str, *, ok: bool, codigo: str | None = None, mensagem: str | None = None,
        ator: UUID | None = None, token_id: UUID | None = None, expira_em: datetime | None = None,
    ) -> None:
        if self.falhar:
            raise RuntimeError("fake event store failure")
        if evento not in EVENTOS:
            raise ValueError(f"evento desconhecido: {evento}")
        self.itens.append(EventoCanal(evento, ok, utcnow(), codigo, _clip(mensagem), ator, token_id, expira_em))

    def ultimo(self, *, ok: bool) -> EventoCanal | None:
        return next((e for e in reversed(self.itens) if e.ok is ok), None)


class SupabaseSwCanalEventStore:
    def __init__(self, client: Any) -> None:
        self._client = client

    def _table(self):
        return self._client.schema(_SCHEMA).table(_TABLE)

    def registrar(
        self, evento: str, *, ok: bool, codigo: str | None = None, mensagem: str | None = None,
        ator: UUID | None = None, token_id: UUID | None = None, expira_em: datetime | None = None,
    ) -> None:
        exec_query(self._table().insert({
            "evento": evento, "ok": ok, "codigo": codigo, "mensagem": _clip(mensagem),
            "ator": str(ator) if ator else None, "token_id": str(token_id) if token_id else None,
            "expira_em": expira_em.isoformat() if expira_em else None,
        }))

    def ultimo(self, *, ok: bool) -> EventoCanal | None:
        res = exec_query(
            self._table().select("evento, ok, codigo, mensagem, ator, token_id, expira_em, created_at")
            .eq("ok", ok).order("created_at", desc=True).limit(1))
        rows = res.data or []
        if not rows:
            return None
        r = rows[0]
        return EventoCanal(
            r["evento"], bool(r["ok"]), db_ts(r["created_at"]), r.get("codigo"), r.get("mensagem"),
            UUID(str(r["ator"])) if r.get("ator") else None, UUID(str(r["token_id"])) if r.get("token_id") else None,
            db_ts(r.get("expira_em")))


def get_sw_canal_event_store(settings: Any) -> SwCanalEventStore:
    """Real when a service-role key is configured, Fake otherwise (same signal as every agents store)."""
    if not getattr(settings, "supabase_service_role_key", None):
        return FakeSwCanalEventStore()
    from app.database import get_admin_client

    return SupabaseSwCanalEventStore(get_admin_client())
