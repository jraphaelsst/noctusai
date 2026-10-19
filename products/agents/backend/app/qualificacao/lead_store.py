"""Per-lead qualification store — records, property events, cached state
(migration 032, CONTRACT §3.3).

Seed IO shape: ``LeadQualificacaoStore`` Protocol + Fake + Real + factory. Every
method is org-scoped. ``registros`` are append-only (no update/delete API); the
only deleters are :meth:`apagar_por_lead` (LGPD, on request — the method A-THREAD's
``apagar_lead`` calls) and :meth:`purgar_inativos` (the 180-day retention).
``lead_ref_id`` is a FOREIGN KEY to ``agents.lead_refs`` ON DELETE CASCADE (migration 037): deleting a lead
erases its qualification with it, and the retention purge does the same.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, Sequence
from uuid import UUID, uuid4

from app.qualificacao.models import Confirmacao, EventoImovel, Registro
from app.stores._db_errors import exec_query, exec_rpc
from app.stores._util import utcnow
from noctusai_lib.integrations.persistence.paging import iter_paged_rows

__all__ = [
    "EstadoCache",
    "LeadQualificacaoStore",
    "FakeLeadQualificacaoStore",
    "SupabaseLeadQualificacaoStore",
    "get_lead_qualificacao_store",
]

_SCHEMA = "agents"


@dataclass(frozen=True)
class EstadoCache:
    """Row of ``lead_qualificacao_estado`` — a cache, recomputed by code."""

    org_id: UUID
    lead_ref_id: UUID
    versao_id: UUID
    valores: dict[str, Any]
    score: int
    estagio: str
    faltando: tuple[str, ...]
    hash: str
    calculado_em: datetime
    scores: dict[str, int] = field(default_factory=dict)
    regra_id: str | None = None
    detalhe: dict[str, Any] = field(default_factory=dict)
    descartado_sugerido: dict[str, Any] | None = None


class LeadQualificacaoStore(Protocol):
    def listar_registros(self, org_id: UUID, lead_ref_id: UUID) -> list[Registro]:
        """Oldest first (the engine lets the later record win)."""
        ...
    def adicionar_registros(
        self, org_id: UUID, lead_ref_id: UUID, *, agent_id: UUID, versao_id: UUID,
        thread_id: UUID | None, message_id: UUID | None, registros: Sequence[Registro],
    ) -> list[Registro]: ...
    def listar_eventos(self, org_id: UUID, lead_ref_id: UUID) -> list[EventoImovel]: ...
    def adicionar_evento(
        self, org_id: UUID, lead_ref_id: UUID, *, agent_id: UUID, thread_id: UUID | None,
        evento: EventoImovel,
    ) -> EventoImovel: ...
    def obter_estado(self, org_id: UUID, lead_ref_id: UUID) -> EstadoCache | None: ...
    def salvar_estado(self, estado: EstadoCache) -> None: ...
    def listar_confirmacoes(self, org_id: UUID, lead_ref_id: UUID) -> list[Confirmacao]: ...
    def adicionar_confirmacao(self, org_id: UUID, lead_ref_id: UUID, c: Confirmacao) -> Confirmacao:
        """A human's confirmation of a terminal stage (append-only)."""
        ...
    def apagar_por_lead(self, org_id: UUID, lead_ref_id: UUID) -> int:
        """Erase every qualification row of one lead. Idempotent; returns rows removed."""
        ...
    def purgar_inativos(self, cutoff: datetime) -> int:
        """Erase every lead whose last activity is older than ``cutoff``."""
        ...


