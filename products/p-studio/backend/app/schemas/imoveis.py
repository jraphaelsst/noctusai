from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel

TipoImovel = Literal["casa", "apartamento", "cobertura", "terreno", "comercial", "galpao"]
PadraoImovel = Literal["alto", "medio", "economico"]


class ImovelCreate(BaseModel):
    cliente_id: Optional[str] = None
    codigo: Optional[str] = None  # gerado (PS-001, PS-002…) quando ausente
    endereco: str
    condominio: Optional[str] = None
    cidade: Optional[str] = None
    estado: Optional[str] = None
    tipo: TipoImovel = "apartamento"
    padrao: PadraoImovel = "medio"
    area: Optional[float] = None
    dormitorios: int = 0
    banheiros: int = 0
    vagas: int = 0
    valor: Optional[float] = None
    maps_url: Optional[str] = None
    observacoes: Optional[str] = None


class ImovelUpdate(BaseModel):
    cliente_id: Optional[str] = None
    codigo: Optional[str] = None
    endereco: Optional[str] = None
    condominio: Optional[str] = None
    cidade: Optional[str] = None
    estado: Optional[str] = None
    tipo: Optional[TipoImovel] = None
    padrao: Optional[PadraoImovel] = None
    area: Optional[float] = None
    dormitorios: Optional[int] = None
    banheiros: Optional[int] = None
    vagas: Optional[int] = None
    valor: Optional[float] = None
    maps_url: Optional[str] = None
    observacoes: Optional[str] = None


class ImovelOut(BaseModel):
    id: str
    org_id: str
    cliente_id: Optional[str] = None
    codigo: str
    endereco: str
    condominio: Optional[str] = None
    cidade: Optional[str] = None
    estado: Optional[str] = None
    tipo: str
    padrao: str
    area: Optional[float] = None
    dormitorios: int
    banheiros: int
    vagas: int
    valor: Optional[float] = None
    maps_url: Optional[str] = None
    observacoes: Optional[str] = None
    created_at: datetime
    updated_at: datetime
