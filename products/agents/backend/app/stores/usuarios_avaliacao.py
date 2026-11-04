"""Who may talk to an agent in evaluation mode — resolved from noc's user table, never stored as numbers (Julia v3
contract section 12.12). The allow-list holds ``noctus_users`` ids; the phone of each is read from
``public.noctus_users.telefone`` (E.164, set in noc's app) AT GATE TIME, per turn, never cached across turns — a phone
edited in noc applies on the next message.

NOC-REMEDIATE[user-phones-seed-helper]: read ``noctus_users`` directly until the seed ``resolve_user_phones`` lands
in ``noctusai_lib.integrations.persistence.table_reads``; then this module's Real store calls it. — 2026-11-03

Seed IO shape: ``UsuariosAvaliacao`` Protocol + ``FakeUsuariosAvaliacao`` + ``SupabaseUsuariosAvaliacao`` (Real) +
``get_usuarios_avaliacao(settings)`` factory.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from noctusai_lib.integrations.persistence.table_reads import batched

__all__ = [
    "FakeUsuariosAvaliacao",
    "SupabaseUsuariosAvaliacao",
    "UsuarioAvaliacao",
    "UsuariosAvaliacao",
    "get_usuarios_avaliacao",
]


@dataclass(frozen=True)
class UsuarioAvaliacao:
    id: UUID
    nome: str | None
    #: E.164 phone from noc, ``None`` when the user has none.
    telefone: str | None


class UsuariosAvaliacao(Protocol):
    def da_org(self, org_id: UUID, user_ids: list[UUID]) -> dict[UUID, UsuarioAvaliacao]:
        """The users among ``user_ids`` that BELONG to ``org_id`` (a foreign / unknown id is simply absent). Raises
        when the user table cannot be read — callers fail closed."""
        ...


class FakeUsuariosAvaliacao:
    def __init__(self) -> None:
        self._rows: dict[UUID, tuple[UUID, str | None, str | None]] = {}
        #: Set to an exception to simulate the user table being unreadable (fail-closed tests).
        self.falha: Exception | None = None
        self.leituras = 0

    def add(self, org_id: UUID, user_id: UUID, *, nome: str | None = None, telefone: str | None = None) -> UUID:
        self._rows[user_id] = (org_id, nome, telefone)
        return user_id

    def da_org(self, org_id: UUID, user_ids: list[UUID]) -> dict[UUID, UsuarioAvaliacao]:
        self.leituras += 1
        if self.falha is not None:
            raise self.falha
        return {
            u: UsuarioAvaliacao(u, self._rows[u][1], self._rows[u][2])
            for u in user_ids if u in self._rows and self._rows[u][0] == org_id
        }


class SupabaseUsuariosAvaliacao:
    """Real store — ``public.noctus_users`` through the core (public-schema) client."""

    def __init__(self, core_client_factory: Any) -> None:
        self._core = core_client_factory

    def da_org(self, org_id: UUID, user_ids: list[UUID]) -> dict[UUID, UsuarioAvaliacao]:
        out: dict[UUID, UsuarioAvaliacao] = {}
        for lote in batched([str(u) for u in user_ids]):
            rows = (
                self._core().table("noctus_users").select("id,org_id,nome,email,telefone")
                .in_("id", lote).eq("org_id", str(org_id)).execute().data or []
            )
            for r in rows:
                uid = UUID(str(r["id"]))
                out[uid] = UsuarioAvaliacao(uid, r.get("nome") or r.get("email"), (r.get("telefone") or None))
        return out


def get_usuarios_avaliacao(settings: Any) -> UsuariosAvaliacao:
    """Real when a Supabase service-role key is configured, Fake otherwise."""
    if not getattr(settings, "supabase_service_role_key", None):
        return FakeUsuariosAvaliacao()
    from app.database import get_core_client

    return SupabaseUsuariosAvaliacao(get_core_client)
