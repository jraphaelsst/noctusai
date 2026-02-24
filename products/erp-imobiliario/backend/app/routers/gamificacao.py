"""
Gamification Router — leaderboard, points, achievements, and point registration.

-- CREATE TABLE pontuacoes (
--   id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
--   org_id uuid NOT NULL,
--   user_id uuid NOT NULL,
--   acao text NOT NULL,
--   pontos int NOT NULL,
--   referencia_id uuid,
--   referencia_tipo text,
--   created_at timestamptz NOT NULL DEFAULT now()
-- );
-- CREATE TABLE conquistas (
--   id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
--   org_id uuid NOT NULL,
--   user_id uuid NOT NULL,
--   tipo text NOT NULL,
--   nome text NOT NULL,
--   descricao text,
--   icone text NOT NULL DEFAULT '🏆',
--   desbloqueada_em timestamptz NOT NULL DEFAULT now()
-- );
"""
import logging
from typing import Optional, Literal
from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field
from app.dependencies import get_current_user, get_user_client, log_action
from app.responses import success_response, paginated_response, calculate_pagination
from app.config import settings
from app.services.gamificacao_service import (
    registrar_pontos,
    build_leaderboard,
    PONTOS_POR_ACAO,
    BADGES,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/gamificacao", tags=["Gamificação"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class RegistrarPontosRequest(BaseModel):
    acao: str = Field(..., description="Action type (novo_cliente, visita_realizada, etc.)")
    referencia_id: Optional[str] = None
    referencia_tipo: Optional[str] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/leaderboard")
async def leaderboard(
    periodo: Literal["semana", "mes", "geral"] = Query("geral"),
    authorization: Optional[str] = Header(None),
):
    """
    Get the leaderboard — ranking of agents by points.
    Supports filtering by period: semana, mes, geral.
    """
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    ranking = build_leaderboard(db, periodo)

    # Enrich with profile names
    if ranking:
        user_ids = [r["user_id"] for r in ranking]
        profiles_result = db.table("profiles").select("id, nome, avatar_url").in_(
            "id", user_ids
        ).execute()
        profiles_map = {p["id"]: p for p in (profiles_result.data or [])}

        for entry in ranking:
            profile = profiles_map.get(entry["user_id"], {})
            entry["nome"] = profile.get("nome", "Usuário")
            entry["avatar_url"] = profile.get("avatar_url")

    return success_response(ranking)


@router.get("/pontos")
async def meus_pontos(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    authorization: Optional[str] = Header(None),
):
    """Get the current user's points history."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    validated_page, validated_page_size, offset = calculate_pagination(
        page, page_size, settings.max_page_size
    )

    # Count
    count_result = db.table("pontuacoes").select("id", count="exact").eq(
        "user_id", user.id
    ).execute()
    total = count_result.count if count_result.count is not None else 0

    # Data
    result = db.table("pontuacoes").select("*").eq(
        "user_id", user.id
    ).order("created_at", desc=True).range(
        offset, offset + validated_page_size - 1
    ).execute()

    data = result.data or []

    # Add total points summary
    total_pontos = sum(r.get("pontos", 0) for r in data) if not offset else None

    response = paginated_response(data, total, validated_page, validated_page_size)

    if total_pontos is not None:
        # For first page, also compute grand total
        all_pts = db.table("pontuacoes").select("pontos").eq("user_id", user.id).execute()
        response["total_pontos"] = sum(r.get("pontos", 0) for r in (all_pts.data or []))

    return response


@router.get("/conquistas")
async def minhas_conquistas(authorization: Optional[str] = Header(None)):
    """Get the current user's badges/achievements."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    result = db.table("conquistas").select("*").eq(
        "user_id", user.id
    ).order("desbloqueada_em", desc=True).execute()

    unlocked = result.data or []
    unlocked_tipos = {c["tipo"] for c in unlocked}

    # Build full list with locked/unlocked state
    all_badges = []
    for badge in BADGES:
        is_unlocked = badge["tipo"] in unlocked_tipos
        badge_data = {
            "tipo": badge["tipo"],
            "nome": badge["nome"],
            "descricao": badge["descricao"],
            "icone": badge["icone"],
            "desbloqueada": is_unlocked,
        }
        if is_unlocked:
            matching = next((c for c in unlocked if c["tipo"] == badge["tipo"]), None)
            if matching:
                badge_data["desbloqueada_em"] = matching.get("desbloqueada_em")
        all_badges.append(badge_data)

    return success_response(all_badges)


@router.post("/registrar")
async def registrar(body: RegistrarPontosRequest, authorization: Optional[str] = Header(None)):
    """
    Register points for an action. Intended for internal/automated use.
    Also checks and awards new badges if criteria are met.
    """
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    if body.acao not in PONTOS_POR_ACAO:
        raise HTTPException(
            status_code=400,
            detail=f"Ação desconhecida: '{body.acao}'. "
                   f"Ações válidas: {', '.join(PONTOS_POR_ACAO.keys())}",
        )

    result = registrar_pontos(
        user_id=user.id,
        acao=body.acao,
        supabase=db,
        referencia_id=body.referencia_id,
        referencia_tipo=body.referencia_tipo,
    )

    return success_response(result)


@router.get("/regras")
async def regras(authorization: Optional[str] = Header(None)):
    """Get point rules and available badges — public reference endpoint."""
    await get_current_user(authorization)

    return success_response({
        "pontos_por_acao": PONTOS_POR_ACAO,
        "conquistas_disponiveis": [
            {
                "tipo": b["tipo"],
                "nome": b["nome"],
                "descricao": b["descricao"],
                "icone": b["icone"],
            }
            for b in BADGES
        ],
    })
