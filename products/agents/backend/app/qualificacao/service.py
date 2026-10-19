"""The qualification service — what the channel tools call (CONTRACT §3.4).

Typed results only: every refusal is a machine ``codigo``; its wording lives in
DB texts owned by the content layer (D2), never here. The service never calls a
model and never lets a model set stage or score: it validates and appends records,
then recomputes the state with :func:`engine.calcular` and refreshes the cache row.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Sequence
from uuid import UUID

from app.qualificacao import engine
from app.qualificacao.lead_store import EstadoCache, LeadQualificacaoStore
from app.qualificacao.matcher import MAX_TRECHO, conferir_trecho
from app.qualificacao.models import (
    DERIVADOS,
    EVENTOS_IMOVEL,
    ORIGENS_IMOVEL,
    EstadoQualificacao,
    EventoImovel,
    Registro,
    VersaoPadrao,
)
from app.qualificacao.store import PadraoStore
from app.stores._util import utcnow

__all__ = [
    "MAX_ITENS",
    "ItemPerfil",
    "ItemRecusado",
    "RegistrarPerfilResultado",
    "EventoImovelResultado",
    "ConclusaoResultado",
    "QualificacaoLead",
    "VersaoNaoUtilizavel",
    "QualificacaoService",
]

MAX_ITENS = 10
_REACOES = frozenset(e for e in EVENTOS_IMOVEL if e != "oferecido")


class VersaoNaoUtilizavel(Exception):
    """The pinned standard version is a draft (never a legal pin) — typed refusal ``versao_nao_publicada``."""

    codigo = "versao_nao_publicada"


@dataclass(frozen=True)
class ItemPerfil:
    criterio: str
    valor: Any
    trecho: str | None = None


@dataclass(frozen=True)
class ItemRecusado:
    criterio: str
    codigo: str


@dataclass(frozen=True)
class RegistrarPerfilResultado:
    ok: bool
    aceitos: tuple[str, ...] = ()
    inalterados: tuple[str, ...] = ()
    recusados: tuple[ItemRecusado, ...] = ()
    codigo: str | None = None  # batch-level refusal (itens_demais / sem_itens / versao_nao_publicada)
    estado: EstadoQualificacao | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "ok": self.ok, "codigo": self.codigo, "aceitos": list(self.aceitos),
            "inalterados": list(self.inalterados),
            "recusados": [{"criterio": r.criterio, "codigo": r.codigo} for r in self.recusados],
            "avaliacao": self.estado.avaliar_payload() if self.estado else None,
        }


@dataclass(frozen=True)
class EventoImovelResultado:
    ok: bool
    codigo: str | None = None
    inalterado: bool = False
    estado: EstadoQualificacao | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "ok": self.ok, "codigo": self.codigo, "inalterado": self.inalterado,
            "avaliacao": self.estado.avaliar_payload() if self.estado else None,
        }


@dataclass(frozen=True)
class ConclusaoResultado:
    ok: bool
    estagio: str
    codigo: str | None = None  # estagio_nao_conclusivo
    lead_pronto: dict[str, Any] | None = None


@dataclass(frozen=True)
class QualificacaoLead:
    """Full computed state + property events (``GET .../leads/{ref}/qualificacao``)."""

    versao_id: UUID
    estado: EstadoQualificacao
    eventos: tuple[EventoImovel, ...]
    calculado_em: datetime


class QualificacaoService:
    def __init__(
        self,
        padroes: PadraoStore,
        leads: LeadQualificacaoStore,
        *,
        agora: Callable[[], datetime] = utcnow,
    ) -> None:
        self._padroes = padroes
        self._leads = leads
        self._agora = agora

    # ── loading ────────────────────────────────────────────────────────────

    def _versao(self, versao_id: UUID) -> VersaoPadrao:
        v = self._padroes.obter_versao(versao_id)  # NotFound propagates
        if v.status == "rascunho":
            raise VersaoNaoUtilizavel()
        return v

    def _calcular(self, v: VersaoPadrao, registros, eventos) -> EstadoQualificacao:
        return engine.calcular(v, registros, eventos, self._agora())

    def _persistir(self, org_id: UUID, lead_ref_id: UUID, v: VersaoPadrao, e: EstadoQualificacao) -> None:
        self._leads.salvar_estado(EstadoCache(
            org_id=org_id, lead_ref_id=lead_ref_id, versao_id=v.id, valores=e.valores, score=e.score,
            estagio=e.estagio, faltando=e.faltando, hash=e.hash, calculado_em=e.calculado_em or self._agora(),
        ))

    # ── reads ──────────────────────────────────────────────────────────────

    def avaliar(self, org_id: UUID, lead_ref_id: UUID, versao_id: UUID) -> EstadoQualificacao:
        """The ``avaliar_lead`` state (``.avaliar_payload()`` is the §3.4 payload).
        Computed fresh from the records; writes nothing."""
        v = self._versao(versao_id)
        return self._calcular(
            v, self._leads.listar_registros(org_id, lead_ref_id), self._leads.listar_eventos(org_id, lead_ref_id),
        )

    def obter_qualificacao(self, org_id: UUID, lead_ref_id: UUID) -> QualificacaoLead | None:
        """Org-scoped read for ``GET /api/channels/leads/{ref}/qualificacao``; ``None`` = never qualified."""
        cache = self._leads.obter_estado(org_id, lead_ref_id)
        if cache is None:
            return None
        v = self._padroes.obter_versao(cache.versao_id)
        eventos = self._leads.listar_eventos(org_id, lead_ref_id)
        estado = self._calcular(v, self._leads.listar_registros(org_id, lead_ref_id), eventos)
        return QualificacaoLead(cache.versao_id, estado, tuple(eventos), estado.calculado_em or self._agora())

    def codigos_oferecidos(self, org_id: UUID, lead_ref_id: UUID) -> list[str]:
        """Every code already offered to this lead (``excluir_codigos`` of the next search)."""
        vistos: list[str] = []
        for e in self._leads.listar_eventos(org_id, lead_ref_id):
            if e.evento == "oferecido" and e.codigo_imovel not in vistos:
                vistos.append(e.codigo_imovel)
        return vistos

    def proximo_lote(self, org_id: UUID, lead_ref_id: UUID) -> int:
        lotes = [e.lote or 0 for e in self._leads.listar_eventos(org_id, lead_ref_id) if e.evento == "oferecido"]
        return max(lotes, default=0) + 1

    # ── registrar_perfil ───────────────────────────────────────────────────

    def registrar_perfil(
        self,
        org_id: UUID,
        lead_ref_id: UUID,
        *,
        agent_id: UUID,
        versao_id: UUID,
        itens: Sequence[ItemPerfil],
        mensagens_lead: Sequence[str],
        thread_id: UUID | None = None,
        message_id: UUID | None = None,
        fonte: str = "lead_informou",
    ) -> RegistrarPerfilResultado:
        """Validate then append the lead's answers. Per-item refusals do not block
        the accepted items (typed in ``recusados``). ``trecho`` must be found in the
        lead's own recent messages unless ``fonte`` is ``migracao`` / ``humano``."""
        if fonte not in ("lead_informou", "migracao", "humano"):
            return RegistrarPerfilResultado(False, codigo="fonte_invalida")
        if not itens:
            return RegistrarPerfilResultado(False, codigo="sem_itens")
        if len(itens) > MAX_ITENS:
            return RegistrarPerfilResultado(False, codigo="itens_demais")
        try:
            v = self._versao(versao_id)
        except VersaoNaoUtilizavel as exc:
            return RegistrarPerfilResultado(False, codigo=exc.codigo)

        registros = self._leads.listar_registros(org_id, lead_ref_id)
        eventos = self._leads.listar_eventos(org_id, lead_ref_id)
        atuais = self._calcular(v, registros, eventos).valores

        novos: list[Registro] = []
        aceitos: list[str] = []
        inalterados: list[str] = []
        recusados: list[ItemRecusado] = []
        vistos: set[str] = set()
        for item in itens:
            codigo = self._recusa_item(v, item, fonte, mensagens_lead, vistos)
            if codigo is not None:
                recusados.append(ItemRecusado(item.criterio, codigo))
                continue
            vistos.add(item.criterio)
            crit = v.criterio(item.criterio)
            _, norm, _ = engine.validar_valor(crit, item.valor)
            if atuais.get(item.criterio) == norm:
                inalterados.append(item.criterio)
                continue
            novos.append(Registro(
                criterio_chave=item.criterio, valor=norm, fonte=fonte,
                trecho=(item.trecho.strip() if item.trecho else None),
            ))
            aceitos.append(item.criterio)

        escritos: list[Registro] = []
        if novos:
            escritos = self._leads.adicionar_registros(
                org_id, lead_ref_id, agent_id=agent_id, versao_id=versao_id, thread_id=thread_id,
                message_id=message_id, registros=novos,
            )
        estado = self._calcular(v, [*registros, *escritos], eventos)
        if novos or self._leads.obter_estado(org_id, lead_ref_id) is None:
            self._persistir(org_id, lead_ref_id, v, estado)
        return RegistrarPerfilResultado(
            ok=not recusados, aceitos=tuple(aceitos), inalterados=tuple(inalterados),
            recusados=tuple(recusados), estado=estado,
        )

    @staticmethod
    def _recusa_item(
        v: VersaoPadrao, item: ItemPerfil, fonte: str, mensagens_lead: Sequence[str], vistos: set[str],
    ) -> str | None:
        if item.criterio in vistos:
            return "criterio_repetido"
        if item.criterio in DERIVADOS:
            return "criterio_derivado"
        crit = v.criterio(item.criterio)
        if crit is None or not crit.ativo:
            return "criterio_desconhecido"
        if crit.sensivel == "nao_coletar":
            return "nao_coletar"
        ok, _, codigo = engine.validar_valor(crit, item.valor)
        if not ok:
            return codigo
        if fonte == "lead_informou":
            ok, codigo = conferir_trecho(item.trecho, mensagens_lead)
            if not ok:
                return codigo
        elif item.trecho and len(item.trecho) > MAX_TRECHO:
            return "trecho_longo"  # migracao / humano: the quote is optional, never oversized
        return None

    # ── registrar_evento_imovel ────────────────────────────────────────────

    def registrar_evento_imovel(
        self,
        org_id: UUID,
        lead_ref_id: UUID,
        *,
        agent_id: UUID,
        versao_id: UUID,
        codigo_imovel: str,
        evento: str,
        origem: str = "campanha",
        lote: int | None = None,
        motivo: str | None = None,
        thread_id: UUID | None = None,
    ) -> EventoImovelResultado:
        if evento not in EVENTOS_IMOVEL:
            return EventoImovelResultado(False, "evento_invalido")
        if origem not in ORIGENS_IMOVEL:
            return EventoImovelResultado(False, "origem_invalida")
        codigo_imovel = (codigo_imovel or "").strip()
        if not codigo_imovel or len(codigo_imovel) > 64:
            return EventoImovelResultado(False, "codigo_invalido")
        if motivo is not None and len(motivo) > 200:
            return EventoImovelResultado(False, "motivo_longo")
        if lote is not None and lote < 1:
            return EventoImovelResultado(False, "lote_invalido")
        try:
            v = self._versao(versao_id)
        except VersaoNaoUtilizavel as exc:
            return EventoImovelResultado(False, exc.codigo)

        registros = self._leads.listar_registros(org_id, lead_ref_id)
        eventos = self._leads.listar_eventos(org_id, lead_ref_id)
        do_codigo = [e for e in eventos if e.codigo_imovel == codigo_imovel]
        oferecido = any(e.evento == "oferecido" for e in do_codigo)
        ultima = next((e.evento for e in reversed(do_codigo) if e.evento != "oferecido"), None)

        if evento == "oferecido":
            if oferecido:
                if origem == "pedido_lead":
                    return EventoImovelResultado(True, inalterado=True, estado=self._calcular(v, registros, eventos))
                return EventoImovelResultado(False, "imovel_ja_oferecido")
        else:
            if not oferecido:
                return EventoImovelResultado(False, "imovel_nao_oferecido")
            if ultima == evento:
                return EventoImovelResultado(True, inalterado=True, estado=self._calcular(v, registros, eventos))

        novo = self._leads.adicionar_evento(
            org_id, lead_ref_id, agent_id=agent_id, thread_id=thread_id,
            evento=EventoImovel(codigo_imovel=codigo_imovel, evento=evento, origem=origem, lote=lote, motivo=motivo),
        )
        estado = self._calcular(v, registros, [*eventos, novo])
        self._persistir(org_id, lead_ref_id, v, estado)
        return EventoImovelResultado(True, estado=estado)

    # ── concluir ───────────────────────────────────────────────────────────

    def pode_concluir(self, org_id: UUID, lead_ref_id: UUID, versao_id: UUID) -> ConclusaoResultado:
        """Code-gated ``concluir_qualificacao``: allowed only when the computed
        stage is ``conclusivo``. On success carries the ``lead_pronto`` action payload."""
        v = self._versao(versao_id)
        eventos = self._leads.listar_eventos(org_id, lead_ref_id)
        estado = self._calcular(v, self._leads.listar_registros(org_id, lead_ref_id), eventos)
        if not estado.pode_concluir:
            return ConclusaoResultado(False, estado.estagio, codigo="estagio_nao_conclusivo")
        ativos = engine_ultimas_reacoes(eventos)
        return ConclusaoResultado(
            True, estado.estagio,
            lead_pronto={
                "estagio": estado.estagio, "score": estado.score, "valores": dict(estado.valores),
                "imoveis_gostou": sorted(c for c, e in ativos.items() if e in ("gostou", "quer_visitar")),
                "intencoes_visita": sorted(c for c, e in ativos.items() if e == "quer_visitar"),
            },
        )

    # ── LGPD ───────────────────────────────────────────────────────────────

    def apagar_por_lead(self, org_id: UUID, lead_ref_id: UUID) -> int:
        """Delete-by-lead, idempotent. A-THREAD's ``apagar_lead`` calls this."""
        return self._leads.apagar_por_lead(org_id, lead_ref_id)

    def purgar_inativos(self, cutoff: datetime) -> int:
        return self._leads.purgar_inativos(cutoff)


def engine_ultimas_reacoes(eventos: Sequence[EventoImovel]) -> dict[str, str]:
    """Latest non-``oferecido`` event per property code."""
    out: dict[str, str] = {}
    for e in eventos:
        if e.evento != "oferecido":
            out[e.codigo_imovel] = e.evento
    return out
