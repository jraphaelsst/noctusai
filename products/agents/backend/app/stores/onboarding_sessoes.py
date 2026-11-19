"""``agents.onboarding_sessoes`` + ``agents.onboarding_eventos`` (migration 089): the onboarding interview's binding to
its target org and its append-only event ledger (EOA).

Seed IO shape: Protocol + Fake + Supabase (Real) + factory. A session is looked up by the conversation it belongs to
(the interviewer's tools never name an org); the events are only ever appended.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID, uuid4

from app.stores._db_errors import exec_query
from app.stores._util import db_ts, utcnow

__all__ = [
    "EVENTOS", "EventoOnboarding", "FakeOnboardingStore", "OnboardingStore", "SessaoOnboarding", "SupabaseOnboardingStore",
    "get_onboarding_store",
]

_SCHEMA = "agents"
EVENTOS = (
    "resposta_registrada", "resposta_recusada", "item_marcado_pendente", "importacao_proposta", "resumo_apresentado",
    "aplicacao_executada",
)


@dataclass(frozen=True)
class SessaoOnboarding:
    id: UUID
    org_id: UUID
    conversation_id: UUID
    alvo_org_id: UUID
    agent_key: str
    product: str
    grant_id: UUID
    created_by: UUID
    created_at: datetime = field(default_factory=utcnow)


@dataclass(frozen=True)
class EventoOnboarding:
    id: UUID
    sessao_id: UUID
    event_type: str
    item_n: int | None
    dados: dict[str, Any]
    actor_id: UUID | None
    actor_kind: str
    occurred_at: datetime = field(default_factory=utcnow)


class OnboardingStore(Protocol):
    def criar_sessao(
        self, org_id: UUID, conversation_id: UUID, *, alvo_org_id: UUID, agent_key: str, product: str, grant_id: UUID,
        created_by: UUID,
    ) -> SessaoOnboarding: ...

    def sessao_da_conversa(self, org_id: UUID, conversation_id: UUID) -> SessaoOnboarding | None: ...

    def ultima_sessao(self, alvo_org_id: UUID, agent_key: str, product: str) -> SessaoOnboarding | None: ...

    def registrar_evento(
        self, sessao_id: UUID, event_type: str, *, item_n: int | None = None, dados: dict[str, Any] | None = None,
        actor_id: UUID | None = None, actor_kind: str = "agent",
    ) -> EventoOnboarding: ...

    def eventos(self, sessao_id: UUID) -> list[EventoOnboarding]: ...


class FakeOnboardingStore:
    def __init__(self) -> None:
        self._sessoes: list[SessaoOnboarding] = []
        self._eventos: list[EventoOnboarding] = []

    def criar_sessao(self, org_id, conversation_id, *, alvo_org_id, agent_key, product, grant_id, created_by):
        s = SessaoOnboarding(uuid4(), org_id, conversation_id, alvo_org_id, agent_key, product, grant_id, created_by)
        self._sessoes.append(s)
        return s

    def sessao_da_conversa(self, org_id, conversation_id):
        return next((s for s in self._sessoes if s.org_id == org_id and s.conversation_id == conversation_id), None)

    def ultima_sessao(self, alvo_org_id, agent_key, product):
        found = [s for s in self._sessoes if (s.alvo_org_id, s.agent_key, s.product) == (alvo_org_id, agent_key, product)]
        return found[-1] if found else None

    def registrar_evento(self, sessao_id, event_type, *, item_n=None, dados=None, actor_id=None, actor_kind="agent"):
        if event_type not in EVENTOS:
            raise ValueError(f"event_type must be one of {EVENTOS}")
        e = EventoOnboarding(uuid4(), sessao_id, event_type, item_n, dict(dados or {}), actor_id, actor_kind)
        self._eventos.append(e)
        return e

    def eventos(self, sessao_id):
        return [e for e in self._eventos if e.sessao_id == sessao_id]


class SupabaseOnboardingStore:
    def __init__(self, client: Any) -> None:
        self._client = client

    def _t(self, name: str):
        return self._client.schema(_SCHEMA).table(name)

    @staticmethod
    def _sessao(r: dict[str, Any]) -> SessaoOnboarding:
        return SessaoOnboarding(
            UUID(str(r["id"])), UUID(str(r["org_id"])), UUID(str(r["conversation_id"])), UUID(str(r["alvo_org_id"])),
            r["agent_key"], r["product"], UUID(str(r["grant_id"])), UUID(str(r["created_by"])), db_ts(r["created_at"]))

    @staticmethod
    def _evento(r: dict[str, Any]) -> EventoOnboarding:
        return EventoOnboarding(
            UUID(str(r["id"])), UUID(str(r["sessao_id"])), r["event_type"], r.get("item_n"), dict(r.get("dados") or {}),
            UUID(str(r["actor_id"])) if r.get("actor_id") else None, r["actor_kind"], db_ts(r["occurred_at"]))

    def criar_sessao(self, org_id, conversation_id, *, alvo_org_id, agent_key, product, grant_id, created_by):
        resp = exec_query(self._t("onboarding_sessoes").insert({
            "org_id": str(org_id), "conversation_id": str(conversation_id), "alvo_org_id": str(alvo_org_id),
            "agent_key": agent_key, "product": product, "grant_id": str(grant_id), "created_by": str(created_by)}))
        return self._sessao(resp.data[0])

    def sessao_da_conversa(self, org_id, conversation_id):
        resp = (self._t("onboarding_sessoes").select("*").eq("org_id", str(org_id))
                .eq("conversation_id", str(conversation_id)).limit(1).execute())
        return self._sessao(resp.data[0]) if resp.data else None

    def ultima_sessao(self, alvo_org_id, agent_key, product):
        resp = (self._t("onboarding_sessoes").select("*").eq("alvo_org_id", str(alvo_org_id)).eq("agent_key", agent_key)
                .eq("product", product).order("created_at", desc=True).limit(1).execute())
        return self._sessao(resp.data[0]) if resp.data else None

    def registrar_evento(self, sessao_id, event_type, *, item_n=None, dados=None, actor_id=None, actor_kind="agent"):
        resp = exec_query(self._t("onboarding_eventos").insert({
            "sessao_id": str(sessao_id), "event_type": event_type, "item_n": item_n, "dados": dados or {},
            "actor_id": str(actor_id) if actor_id else None, "actor_kind": actor_kind}))
        return self._evento(resp.data[0])

    def eventos(self, sessao_id):
        resp = (self._t("onboarding_eventos").select("*").eq("sessao_id", str(sessao_id)).order("seq").limit(5000)
                .execute())
        return [self._evento(r) for r in resp.data or []]


def get_onboarding_store(settings: Any) -> OnboardingStore:
    if not getattr(settings, "supabase_service_role_key", None):
        return FakeOnboardingStore()
    from app.database import get_admin_client

    return SupabaseOnboardingStore(get_admin_client())
