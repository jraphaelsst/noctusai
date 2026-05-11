from typing import Optional
from pydantic import Field
from noctusai_lib.api import StrictHttpModel


class MetaCreate(StrictHttpModel):
    nome: str = Field(..., min_length=1, max_length=255)
    tipo: str = Field(..., pattern="^(poupanca|quitar_divida|investimento|fundo_emergencia|personalizado)$")
    valor_alvo: float = Field(..., gt=0)
    valor_atual: Optional[float] = Field(default=0, ge=0)
    data_alvo: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    conta_vinculada_id: Optional[str] = None
    prioridade: Optional[str] = Field(default="media", pattern="^(alta|media|baixa)$")
    icone: Optional[str] = Field(default=None, max_length=10)
    cor: Optional[str] = Field(default=None, max_length=7)


class MetaUpdate(StrictHttpModel):
    nome: Optional[str] = Field(default=None, min_length=1, max_length=255)
    tipo: Optional[str] = Field(default=None, pattern="^(poupanca|quitar_divida|investimento|fundo_emergencia|personalizado)$")
    valor_alvo: Optional[float] = Field(default=None, gt=0)
    valor_atual: Optional[float] = Field(default=None, ge=0)
    data_alvo: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    conta_vinculada_id: Optional[str] = None
    prioridade: Optional[str] = Field(default=None, pattern="^(alta|media|baixa)$")
    status: Optional[str] = Field(default=None, pattern="^(ativa|concluida|pausada|cancelada)$")
    icone: Optional[str] = Field(default=None, max_length=10)
    cor: Optional[str] = Field(default=None, max_length=7)


class ContribuicaoCreate(StrictHttpModel):
    valor: float = Field(..., gt=0)
    data: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    fonte: Optional[str] = Field(default="manual", pattern="^(manual|automatica|transacao)$")
    transacao_id: Optional[str] = None
    notas: Optional[str] = Field(default=None, max_length=500)
