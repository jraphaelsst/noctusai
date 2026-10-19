"""Frozen value types of the qualification standard and the per-lead state."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

GRUPOS = ("prontidao", "bloqueios", "interesse", "perfil_imovel", "perfil_vida", "contato")
TIPOS = ("enum", "multi", "bool", "numero", "faixa", "texto", "imovel_ref")
SENSIVEL = (None, "faixa", "nao_coletar")
FONTES = ("lead_informou", "migracao", "humano")
EVENTOS_IMOVEL = ("oferecido", "gostou", "nao_gostou", "quer_visitar", "descartado", "quer_ver_mais")
ORIGENS_IMOVEL = ("campanha", "similar", "pedido_lead")
STATUS_VERSAO = ("rascunho", "publicada", "arquivada")

#: Criteria computed from the property events, never recorded by the model.
#: A rule may reference them; a version may also define a criterion row with
#: the same key to attach points to them (its ``pontuacao`` then applies).
DERIVADOS = ("imoveis_gostou", "deseja_visitar", "imoveis_oferecidos", "quer_mais_opcoes")


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
    minimo_para_ofertar: dict[str, Any]
    lote_ofertas: int = 3
    score_max: int = 100


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

    def avaliar_payload(self) -> dict[str, Any]:
        """The ``avaliar_lead`` tool payload (CONTRACT §3.4) — small by design
        (no full criteria list, risk 2)."""
        return {
            "estagio": self.estagio,
            "score": self.score,
            "faltando": list(self.faltando),
            "proximo_criterio": self.proximo_criterio.to_dict() if self.proximo_criterio else None,
            "pode_ofertar": self.pode_ofertar,
            "pode_concluir": self.pode_concluir,
        }
