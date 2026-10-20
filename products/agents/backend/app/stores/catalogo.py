"""The agent catalogue rows (migration 040): display-level data only.

``catalogo_agentes`` (role + public description) and ``catalogo_capacidades`` (capability labels) are DB rows
a platform admin edits -- never a tool description, a prompt line or a rule. The catalogue endpoint
(``GET /api/agents/catalogo``) joins them with the org's agents; an agent without a visible row is not listed.

Seed IO shape: Protocol + Fake + Supabase + factory (KB § PATTERNS/backend/seed-fake-real-adapter.md).
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Protocol
from uuid import UUID

__all__ = ["CatalogoEntrada", "CatalogoStore", "FakeCatalogoStore", "SupabaseCatalogoStore", "get_catalogo_store"]

_SCHEMA = "agents"


@dataclass(frozen=True)
class CatalogoEntrada:
    agent_key: str
    papel: str
    descricao_publica: str
    capacidades: tuple[str, ...] = field(default_factory=tuple)
    ordem: int = 0
    visivel: bool = True


class CatalogoStore(Protocol):
    def listar(self) -> list[CatalogoEntrada]:
        """Every VISIBLE entry, by ``ordem`` then key."""
        ...

    def salvar(self, entrada: CatalogoEntrada, *, updated_by: UUID | None = None) -> CatalogoEntrada:
        """Upsert one entry and replace its capability labels."""
        ...


class FakeCatalogoStore:
    def __init__(self, entradas: list[CatalogoEntrada] | None = None) -> None:
        self._rows: dict[str, CatalogoEntrada] = {e.agent_key: e for e in (entradas or [])}

    def listar(self) -> list[CatalogoEntrada]:
        return sorted((e for e in self._rows.values() if e.visivel), key=lambda e: (e.ordem, e.agent_key))

    def salvar(self, entrada: CatalogoEntrada, *, updated_by: UUID | None = None) -> CatalogoEntrada:
        self._rows[entrada.agent_key] = replace(entrada, capacidades=tuple(entrada.capacidades))
        return self._rows[entrada.agent_key]


class SupabaseCatalogoStore:
    def __init__(self, client: Any) -> None:
        self._client = client

    def _t(self, name: str):
        return self._client.schema(_SCHEMA).table(name)

    def listar(self) -> list[CatalogoEntrada]:
        agentes = self._t("catalogo_agentes").select("*").eq("visivel", True).limit(500).execute().data or []
        caps = self._t("catalogo_capacidades").select("*").limit(5000).execute().data or []
        por_agente: dict[str, list[tuple[int, str]]] = {}
        for c in caps:
            por_agente.setdefault(c["agent_key"], []).append((int(c["ordem"]), c["rotulo"]))
        out = [
            CatalogoEntrada(
                agent_key=a["agent_key"], papel=a["papel"], descricao_publica=a["descricao_publica"],
                capacidades=tuple(r for _, r in sorted(por_agente.get(a["agent_key"], []))),
                ordem=int(a.get("ordem") or 0), visivel=True,
            )
            for a in agentes
        ]
        return sorted(out, key=lambda e: (e.ordem, e.agent_key))

    def salvar(self, entrada: CatalogoEntrada, *, updated_by: UUID | None = None) -> CatalogoEntrada:
        self._t("catalogo_agentes").upsert({
            "agent_key": entrada.agent_key, "papel": entrada.papel, "descricao_publica": entrada.descricao_publica,
            "ordem": entrada.ordem, "visivel": entrada.visivel,
            "updated_by": str(updated_by) if updated_by else None,
        }, on_conflict="agent_key").execute()
        self._t("catalogo_capacidades").delete().eq("agent_key", entrada.agent_key).execute()
        if entrada.capacidades:
            self._t("catalogo_capacidades").insert([
                {"agent_key": entrada.agent_key, "ordem": i, "rotulo": r} for i, r in enumerate(entrada.capacidades)
            ]).execute()
        return entrada


def get_catalogo_store(settings: Any) -> CatalogoStore:
    if not getattr(settings, "supabase_service_role_key", None):
        return FakeCatalogoStore()
    from app.database import get_admin_client

    return SupabaseCatalogoStore(get_admin_client())
