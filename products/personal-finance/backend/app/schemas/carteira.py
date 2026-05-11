from typing import Optional
from pydantic import Field
from noctusai_lib.api import StrictHttpModel


class CarteiraCreate(StrictHttpModel):
    nome: str = Field(..., min_length=1, max_length=255)
    tipo: Optional[str] = Field(default="geral", pattern="^(geral|acoes|renda_fixa|fundos|crypto|previdencia|outro)$")
    corretora: Optional[str] = Field(default=None, max_length=255)


class CarteiraUpdate(StrictHttpModel):
    nome: Optional[str] = Field(default=None, min_length=1, max_length=255)
    tipo: Optional[str] = Field(default=None, pattern="^(geral|acoes|renda_fixa|fundos|crypto|previdencia|outro)$")
    corretora: Optional[str] = Field(default=None, max_length=255)
    ativo: Optional[bool] = None


class AlocacaoAlvoCreate(StrictHttpModel):
    classe_ativo: str = Field(..., min_length=1, max_length=100)
    percentual_alvo: float = Field(..., ge=0, le=100)
    limite_desvio: Optional[float] = Field(default=5.0, ge=0, le=50)
