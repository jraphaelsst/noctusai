"""The per-version honeytoken (Julia v2 guardrails B7): a random marker that lives in the model's system prompt and in
this table, and NOWHERE a person can read.

``garantir`` is the only way in -- it generates the marker the first time a version needs it (publish calls it; a
turn on an older version creates it on first use) and returns the same value forever after. There is deliberately NO
``listar`` and no route that returns it: the marker is a tripwire, and a tripwire someone can read is a password.
Protocol + Fake + Supabase + factory, like every seed-shaped store in this package.
"""
from __future__ import annotations

import logging
import secrets
from typing import Any, Protocol
from uuid import UUID

__all__ = ["FakeMarcadorStore", "MarcadorStore", "SupabaseMarcadorStore", "get_marcador_store", "novo_marcador"]

logger = logging.getLogger(__name__)

_SCHEMA = "agents"
_TABLE = "agent_version_marcadores"


def novo_marcador() -> str:
    """16 random bytes as hex: not a word, never produced by chance (the migration CHECK is ``[a-f0-9]{16,64}``)."""
    return secrets.token_hex(16)


class MarcadorStore(Protocol):
    def garantir(self, org_id: UUID, version_id: UUID) -> str:
        """The version's marker, created on first call. Idempotent and race-safe: two callers get the same value."""
        ...


class FakeMarcadorStore:
    def __init__(self) -> None:
        self._m: dict[UUID, str] = {}

    def garantir(self, org_id: UUID, version_id: UUID) -> str:
        return self._m.setdefault(version_id, novo_marcador())


class SupabaseMarcadorStore:
    def __init__(self, client: Any) -> None:
        self._client = client

    def _t(self):
        return self._client.schema(_SCHEMA).table(_TABLE)

    def garantir(self, org_id: UUID, version_id: UUID) -> str:
        rows = self._t().select("marcador").eq("version_id", str(version_id)).eq("org_id", str(org_id)).execute().data
        if rows:
            return str(rows[0]["marcador"])
        # on_conflict + ignore_duplicates: a concurrent publish/turn that lost the race keeps the winner's value
        self._t().upsert(
            {"version_id": str(version_id), "org_id": str(org_id), "marcador": novo_marcador()},
            on_conflict="version_id", ignore_duplicates=True,
        ).execute()
        rows = self._t().select("marcador").eq("version_id", str(version_id)).eq("org_id", str(org_id)).execute().data
        if not rows:
            raise RuntimeError("marcador_nao_gravado")
        return str(rows[0]["marcador"])


_FAKE = FakeMarcadorStore()


def get_marcador_store(settings: Any) -> MarcadorStore:
    """Real when a Supabase service-role key is configured, a process-wide Fake otherwise (so the marker is stable
    across the turns of a test)."""
    if not getattr(settings, "supabase_service_role_key", None):
        return _FAKE
    from app.database import get_admin_client

    return SupabaseMarcadorStore(get_admin_client())
