"""
Pydantic schemas for matching requests and responses.
"""
from pydantic import BaseModel, Field
from typing import Optional


class MatchRequest(BaseModel):
    """Request to generate matches. Both IDs empty = full platform scan."""
    ativo_origem_id: Optional[str] = None
    ativo_destino_id: Optional[str] = None


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
    """Weighted score breakdown — unified for both AI and rule-based matches."""
    embedding_similarity: float = 0
    compatibilidade_regiao: float = 0
    compatibilidade_preco: float = 0
    compatibilidade_specs: float = 0
    qualidade_anuncio: float = 0
    interesses: float = 0


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
