from typing import Optional
from pydantic import Field
from noctusai_lib.api import StrictHttpModel


class CategoriaCreate(StrictHttpModel):
    nome: str = Field(..., min_length=1, max_length=100)
    tipo: str = Field(..., pattern="^(receita|despesa|transferencia)$")
    categoria_pai_id: Optional[str] = None
    icone: Optional[str] = Field(default=None, max_length=10)
    cor: Optional[str] = Field(default=None, max_length=7)
    tipo_orcamento: Optional[str] = Field(default=None, pattern="^(necessidade|desejo|poupanca)$")
    ordem: Optional[int] = Field(default=0, ge=0)


class CategoriaUpdate(StrictHttpModel):
    nome: Optional[str] = Field(default=None, min_length=1, max_length=100)
    tipo: Optional[str] = Field(default=None, pattern="^(receita|despesa|transferencia)$")
    categoria_pai_id: Optional[str] = None
    icone: Optional[str] = Field(default=None, max_length=10)
    cor: Optional[str] = Field(default=None, max_length=7)
    tipo_orcamento: Optional[str] = Field(default=None, pattern="^(necessidade|desejo|poupanca)$")
    ordem: Optional[int] = Field(default=None, ge=0)
