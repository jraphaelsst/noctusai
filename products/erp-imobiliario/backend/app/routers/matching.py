"""
Matching API Router — Unified Ativos Table

POST   /api/matching/gerar   — Generate matches
GET    /api/matching          — List matches with filters
PATCH  /api/matching/{id}     — Update match status
"""
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel, model_validator

from app.dependencies import get_current_user, get_user_client, get_admin_client
from app.services.matching import (
    gerar_matches_para_imovel,
    gerar_matches_para_permuta,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/matching", tags=["Matching"])


class GerarMatchesRequest(BaseModel):
    ativo_origem_id: Optional[str] = None
    ativo_destino_id: Optional[str] = None
    score_minimo: int = 20

    @model_validator(mode='after')
    def at_least_one_id(self):
        if not self.ativo_origem_id and not self.ativo_destino_id:
            raise ValueError('Informe ativo_origem_id ou ativo_destino_id')
        return self


class AtualizarStatusRequest(BaseModel):
    status: str


@router.post("/gerar")
async def gerar_matches(body: GerarMatchesRequest, authorization: Optional[str] = Header(None)):
    """Generate matches. Provide ativo_origem_id (imovel) or ativo_destino_id (permuta)."""
    user, token = await get_current_user(authorization)
    db = get_admin_client()

    matches = []

    if body.ativo_origem_id:
        imovel_res = db.table("ativos").select("*").eq("id", body.ativo_origem_id).eq("natureza", "imovel").single().execute()
        if not imovel_res.data:
            raise HTTPException(status_code=404, detail="Imóvel não encontrado")
        imovel = imovel_res.data

        permutas_res = db.table("ativos").select("*").in_("natureza", ["permuta_imovel", "permuta_automovel"]).eq("status", "ativo").execute()
        permutas = permutas_res.data or []

        matches = gerar_matches_para_imovel(imovel, permutas, body.score_minimo)

    elif body.ativo_destino_id:
        permuta_res = db.table("ativos").select("*").eq("id", body.ativo_destino_id).single().execute()
        if not permuta_res.data:
            raise HTTPException(status_code=404, detail="Permuta não encontrada")
        permuta = permuta_res.data

        imoveis_res = db.table("ativos").select("*").eq("natureza", "imovel").eq("aceita_permutas", True).eq("status", "ativo").execute()
        imoveis = imoveis_res.data or []

        matches = gerar_matches_para_permuta(permuta, imoveis, body.score_minimo)

    # Upsert matches
    for match in matches:
        db.table("matches").upsert(
            {
                "ativo_origem_id": match["ativo_origem_id"],
                "ativo_destino_id": match["ativo_destino_id"],
                "score": match["score"],
                "justificativa": match["justificativa"],
                "detalhes": match["detalhes"],
                "status": "pendente",
            },
            on_conflict="ativo_origem_id,ativo_destino_id",
        ).execute()

    logger.info(f"Generated {len(matches)} matches")
    return {"total": len(matches), "matches": matches}


@router.get("")
async def listar_matches(
    ativo_origem_id: Optional[str] = None,
    ativo_destino_id: Optional[str] = None,
    min_score: Optional[int] = None,
    status: Optional[str] = None,
    authorization: Optional[str] = Header(None),
):
    """List persisted matches with optional filters."""
    _, token = await get_current_user(authorization)
    db = get_user_client(token)

    query = db.table("matches").select("*").order("score", desc=True)

    if ativo_origem_id:
        query = query.eq("ativo_origem_id", ativo_origem_id)
    if ativo_destino_id:
        query = query.eq("ativo_destino_id", ativo_destino_id)
    if min_score:
        query = query.gte("score", min_score)
    if status:
        query = query.eq("status", status)

    result = query.execute()
    return {"data": result.data or [], "total": len(result.data or [])}


@router.patch("/{match_id}")
async def atualizar_status_match(
    match_id: str,
    body: AtualizarStatusRequest,
    authorization: Optional[str] = Header(None),
):
    """Update match status (aceito, rejeitado)."""
    _, token = await get_current_user(authorization)
    db = get_user_client(token)

    valid_statuses = {"aceito", "rejeitado", "pendente", "expirado"}
    if body.status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Status inválido. Use: {valid_statuses}")

    result = db.table("matches").update({"status": body.status}).eq("id", match_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Match não encontrado")

    return {"data": result.data[0]}
