"""
Matching API endpoints.

POST /api/matching/gerar     — Generate matches for an imóvel or perfil
GET  /api/matching            — List persisted matches with filters
PATCH /api/matching/{id}      — Update match status (aceitar/rejeitar)
"""
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Header

from app.database import get_supabase_client
from app.schemas.matching import MatchRequest, MatchResponse, MatchStatusUpdate
from app.services.matching import gerar_matches_para_imovel, gerar_matches_para_perfil

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/matching", tags=["Matching"])


# --- Helper: extract user from Authorization header ---

async def _get_user_from_token(authorization: str | None):
    """Validate the JWT and return the user."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token de autenticação ausente")

    token = authorization.replace("Bearer ", "")
    client = get_supabase_client()

    try:
        user_response = client.auth.get_user(token)
        if not user_response or not user_response.user:
            raise HTTPException(status_code=401, detail="Token inválido")
        return user_response.user, token
    except Exception as e:
        logger.error(f"Auth error: {e}")
        raise HTTPException(status_code=401, detail="Não autenticado")


# --- Endpoints ---

@router.post("/gerar", response_model=MatchResponse)
async def gerar_matches(
    request: MatchRequest,
    authorization: Optional[str] = Header(None),
):
    """
    Generate matches for an imóvel or perfil de permuta.

    The algorithm:
    1. Fetches the target imóvel/perfil from Supabase
    2. Fetches all counterpart perfis/imóveis
    3. Calculates scores (0-100) for each pair
    4. Persists results in the `matches` table (upsert)
    5. Returns the list of matches

    Only matches with score > 0 are stored.
    """
    user, token = await _get_user_from_token(authorization)
    client = get_supabase_client(token)

    match_results = []

    if request.imovel_id:
        logger.info(f"Generating matches for imovel: {request.imovel_id}")

        # Fetch the imóvel
        res = client.table("imoveis").select("*").eq("id", request.imovel_id).single().execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="Imóvel não encontrado")
        imovel = res.data

        # Fetch all perfis de permuta (category: imóvel)
        res_perfis = client.table("perfis_permutas").select("*").eq("categoria", "imovel").execute()
        perfis = res_perfis.data or []

        if perfis:
            match_results = gerar_matches_para_imovel(imovel, perfis)

        # Delete old matches for this imóvel
        client.table("matches").delete().eq("imovel_id", request.imovel_id).execute()

    if request.perfil_permuta_id:
        logger.info(f"Generating matches for perfil: {request.perfil_permuta_id}")

        # Fetch the perfil
        res = client.table("perfis_permutas").select("*").eq("id", request.perfil_permuta_id).single().execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="Perfil de permuta não encontrado")
        perfil = res.data

        # Fetch all imóveis that accept permutas
        res_imoveis = client.table("imoveis").select("*").eq("aceita_permutas", True).execute()
        imoveis = res_imoveis.data or []

        if imoveis:
            match_results = gerar_matches_para_perfil(perfil, imoveis)

        # Delete old matches for this perfil
        client.table("matches").delete().eq("perfil_permuta_id", request.perfil_permuta_id).execute()

    # Persist new matches
    if match_results:
        match_rows = [
            {
                "imovel_id": m.imovel_id,
                "perfil_permuta_id": m.perfil_permuta_id,
                "score": m.score,
                "status": "pendente",
                "justificativa": m.justificativa,
                "detalhes": m.detalhes.model_dump(),
            }
            for m in match_results
        ]

        client.table("matches").upsert(
            match_rows,
            on_conflict="imovel_id,perfil_permuta_id",
        ).execute()

    # Log the action
    try:
        client.table("user_actions_log").insert({
            "usuario_id": user.id,
            "tipo_acao": "criar",
            "tipo_entidade": "match",
            "descricao": f"Gerou {len(match_results)} matches"
                         f"{' para imóvel ' + request.imovel_id if request.imovel_id else ''}"
                         f"{' para perfil ' + request.perfil_permuta_id if request.perfil_permuta_id else ''}",
        }).execute()
    except Exception as e:
        logger.warning(f"Failed to log action (non-blocking): {e}")

    logger.info(f"Generated {len(match_results)} matches successfully")

    return MatchResponse(
        data=match_results,
        total=len(match_results),
    )


@router.get("")
async def listar_matches(
    imovel_id: Optional[str] = None,
    perfil_permuta_id: Optional[str] = None,
    min_score: Optional[int] = None,
    authorization: Optional[str] = Header(None),
):
    """List persisted matches with optional filters."""
    _, token = await _get_user_from_token(authorization)
    client = get_supabase_client(token)

    query = client.table("matches").select(
        "*, "
        "imovel:imoveis!matches_imovel_id_fkey("
        "  id, tipo, preco_pedido, aceita_permutas,"
        "  cidade, estado, bairro, cep,"
        "  area_privativa, area_total, quartos, vagas,"
        "  titulo_anuncio, fotos, owner_id, status"
        "), "
        "perfil_permuta:perfis_permutas!matches_perfil_permuta_id_fkey("
        "  id, categoria, tipo_imovel, tipo_movel,"
        "  faixa_preco_min, faixa_preco_max, regiao_preferida,"
        "  aceita_completar_diferenca, limite_complemento,"
        "  valor_estimado, cliente_ofertante_id, status"
        ")"
    ).order("score", desc=True)

    if imovel_id:
        query = query.eq("imovel_id", imovel_id)
    if perfil_permuta_id:
        query = query.eq("perfil_permuta_id", perfil_permuta_id)
    if min_score:
        query = query.gte("score", min_score)

    res = query.execute()
    return {"data": res.data or [], "total": len(res.data or [])}


@router.patch("/{match_id}")
async def atualizar_status_match(
    match_id: str,
    body: MatchStatusUpdate,
    authorization: Optional[str] = Header(None),
):
    """Update match status (aceitar/rejeitar)."""
    user, token = await _get_user_from_token(authorization)
    client = get_supabase_client(token)

    if body.status not in ("aceito", "rejeitado"):
        raise HTTPException(status_code=400, detail="Status deve ser 'aceito' ou 'rejeitado'")

    res = client.table("matches").update(
        {"status": body.status}
    ).eq("id", match_id).execute()

    if not res.data:
        raise HTTPException(status_code=404, detail="Match não encontrado")

    # Log action
    try:
        label = "Aceitou" if body.status == "aceito" else "Rejeitou"
        client.table("user_actions_log").insert({
            "usuario_id": user.id,
            "tipo_acao": "editar",
            "tipo_entidade": "match",
            "entidade_id": match_id,
            "descricao": f"{label} match {match_id}",
        }).execute()
    except Exception as e:
        logger.warning(f"Failed to log action (non-blocking): {e}")

    return {"data": res.data[0] if res.data else None}
