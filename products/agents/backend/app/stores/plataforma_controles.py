"""Platform kill switch store — ``agents.plataforma_controles`` (migration 056, Julia v3 contract §12.1).

One row per agent KEY, platform-wide (no org): ``desligado`` stops that agent for EVERY org. The turn path reads it
FIRST on every turn (:mod:`app.channels.controles`) and fails closed — an unreadable switch is a 503
``controle_indisponivel``, never a reply. A key with no row reads as ``desligado=False``.

Writes go through ``agents.set_plataforma_controle`` (one transaction; the attributed audit row,
``plataforma_desligada`` / ``plataforma_religada``, lands inside it).

Seed IO shape: ``PlataformaControleStore`` Protocol + ``FakePlataformaControleStore`` +
``SupabasePlataformaControleStore`` (Real) + ``get_plataforma_controle_store(settings)`` factory.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from app.stores._db_errors import exec_rpc
from app.stores._util import db_ts, utcnow
from app.stores.errors import NotFound

__all__ = [
    "MOTIVO_MAX",
    "FakePlataformaControleStore",
    "PlataformaControle",
    "PlataformaControleStore",
    "SupabasePlataformaControleStore",
    "get_plataforma_controle_store",
]

_SCHEMA = "agents"
#: ``plataforma_controles.motivo`` CHECK (056).
MOTIVO_MAX = 500


@dataclass(frozen=True)
class PlataformaControle:
    agent_key: str
    desligado: bool = False
    motivo: str | None = None
    alterado_por: UUID | None = None
    alterado_em: datetime | None = None


class PlataformaControleStore(Protocol):
    def get(self, agent_key: str) -> PlataformaControle:
        """The agent's platform switch (``desligado=False`` when it never had a row)."""
        ...

    def set(
        self, agent_key: str, *, desligado: bool, motivo: str | None = None, actor: UUID | None = None
    ) -> PlataformaControle:
        """Flip the switch with an attributed audit row. Raises :class:`NotFound` (no platform definition with
        that key) and :class:`ValueError` (motivo longer than :data:`MOTIVO_MAX`)."""
        ...


def _validate(motivo: str | None) -> None:
    if motivo is not None and len(motivo) > MOTIVO_MAX:
        raise ValueError(f"motivo must be at most {MOTIVO_MAX} characters")


class FakePlataformaControleStore:
    """In-memory store. ``conhecidos`` are the keys that have a platform definition (``set`` of another key is
    :class:`NotFound`); ``None`` accepts any key."""

    def __init__(self, conhecidos: set[str] | None = None) -> None:
        self._rows: dict[str, PlataformaControle] = {}
        self.conhecidos = conhecidos
        #: ``(agent_key, acao, actor, motivo)`` per change — the audit the RPC writes.
        self.auditoria: list[tuple[str, str, UUID | None, str | None]] = []
        #: Set to an exception to simulate the switch being unreadable (fail-closed tests).
        self.falha: Exception | None = None

    def get(self, agent_key: str) -> PlataformaControle:
        if self.falha is not None:
            raise self.falha
        return self._rows.get(agent_key, PlataformaControle(agent_key))

    def set(
        self, agent_key: str, *, desligado: bool, motivo: str | None = None, actor: UUID | None = None
    ) -> PlataformaControle:
        _validate(motivo)
        if self.conhecidos is not None and agent_key not in self.conhecidos:
            raise NotFound(f"no platform definition for agent {agent_key}")
        rec = PlataformaControle(agent_key, desligado, motivo, actor, utcnow())
        self._rows[agent_key] = rec
        self.auditoria.append((agent_key, "plataforma_desligada" if desligado else "plataforma_religada", actor, motivo))
        return rec


class SupabasePlataformaControleStore:
    """Real store — Postgres via the admin client."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def get(self, agent_key: str) -> PlataformaControle:
        rows = (
            self._client.schema(_SCHEMA).table("plataforma_controles")
            .select("agent_key, desligado, motivo, alterado_por, alterado_em")
            .eq("agent_key", agent_key).limit(1).execute().data or []
        )
        if not rows:
            return PlataformaControle(agent_key)
        row = rows[0]
        return PlataformaControle(
            agent_key=row["agent_key"], desligado=bool(row["desligado"]), motivo=row.get("motivo"),
            alterado_por=UUID(str(row["alterado_por"])) if row.get("alterado_por") else None,
            alterado_em=db_ts(row.get("alterado_em")),
        )

    def set(
        self, agent_key: str, *, desligado: bool, motivo: str | None = None, actor: UUID | None = None
    ) -> PlataformaControle:
        _validate(motivo)
        exec_rpc(self._client, _SCHEMA, "set_plataforma_controle", {
            "p_agent_key": agent_key, "p_desligado": bool(desligado), "p_motivo": motivo,
            "p_actor": str(actor) if actor else None,
        })
        return self.get(agent_key)


def get_plataforma_controle_store(settings: Any) -> PlataformaControleStore:
    """Real when a Supabase service-role key is configured, Fake otherwise — same signal as
    :func:`app.stores.agent_controles.get_agent_controle_store`."""
    if not getattr(settings, "supabase_service_role_key", None):
        return FakePlataformaControleStore()
    from app.database import get_admin_client

    return SupabasePlataformaControleStore(get_admin_client())
