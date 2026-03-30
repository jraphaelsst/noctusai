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

from app.dependencies import get_current_user, get_user_client, get_org_id, first_or_none
from app.responses import success_response
from app.services.ai_service import check_openai_configured
from app.schemas.matching import MatchRequest as GerarMatchesRequest, MatchStatusUpdate as AtualizarStatusRequest, EmbedRequest
from app.services.matching import (
    gerar_matches_para_imovel,
    gerar_matches_para_permuta,
    upsert_matches,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/matching", tags=["Matching"])


_SCORE_MINIMO = 45.0

# Fields needed by the matching algorithm — avoids fetching all 50+ columns
_MATCHING_FIELDS = (
    "id,natureza,tipo_imovel,tipo_veiculo,marca,modelo,valor,titulo_anuncio,"
    "descricao_seo,ref,cidade,bairro,estado,zona,regiao_preferida,"
    "quartos,quartos_min,vagas,vagas_min,area_total,area_privativa,"
    "metragem_min,metragem_max,faixa_preco_min,faixa_preco_max,"
    "aceita_permutas,aceita_completar_diferenca,interesses,"
    "fotos,tour_virtual_url,pontos_de_interesse,condominio_nome,condominio_id,"
    "ano,motor,status,embedding"
)


def _match_single_ativo(ativo: dict, db) -> list[dict]:
    """Match a single ativo against all counterparts.

    Unified path: hard filters first → scoring → embedding enhancement
    (if embeddings available). No separate embedding path — embeddings
    enhance scores for pairs that already passed hard filters.
    """
    is_imovel = ativo.get("natureza") == "imovel"

    if is_imovel:
        permutas_res = db.table("ativos").select(_MATCHING_FIELDS).in_(
            "natureza", ["permuta_imovel", "permuta_automovel"]
        ).eq("status", "ativo").execute()
        return gerar_matches_para_imovel(ativo, permutas_res.data or [], _SCORE_MINIMO)
    else:
        imoveis_res = db.table("ativos").select(_MATCHING_FIELDS).eq(
            "natureza", "imovel"
        ).eq("aceita_permutas", True).eq("status", "ativo").execute()
        return gerar_matches_para_permuta(ativo, imoveis_res.data or [], _SCORE_MINIMO)


@router.post("/gerar")
async def gerar_matches(body: GerarMatchesRequest, authorization: Optional[str] = Header(None)):
    """Generate matches automatically. Tries embedding-based first, falls back to rule-based.
    When both IDs are empty, performs a full platform scan."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    matches = []

    if body.ativo_origem_id:
        imovel_res = db.table("ativos").select(_MATCHING_FIELDS).eq("id", body.ativo_origem_id).eq("natureza", "imovel").single().execute()
        if not imovel_res.data:
            raise HTTPException(status_code=404, detail="Imóvel não encontrado")
        matches = _match_single_ativo(imovel_res.data, db)

    elif body.ativo_destino_id:
        permuta_res = db.table("ativos").select(_MATCHING_FIELDS).eq("id", body.ativo_destino_id).single().execute()
        if not permuta_res.data:
            raise HTTPException(status_code=404, detail="Permuta não encontrada")
        matches = _match_single_ativo(permuta_res.data, db)

    else:
        # Full platform scan: match all active imoveis against all active permutas
        imoveis_res = db.table("ativos").select(_MATCHING_FIELDS).eq(
            "natureza", "imovel"
        ).eq("aceita_permutas", True).eq("status", "ativo").execute()

        for imovel in (imoveis_res.data or []):
            imovel_matches = _match_single_ativo(imovel, db)
            matches.extend(imovel_matches)

    # Bulk upsert matches via service
    upsert_matches(matches, db)

    logger.info(f"Generated {len(matches)} matches")
    return success_response(matches, total=len(matches))


@router.post("/embed")
async def embed_ativo(body: EmbedRequest, authorization: Optional[str] = Header(None)):
    """Generate embedding for a single ativo."""
    user, token = await get_current_user(authorization)
    if not check_openai_configured(get_org_id(user)):
        raise HTTPException(
            status_code=422,
            detail="OpenAI API Key não configurada. "
            "Acesse Configurações > Chaves de API para configurar.",
        )
    db = get_user_client(token)

    from app.services.embedding_service import embed_ativo as do_embed

    ativo_res = db.table("ativos").select(_MATCHING_FIELDS).eq("id", body.ativo_id).single().execute()
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
    if not check_openai_configured(get_org_id(user)):
        raise HTTPException(
            status_code=422,
            detail="OpenAI API Key não configurada. "
            "Acesse Configurações > Chaves de API para configurar.",
        )
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


@router.get("/counts")
async def match_counts(authorization: Optional[str] = Header(None)):
    """Return match counts per ativo_destino_id (lightweight aggregation)."""
    _, token = await get_current_user(authorization)
    db = get_user_client(token)

    result = db.table("matches").select("ativo_destino_id").execute()
    counts: dict[str, int] = {}
    for row in (result.data or []):
        did = row["ativo_destino_id"]
        counts[did] = counts.get(did, 0) + 1

    return success_response(counts)


@router.get("")
async def listar_matches(
    ativo_origem_id: Optional[str] = None,
    ativo_destino_id: Optional[str] = None,
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

    check = db.table("matches").select("id").eq("id", match_id).execute()
    if not check.data:
        raise HTTPException(status_code=404, detail="Match não encontrado")

    result = db.table("matches").update({"status": body.status}).eq("id", match_id).execute()
    return success_response(first_or_none(result))