class FakeLeadQualificacaoStore:
    def __init__(self) -> None:
        self._reg: list[tuple[UUID, UUID, Registro]] = []
        self._ev: list[tuple[UUID, UUID, EventoImovel]] = []
        self._estado: dict[tuple[UUID, UUID], EstadoCache] = {}
        self._conf: list[tuple[UUID, UUID, Confirmacao]] = []

    def listar_registros(self, org_id, lead_ref_id):
        return [r for o, l, r in self._reg if o == org_id and l == lead_ref_id]

    def adicionar_registros(self, org_id, lead_ref_id, *, agent_id, versao_id, thread_id, message_id, registros):
        out = []
        for r in registros:
            row = Registro(
                criterio_chave=r.criterio_chave, valor=r.valor, fonte=r.fonte, trecho=r.trecho,
                created_at=utcnow(), id=uuid4(), versao_id=versao_id, agent_id=agent_id,
                thread_id=thread_id, message_id=message_id,
            )
            self._reg.append((org_id, lead_ref_id, row))
            out.append(row)
        return out

    def listar_eventos(self, org_id, lead_ref_id):
        return [e for o, l, e in self._ev if o == org_id and l == lead_ref_id]

    def adicionar_evento(self, org_id, lead_ref_id, *, agent_id, thread_id, evento):
        from dataclasses import replace

        row = replace(evento, created_at=utcnow(), id=uuid4(), agent_id=agent_id, thread_id=thread_id)
        self._ev.append((org_id, lead_ref_id, row))
        return row

    def obter_estado(self, org_id, lead_ref_id):
        e = self._estado.get((org_id, lead_ref_id))
        return e

    def salvar_estado(self, estado):
        self._estado[(estado.org_id, estado.lead_ref_id)] = estado

    def listar_confirmacoes(self, org_id, lead_ref_id):
        return [c for o, l, c in self._conf if o == org_id and l == lead_ref_id]

    def adicionar_confirmacao(self, org_id, lead_ref_id, c):
        from dataclasses import replace

        row = replace(c, created_at=utcnow(), id=uuid4())
        self._conf.append((org_id, lead_ref_id, row))
        return row

    def apagar_por_lead(self, org_id, lead_ref_id):
        n0 = len(self._reg) + len(self._ev) + len(self._estado) + len(self._conf)
        self._reg = [t for t in self._reg if not (t[0] == org_id and t[1] == lead_ref_id)]
        self._ev = [t for t in self._ev if not (t[0] == org_id and t[1] == lead_ref_id)]
        self._conf = [t for t in self._conf if not (t[0] == org_id and t[1] == lead_ref_id)]
        self._estado.pop((org_id, lead_ref_id), None)
        return n0 - (len(self._reg) + len(self._ev) + len(self._estado) + len(self._conf))

    def purgar_inativos(self, cutoff):
        ultima: dict[tuple[UUID, UUID], datetime] = {}
        for o, l, r in self._reg:
            ultima[(o, l)] = max(ultima.get((o, l), r.created_at), r.created_at)
        for o, l, e in self._ev:
            ultima[(o, l)] = max(ultima.get((o, l), e.created_at), e.created_at)
        for o, l, c in self._conf:
            ultima[(o, l)] = max(ultima.get((o, l), c.created_at), c.created_at)
        for k, s in self._estado.items():
            ultima[k] = max(ultima.get(k, s.calculado_em), s.calculado_em)
        removidos = 0
        for (o, l), ts in list(ultima.items()):
            if ts < cutoff:
                removidos += self.apagar_por_lead(o, l)
        return removidos


