"""
Pydantic schemas for matching requests and responses.
"""
from pydantic import BaseModel, model_validator
from typing import Optional


class MatchRequest(BaseModel):
    """Request to generate matches."""
    imovel_id: Optional[str] = None
    perfil_permuta_id: Optional[str] = None

    @model_validator(mode="after")
    def validate_at_least_one(self):
        if not self.imovel_id and not self.perfil_permuta_id:
            raise ValueError("Either imovel_id or perfil_permuta_id is required")
        return self


class MatchDetails(BaseModel):
    """Sub-score breakdown for a match."""
    compatibilidade_regiao: int = 0
    compatibilidade_preco: int = 0
    compatibilidade_specs: int = 0
    qualidade_anuncio: int = 0
    gap_valor: float = 0


class MatchResult(BaseModel):
    """Result of a single match calculation."""
    imovel_id: str
    perfil_permuta_id: str
    score: int
    justificativa: str
    detalhes: MatchDetails


class MatchResponse(BaseModel):
    """Response from the matching endpoint."""
    data: list[MatchResult]
    total: int


class MatchStatusUpdate(BaseModel):
    """Request to update a match status."""
    status: str  # 'aceito' | 'rejeitado'
