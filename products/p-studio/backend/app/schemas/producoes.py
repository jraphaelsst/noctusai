from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel

EtapaProducao = Literal[
    "agendado", "captado", "backup", "selecao",
    "edicao", "revisao", "entregue", "arquivado",
]

TipoEvento = Literal["transicao", "comentario", "arquivo"]

# Ordem canônica do pipeline de pós (spec § 4).
ETAPAS: tuple[str, ...] = (
    "agendado", "captado", "backup", "selecao",
    "edicao", "revisao", "entregue", "arquivado",
)

ETAPA_LABELS: dict[str, str] = {
    "agendado": "Agendado",
    "captado": "Captado",
    "backup": "Backup realizado",
    "selecao": "Seleção",
    "edicao": "Edição",
    "revisao": "Revisão",
    "entregue": "Entregue",
    "arquivado": "Arquivado",
}


class ProducaoCreate(BaseModel):
    negocio_id: Optional[str] = None
    captacao_id: Optional[str] = None
    cliente_id: Optional[str] = None
    etapa: EtapaProducao = "agendado"
    responsavel: Optional[str] = None
    prazo_entrega: Optional[date] = None
    observacoes: Optional[str] = None


class ProducaoUpdate(BaseModel):
    responsavel: Optional[str] = None
    prazo_entrega: Optional[date] = None
    observacoes: Optional[str] = None


class ProducaoEtapaUpdate(BaseModel):
    """Avanço de etapa. `comentario` vira um evento no histórico."""

    etapa: EtapaProducao
    responsavel: Optional[str] = None
    comentario: Optional[str] = None


class ProducaoEventoCreate(BaseModel):
    comentario: str
    responsavel: Optional[str] = None


class ProducaoEventoOut(BaseModel):
    id: str
    producao_id: str
    etapa: str
    tipo: str
    responsavel: Optional[str] = None
    comentario: Optional[str] = None
    arquivo_url: Optional[str] = None
    created_at: datetime


class ProducaoOut(BaseModel):
    id: str
    org_id: str
    negocio_id: Optional[str] = None
    captacao_id: Optional[str] = None
    cliente_id: Optional[str] = None
    etapa: str
    responsavel: Optional[str] = None
    prazo_entrega: Optional[date] = None
    entregue_em: Optional[date] = None
    observacoes: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    cliente_nome: Optional[str] = None
    endereco: Optional[str] = None
    eventos: list[ProducaoEventoOut] = []