class SupabaseLeadQualificacaoStore:
    """Real store — Postgres through the admin client."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def _t(self, name: str):
        return self._client.schema(_SCHEMA).table(name)

    @staticmethod
    def _registro(r: dict[str, Any]) -> Registro:
        return Registro(
            id=UUID(str(r["id"])), criterio_chave=r["criterio_chave"], valor=r["valor"], fonte=r["fonte"],
            trecho=r.get("trecho"), created_at=r.get("created_at"),
            versao_id=UUID(str(r["versao_id"])) if r.get("versao_id") else None,
            agent_id=UUID(str(r["agent_id"])) if r.get("agent_id") else None,
            thread_id=UUID(str(r["thread_id"])) if r.get("thread_id") else None,
            message_id=UUID(str(r["message_id"])) if r.get("message_id") else None,
        )

    @staticmethod
    def _evento(r: dict[str, Any]) -> EventoImovel:
        return EventoImovel(
            id=UUID(str(r["id"])), codigo_imovel=r["codigo_imovel"], evento=r["evento"], origem=r["origem"],
            lote=r.get("lote"), motivo=r.get("motivo"), created_at=r.get("created_at"),
            agent_id=UUID(str(r["agent_id"])) if r.get("agent_id") else None,
            thread_id=UUID(str(r["thread_id"])) if r.get("thread_id") else None,
        )

    def listar_registros(self, org_id, lead_ref_id):
        def page(lo: int, hi: int):
            return (
                self._t("lead_qualificacao_registros").select("*")
                .eq("org_id", str(org_id)).eq("lead_ref_id", str(lead_ref_id))
                .order("created_at").order("id").range(lo, hi).execute().data
            )

        return [self._registro(r) for r in iter_paged_rows(page)]

    def adicionar_registros(self, org_id, lead_ref_id, *, agent_id, versao_id, thread_id, message_id, registros):
        if not registros:
            return []
        rows = [
            {
                "org_id": str(org_id), "lead_ref_id": str(lead_ref_id), "agent_id": str(agent_id),
                "versao_id": str(versao_id), "thread_id": str(thread_id) if thread_id else None,
                "message_id": str(message_id) if message_id else None, "criterio_chave": r.criterio_chave,
                "valor": r.valor, "trecho": r.trecho, "fonte": r.fonte,
            }
            for r in registros
        ]
        resp = exec_query(self._t("lead_qualificacao_registros").insert(rows))
        return [self._registro(r) for r in resp.data or []]

    def listar_eventos(self, org_id, lead_ref_id):
        def page(lo: int, hi: int):
            return (
                self._t("lead_imovel_eventos").select("*")
                .eq("org_id", str(org_id)).eq("lead_ref_id", str(lead_ref_id))
                .order("created_at").order("id").range(lo, hi).execute().data
            )

        return [self._evento(r) for r in iter_paged_rows(page)]

    def adicionar_evento(self, org_id, lead_ref_id, *, agent_id, thread_id, evento):
        row = {
            "org_id": str(org_id), "lead_ref_id": str(lead_ref_id), "agent_id": str(agent_id),
            "thread_id": str(thread_id) if thread_id else None, "codigo_imovel": evento.codigo_imovel,
            "evento": evento.evento, "lote": evento.lote, "motivo": evento.motivo, "origem": evento.origem,
        }
        resp = exec_query(self._t("lead_imovel_eventos").insert(row))
        return self._evento(resp.data[0])

    def obter_estado(self, org_id, lead_ref_id):
        resp = (
            self._t("lead_qualificacao_estado").select("*")
            .eq("org_id", str(org_id)).eq("lead_ref_id", str(lead_ref_id)).limit(1).execute()
        )
        if not resp.data:
            return None
        r = resp.data[0]
        return EstadoCache(
            org_id=UUID(str(r["org_id"])), lead_ref_id=UUID(str(r["lead_ref_id"])),
            versao_id=UUID(str(r["versao_id"])), valores=r.get("valores") or {}, score=r["score"],
            estagio=r["estagio"], faltando=tuple(r.get("faltando") or ()), hash=r["hash"],
            scores=r.get("scores") or {}, regra_id=r.get("regra_id"), detalhe=r.get("detalhe") or {},
            descartado_sugerido=r.get("descartado_sugerido"),
            calculado_em=r["calculado_em"],
        )

    def salvar_estado(self, e):
        row = {
            "lead_ref_id": str(e.lead_ref_id), "org_id": str(e.org_id), "versao_id": str(e.versao_id),
            "valores": e.valores, "score": e.score, "estagio": e.estagio, "faltando": list(e.faltando),
            "hash": e.hash, "scores": e.scores, "regra_id": e.regra_id, "detalhe": e.detalhe,
            "descartado_sugerido": e.descartado_sugerido, "calculado_em": e.calculado_em.isoformat(),
        }
        exec_query(self._t("lead_qualificacao_estado").upsert(row, on_conflict="lead_ref_id"))

    def listar_confirmacoes(self, org_id, lead_ref_id):
        resp = (
            self._t("lead_qualificacao_confirmacoes").select("*").eq("org_id", str(org_id))
            .eq("lead_ref_id", str(lead_ref_id)).order("created_at").limit(1000).execute()
        )
        return [self._confirmacao(r) for r in resp.data or []]

    def adicionar_confirmacao(self, org_id, lead_ref_id, c):
        row = {"org_id": str(org_id), "lead_ref_id": str(lead_ref_id), "estagio": c.estagio,
               "ator_user_id": str(c.ator_user_id), "motivo": c.motivo}
        return self._confirmacao(exec_query(self._t("lead_qualificacao_confirmacoes").insert(row)).data[0])

    @staticmethod
    def _confirmacao(r):
        return Confirmacao(estagio=r["estagio"], ator_user_id=UUID(str(r["ator_user_id"])), motivo=r.get("motivo"),
                           created_at=r.get("created_at"), id=UUID(str(r["id"])))

    def apagar_por_lead(self, org_id, lead_ref_id):
        resp = exec_rpc(
            self._client, _SCHEMA, "apagar_qualificacao_lead",
            {"p_org_id": str(org_id), "p_lead_ref_id": str(lead_ref_id)},
        )
        return int(resp.data or 0)

    def purgar_inativos(self, cutoff):
        resp = exec_rpc(self._client, _SCHEMA, "purgar_qualificacao_inativos", {"p_cutoff": cutoff.isoformat()})
        return int(resp.data or 0)


def get_lead_qualificacao_store(settings: Any) -> LeadQualificacaoStore:
    if not getattr(settings, "supabase_service_role_key", None):
        return FakeLeadQualificacaoStore()
    from app.database import get_admin_client

    return SupabaseLeadQualificacaoStore(get_admin_client())
