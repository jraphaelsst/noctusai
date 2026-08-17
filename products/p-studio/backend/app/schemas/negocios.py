from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel

EtapaNegocio = Literal[
    "novo_lead", "orcamento", "negociacao", "aprovado", "agendamento",
    "producao", "entregue", "recebido", "arquivado",
]

FormaPagamento = Literal["pix", "boleto", "cartao", "transferencia"]

# Ordem canônica do funil comercial (spec § 2). Usada para validar avanços
# de etapa e para ordenar as colunas do kanban.
ETAPAS: tuple[str, ...] = (
    "novo_lead", "orcamento", "negociacao", "aprovado", "agendamento",
    "producao", "entregue", "recebido", "arquivado",
)

ETAPA_LABELS: dict[str, str] = {
    "novo_lead": "Novo Lead",
    "orcamento": "Orçamento Enviado",
    "negociacao": "Negociação",
    "aprovado": "Aprovado",
    "agendamento": "Agendamento",
    "producao": "Produção",
    "entregue": "Entregue",
    "recebido": "Recebido",
    "arquivado": "Arquivado",
}


class NegocioCreate(BaseModel):
    cliente_id: str
    imovel_id: Optional[str] = None
    titulo: Optional[str] = None
    corretor: Optional[str] = None
    etapa: EtapaNegocio = "novo_lead"
    valor: Optional[float] = None  # None → somado dos serviços selecionados
    prazo_entrega: Optional[date] = None
    forma_pagamento: Optional[FormaPagamento] = None
    observacoes: Optional[str] = None
    servico_ids: list[str] = []


class NegocioUpdate(BaseModel):
    cliente_id: Optional[str] = None
    imovel_id: Optional[str] = None
    titulo: Optional[str] = None
    corretor: Optional[str] = None
    valor: Optional[float] = None
    prazo_entrega: Optional[date] = None
    forma_pagamento: Optional[FormaPagamento] = None
    observacoes: Optional[str] = None
    servico_ids: Optional[list[str]] = None


class NegocioEtapaUpdate(BaseModel):
    """Movimento no kanban. Separado do update geral porque a mudança de
    etapa tem efeitos colaterais (abre produção, gera lançamento)."""

    etapa: EtapaNegocio


class NegocioServicoOut(BaseModel):
    id: str
    servico_id: str
    nome: Optional[str] = None
    preco: float


class NegocioOut(BaseModel):
    id: str
    org_id: str
    cliente_id: str
    imovel_id: Optional[str] = None
    titulo: Optional[str] = None
    corretor: Optional[str] = None
    etapa: str
    valor: float
    prazo_entrega: Optional[date] = None
    forma_pagamento: Optional[str] = None
    observacoes: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    # Enriquecidos pelo service para a tela não precisar de N+1 requests
    cliente_nome: Optional[str] = None
    imovel_endereco: Optional[str] = None
    servicos: list[NegocioServicoOut] = []
