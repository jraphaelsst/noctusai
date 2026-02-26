"""
Pydantic schemas for matching requests and responses.
"""
from pydantic import BaseModel, Field, model_validator
from typing import Optional


class MatchRequest(BaseModel):
    """Request to generate matches."""
    ativo_origem_id: Optional[str] = None
    ativo_destino_id: Optional[str] = None
    score_minimo: float = Field(default=20.0, ge=0, le=100)

    @model_validator(mode="after")
    def validate_at_least_one(self):
        if not self.ativo_origem_id and not self.ativo_destino_id:
            raise ValueError("Informe ativo_origem_id ou ativo_destino_id")
        return self


class MatchDetails(BaseModel):
    """Sub-score breakdown for a match."""
    compatibilidade_regiao: int = 0
    compatibilidade_preco: int = 0
    compatibilidade_specs: int = 0
    alinhamento_interesses: int = 0
    qualidade_anuncio: int = 0
    gap_valor: float = 0
    embedding_similarity: Optional[float] = None


class ScoreBreakdown(BaseModel):
    """Weighted score breakdown for composite scoring."""
    embedding: float = 0
    preco: float = 0
    specs: float = 0
    interesses: float = 0
    weights: Optional[dict] = None


class MatchResult(BaseModel):
    """Result of a single match calculation."""
    ativo_origem_id: str
    ativo_destino_id: str
    score: float
    justificativa: str
    detalhes: MatchDetails
    score_breakdown: Optional[ScoreBreakdown] = None


class MatchResponse(BaseModel):
    """Response from the matching endpoint."""
    data: list[MatchResult]
    total: int


class MatchStatusUpdate(BaseModel):
    """Request to update a match status."""
    status: str  # 'aceito' | 'rejeitado' | 'pendente' | 'expirado'


class EmbedRequest(BaseModel):
    """Request to generate embedding for a single ativo."""
    ativo_id: str


class EmbedResponse(BaseModel):
    """Response from embedding endpoint."""
    ativo_id: str
    success: bool
    message: str


class EmbedBatchResponse(BaseModel):
    """Response from batch embedding endpoint."""
    total: int
    embedded: int
    errors: int
