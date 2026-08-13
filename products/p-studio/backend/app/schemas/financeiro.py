from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel

# Status ARMAZENADOS. `atrasado` não está aqui de propósito: é derivado
# (faturado + vencimento no passado) e calculado na leitura, para que um
# lançamento nunca fique com status obsoleto por falta de um job noturno.
StatusLancamento = Literal["a_faturar", "faturado", "recebido", "cancelado"]

# Status EXIBIDOS — inclui o derivado.
StatusExibido = Literal["a_faturar", "faturado", "recebido", "atrasado", "cancelado"]

FormaPagamento = Literal["pix", "boleto", "cartao", "transferencia"]

STATUS_LABELS: dict[str, str] = {
    "a_faturar": "A faturar",
    "faturado": "Faturado",
    "recebido": "Recebido",
    "atrasado": "Atrasado",
    "cancelado": "Cancelado",
}


class LancamentoCreate(BaseModel):
    cliente_id: str
    negocio_id: Optional[str] = None
    descricao: Optional[str] = None
    valor: float = 0
    status: StatusLancamento = "a_faturar"
    data_entrega: Optional[date] = None
    vencimento: Optional[date] = None
    forma_pagamento: Optional[FormaPagamento] = None
    observacoes: Optional[str] = None


class LancamentoUpdate(BaseModel):
    cliente_id: Optional[str] = None
    negocio_id: Optional[str] = None
    descricao: Optional[str] = None
    valor: Optional[float] = None
    status: Optional[StatusLancamento] = None
    data_entrega: Optional[date] = None
    vencimento: Optional[date] = None
    pago_em: Optional[date] = None
    forma_pagamento: Optional[FormaPagamento] = None
    observacoes: Optional[str] = None


class CobrancaCreate(BaseModel):
    """Emissão de cobrança no provedor.

    `indefinido` deixa o pagador escolher a forma na fatura — é o default
    porque é o que mais converte, e o provedor informa depois como foi pago.
    """

    forma: Literal["pix", "boleto", "cartao", "indefinido"] = "indefinido"


class LancamentoBaixa(BaseModel):
    """Registrar recebimento. `pago_em` ausente = hoje."""

    pago_em: Optional[date] = None
    forma_pagamento: Optional[FormaPagamento] = None


class LancamentoOut(BaseModel):
    id: str
    org_id: str
    negocio_id: Optional[str] = None
    cliente_id: str
    descricao: Optional[str] = None
    valor: float
    status: str            # status armazenado
    status_exibido: str    # com `atrasado` derivado
    data_entrega: Optional[date] = None
    vencimento: Optional[date] = None
    pago_em: Optional[date] = None
    forma_pagamento: Optional[str] = None
    observacoes: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    cliente_nome: Optional[str] = None

    # Espelho da cobrança no provedor (migração 003). Nulos enquanto o
    # lançamento não foi cobrado — o que é o caso da maioria.
    provedor: Optional[str] = None
    provedor_cobranca_id: Optional[str] = None
    provedor_status: Optional[str] = None
    url_fatura: Optional[str] = None
    linha_digitavel: Optional[str] = None
    pix_copia_e_cola: Optional[str] = None
    sincronizado_em: Optional[datetime] = None


class ResumoFinanceiro(BaseModel):
    """Cabeçalho da tela financeira (spec § 7)."""

    faturamento_total: float = 0
    recebido: float = 0
    em_aberto: float = 0
    atrasado: float = 0
    receita_mes: float = 0
    receita_ano: float = 0
    ticket_medio: float = 0
    clientes_inadimplentes: int = 0
