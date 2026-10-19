"""Frozen value types of the qualification standard and the per-lead state."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

GRUPOS = ("prontidao", "bloqueios", "interesse", "perfil_imovel", "perfil_vida", "contato")
TIPOS = ("enum", "multi", "bool", "numero", "faixa", "texto", "imovel_ref", "derivado", "identificacao")
SENSIVEL = (None, "faixa", "nao_coletar")
FONTES = ("lead_informou", "migracao", "humano")
EVENTOS_IMOVEL = ("oferecido", "gostou", "nao_gostou", "quer_visitar", "descartado", "quer_ver_mais")
ORIGENS_IMOVEL = ("campanha", "similar", "pedido_lead")
STATUS_VERSAO = ("rascunho", "publicada", "arquivada")

#: Criteria computed from the property events, never recorded by the model.
#: A rule may reference them; a version may also define a criterion row with
#: the same key to attach points to them (its ``pontuacao`` then applies).
DERIVADOS = (
    "imoveis_gostou", "deseja_visitar", "imoveis_oferecidos", "quer_mais_opcoes", "imoveis_rejeitados",
    "respostas_count", "dias_sem_resposta",
)
#: Event names a rule may test: the property events plus two computed/ signalled ones.
EVENTOS_REGRA = EVENTOS_IMOVEL + ("lote_rejeitado", "pediu_humano")


@dataclass(frozen=True)
class Opcao:
    valor: str
    rotulo: str = ""
    descricao_modelo: str = ""
    sinonimos: tuple[str, ...] = ()


@dataclass(frozen=True)
class CriterioDef:
    chave: str
    grupo: str
    rotulo: str
    descricao_modelo: str
    tipo: str
    opcoes: tuple[Opcao, ...] = ()
    unidade: str | None = None
    sensivel: str | None = None
    pontuacao: Any = field(default_factory=dict)  # a dict, or a list of bands for numero/faixa
    ordem: int = 0
    ativo: bool = True
    eixo: str | None = None  # named score axis (fit / intencao / urgencia ...); None = total only
    escopo: str | None = None  # agent/block that asks it (sdr | financeiro | juridico ...); None = every scope
    validade_dias: int | None = None  # a record older than this stops counting (the criterion is missing again)
    id: UUID | None = None


@dataclass(frozen=True)
class EstagioDef:
    chave: str
    rotulo: str
    ordem: int
    regra: dict[str, Any]
    descricao: str = ""
    conclusivo: bool = False
    terminal: bool = False
    id: UUID | None = None


@dataclass(frozen=True)
class ParametrosDef:
    """``eixos``: per-axis config, all data::

        {"intencao": {"max": 100,
                      "multiplicadores": [{"quando": <rule>, "fator": 0.6}],
                      "decaimento": [{"apos_dias": 14, "fator": 0.75}, {"apos_dias": 30, "fator": 0.5}]}}

    ``multiplicadores`` apply when their rule is true (factors multiply); ``decaimento`` picks the
    factor of the largest ``apos_dias`` <= days since the lead's last reply.
    """

    minimo_para_ofertar: dict[str, Any]
    lote_ofertas: int = 3
    score_max: int = 100
    eixos: dict[str, Any] = field(default_factory=dict)
    #: Rule: ask for the identity fields only when it is true (e.g. visit intent recorded). None = any time.
    pedir_identificacao_quando: dict[str, Any] | None = None


@dataclass(frozen=True)
class LeadSinais:
    """System signals about the lead that are not criteria records (pure inputs of ``calcular``)."""

    ultima_resposta_em: datetime | None = None
    respostas_count: int | None = None
    eventos: dict[str, int] = field(default_factory=dict)  # e.g. {"pediu_humano": 1}
    #: Identity FIELDS already collected (names only, never values) -- from agents.lead_identificacao.
    identificacao: frozenset[str] = frozenset()


@dataclass(frozen=True)
class VersaoPadrao:
    """One version of a standard, content included. ``id`` is None only for an
    in-memory fixture (tests)."""

    padrao_chave: str
    versao: int
    criterios: tuple[CriterioDef, ...]
    estagios: tuple[EstagioDef, ...]
    parametros: ParametrosDef
    id: UUID | None = None
    status: str = "publicada"
    notas: str | None = None
    publicada_em: datetime | None = None

    def criterio(self, chave: str) -> CriterioDef | None:
        for c in self.criterios:
            if c.chave == chave:
                return c
        return None


@dataclass(frozen=True)
class Registro:
    criterio_chave: str
    valor: Any
    fonte: str = "lead_informou"
    trecho: str | None = None
    created_at: datetime | None = None
    id: UUID | None = None
    versao_id: UUID | None = None
    agent_id: UUID | None = None
    thread_id: UUID | None = None
    message_id: UUID | None = None


@dataclass(frozen=True)
class EventoImovel:
    codigo_imovel: str
    evento: str
    origem: str = "campanha"
    lote: int | None = None
    motivo: str | None = None
    created_at: datetime | None = None
    id: UUID | None = None
    agent_id: UUID | None = None
    thread_id: UUID | None = None


@dataclass(frozen=True)
class ProximoCriterio:
    chave: str
    rotulo: str
    descricao_modelo: str
    opcoes: tuple[dict[str, str], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "chave": self.chave, "rotulo": self.rotulo,
            "descricao_modelo": self.descricao_modelo, "opcoes": [dict(o) for o in self.opcoes],
        }


@dataclass(frozen=True)
class EstadoQualificacao:
    valores: dict[str, Any]
    score: int
    estagio: str
    faltando: tuple[str, ...]
    proximo_criterio: ProximoCriterio | None
    pode_ofertar: bool
    pode_concluir: bool
    hash: str
    calculado_em: datetime | None = None
    scores: dict[str, int] = field(default_factory=dict)  # per axis, each clamped to [0, axis max]
    regra_id: str | None = None  # the rule that fired for `estagio` (a node "id", else the stage key)
    descartado_sugerido: dict[str, Any] | None = None  # LGPD art. 20: only SUGGESTED until a human confirms
    detalhe: dict[str, Any] = field(default_factory=dict)  # per-axis breakdown, criterion -> points
    identificacao_faltando: tuple[str, ...] = ()  # identity fields still to collect (only once asking is due)
    pedir_identificacao: bool = True  # the data rule says asking for identity is due now

    def avaliar_payload(self) -> dict[str, Any]:
        """The ``avaliar_lead`` tool payload (CONTRACT §3.4) — small by design
        (no full criteria list, risk 2)."""
        return {
            "estagio": self.estagio,
            "score": self.score,
            **({"scores": dict(self.scores)} if self.scores else {}),
            "regra_id": self.regra_id,
            **({"descartado_sugerido": dict(self.descartado_sugerido)} if self.descartado_sugerido else {}),
            "faltando": list(self.faltando),
            "identificacao_faltando": list(self.identificacao_faltando) if self.pedir_identificacao else [],
            "proximo_criterio": self.proximo_criterio.to_dict() if self.proximo_criterio else None,
            "pode_ofertar": self.pode_ofertar,
            "pode_concluir": self.pode_concluir,
        }


@dataclass(frozen=True)
class Confirmacao:
    """A HUMAN's confirmation of a terminal stage (descartado). The engine only ever suggests it."""

    estagio: str
    ator_user_id: UUID
    motivo: str | None = None
    created_at: datetime | None = None
    id: UUID | None = None
