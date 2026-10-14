"""Request bodies for the condominios module (unknown keys are a 422)."""
from __future__ import annotations

from typing import Literal, Optional
from uuid import UUID

from noctusai_lib.api import StrictHttpModel
from pydantic import Field


class CondominioPatchBody(StrictHttpModel):
    cidade: Optional[str] = None
    bairro: Optional[str] = None
    tipo: Optional[Literal["horizontal", "vertical", "loteamento", "misto"]] = None
    seguranca_nivel: Optional[int] = Field(default=None, ge=1, le=5)
    portaria_24h: Optional[bool] = None
    area_lazer: Optional[str] = None
    distancia_raposo_km: Optional[float] = Field(default=None, ge=0)
    acesso_principal: Optional[str] = None
    observacoes: Optional[str] = None
    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)


class RenomearBody(StrictHttpModel):
    nome: str = Field(min_length=1, max_length=200)


class FundirBody(StrictHttpModel):
    destino_id: UUID


class AliasBody(StrictHttpModel):
    alias: str = Field(min_length=1, max_length=200)
