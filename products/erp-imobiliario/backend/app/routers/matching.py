"""
Matching API Router — Unified Ativos Table

POST   /api/matching/gerar        — Generate matches (AI + rule-based fallback)
POST   /api/matching/embed         — Generate embedding for a single ativo
POST   /api/matching/embed-batch   — Batch embed unembedded ativos
GET    /api/matching                — List matches with filters
PATCH  /api/matching/{id}           — Update match status
"""
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Header

from app.dependencies import get_current_user, get_user_client, first_or_none
from app.responses import success_response
from app.schemas.matching import MatchRequest as GerarMatchesRequest, MatchStatusUpdate as AtualizarStatusRequest, EmbedRequest
from app.services.matching import (
    gerar_matches_para_imovel,
    gerar_matches_para_permuta,
    gerar_matches_com_embeddings,
    upsert_matches,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/matching", tags=["Matching"])


@router.post("/gerar")
async def gerar_matches(body: GerarMatchesRequest, authorization: Optional[str] = Header(None)):
    """Generate matches. Tries embedding-based matching first, falls back to rule-based."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    matches = []

    if body.ativo_origem_id:
        imovel_res = db.table("ativos").select("*").eq("id", body.ativo_origem_id).eq("natureza", "imovel").single().execute()
        if not imovel_res.data:
            raise HTTPException(status_code=404, detail="Imóvel não encontrado")
        imovel = imovel_res.data

        # Try embedding-based matching first
        if imovel.get("embedding"):
            matches = await gerar_matches_com_embeddings(imovel, db, body.score_minimo)

        # Fallback to rule-based if no embedding matches
        if not matches:
            permutas_res = db.table("ativos").select("*").in_("natureza", ["permuta_imovel", "permuta_automovel"]).eq("status", "ativo").execute()
            permutas = permutas_res.data or []
            matches = gerar_matches_para_imovel(imovel, permutas, body.score_minimo)

    elif body.ativo_destino_id:
        permuta_res = db.table("ativos").select("*").eq("id", body.ativo_destino_id).single().execute()
        if not permuta_res.data:
            raise HTTPException(status_code=404, detail="Permuta não encontrada")
        permuta = permuta_res.data

        # Try embedding-based matching first
        if permuta.get("embedding"):
            matches = await gerar_matches_com_embeddings(permuta, db, body.score_minimo)

        # Fallback to rule-based if no embedding matches
        if not matches:
            imoveis_res = db.table("ativos").select("*").eq("natureza", "imovel").eq("aceita_permutas", True).eq("status", "ativo").execute()
            imoveis = imoveis_res.data or []
            matches = gerar_matches_para_permuta(permuta, imoveis, body.score_minimo)

    # Bulk upsert matches via service
    upsert_matches(matches, db)

    logger.info(f"Generated {len(matches)} matches")
    return success_response(matches, total=len(matches))


@router.post("/embed")
async def embed_ativo(body: EmbedRequest, authorization: Optional[str] = Header(None)):
    """Generate embedding for a single ativo."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    # Lazy import to avoid ImportError when OpenAI is not needed
    from app.services.embedding_service import embed_ativo as do_embed

    ativo_res = db.table("ativos").select("*").eq("id", body.ativo_id).single().execute()
    if not ativo_res.data:
        raise HTTPException(status_code=404, detail="Ativo não encontrado")

    try:
        success = await do_embed(ativo_res.data, db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return success_response({
        "ativo_id": body.ativo_id,
        "success": success,
        "message": "Embedding gerado com sucesso" if success else "Ativo sem dados suficientes para gerar embedding",
    })


@router.post("/embed-batch")
async def embed_batch(authorization: Optional[str] = Header(None)):
    """Batch embed all ativos without embeddings."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    from app.services.embedding_service import embed_ativos_batch

    # Fetch all ativos without embeddings
    res = db.table("ativos").select("id").is_("embedding", "null").eq("status", "ativo").execute()
    ativo_ids = [row["id"] for row in (res.data or [])]

    if not ativo_ids:
        return success_response({"total": 0, "embedded": 0, "errors": 0})

    try:
        result = await embed_ativos_batch(ativo_ids, db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return success_response(result)


_ATIVO_SUMMARY_FIELDS = "id,natureza,tipo_imovel,tipo_veiculo,marca,modelo,valor,titulo_anuncio,ref,cidade,bairro,estado,zona,condominio_nome,fotos"


@router.get("")
async def listar_matches(
    ativo_origem_id: Optional[str] = None,
    ativo_destino_id: Optional[str] = None,
    min_score: Optional[float] = None,
    status: Optional[str] = None,
    authorization: Optional[str] = Header(None),
):
    """List persisted matches with optional filters, enriched with ativo summaries."""
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
    matches = result.data or []

    if not matches:
        return success_response([], total=0)

    # Collect unique ativo IDs and batch-fetch summaries (avoids N+1)
    ativo_ids = set()
    for m in matches:
        ativo_ids.add(m["ativo_origem_id"])
        ativo_ids.add(m["ativo_destino_id"])

    ativos_res = db.table("ativos").select(_ATIVO_SUMMARY_FIELDS).in_("id", list(ativo_ids)).execute()
    ativos_map = {a["id"]: a for a in (ativos_res.data or [])}

    for m in matches:
        m["ativo_origem"] = ativos_map.get(m["ativo_origem_id"])
        m["ativo_destino"] = ativos_map.get(m["ativo_destino_id"])

    return success_response(matches, total=len(matches))


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
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=404, detail="Match não encontrado")

    return success_response(row)
