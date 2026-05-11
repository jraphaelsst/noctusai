"""
Productivity Metrics Router — Daily productivity snapshots for Daily Life.

Tracks daily productivity metrics (tasks completed, checkins, events, notes)
and provides summary analytics (averages, streaks, trends).
"""
import logging
from typing import Optional
from datetime import date

from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import Field

from app.dependencies import get_user_client, get_current_user_org
from noctusai_lib.primitives.responses import success_response, paginated_response
from noctusai_lib.api.auth import first_or_none
from noctusai_lib.api import StrictHttpModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/metricas", tags=["Metrics"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class MetricCreate(StrictHttpModel):
    data: date
    tarefas_concluidas: int = Field(default=0, ge=0)
    tarefas_criadas: int = Field(default=0, ge=0)
    checkins_realizados: int = Field(default=0, ge=0)
    eventos_do_dia: int = Field(default=0, ge=0)
    notas_criadas: int = Field(default=0, ge=0)
    score_produtividade: Optional[float] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/resumo")
async def resumo_metricas(
    auth: tuple = Depends(get_current_user_org),
    dias: int = Query(30, ge=1, le=365),
):
    """Get a productivity summary: average score, streak, and trend."""
    user, token, _org_id = auth
    db = get_user_client(token)

    result = (
        db.table("metricas_produtividade")
        .select("*")
        .eq("user_id", str(user.id))
        .order("data", desc=True)
        .limit(dias)
        .execute()
    )
    metrics = result.data or []

    if not metrics:
        return success_response({
            "dias_analisados": 0,
            "score_medio": None,
            "total_tarefas_concluidas": 0,
            "total_checkins": 0,
            "streak_dias": 0,
        })

    scores = [m["score_produtividade"] for m in metrics if m.get("score_produtividade") is not None]
    avg_score = round(sum(scores) / len(scores), 2) if scores else None

    total_tarefas = sum(m.get("tarefas_concluidas", 0) for m in metrics)
    total_checkins = sum(m.get("checkins_realizados", 0) for m in metrics)

    # Compute streak: consecutive days with at least one task completed (most recent first)
    streak = 0
    for m in metrics:
        if m.get("tarefas_concluidas", 0) > 0 or m.get("checkins_realizados", 0) > 0:
            streak += 1
        else:
            break

    return success_response({
        "dias_analisados": len(metrics),
        "score_medio": avg_score,
        "total_tarefas_concluidas": total_tarefas,
        "total_checkins": total_checkins,
        "streak_dias": streak,
    })


@router.get("")
async def listar_metricas(
    auth: tuple = Depends(get_current_user_org),
    data_inicio: Optional[str] = Query(None, description="ISO date filter start"),
    data_fim: Optional[str] = Query(None, description="ISO date filter end"),
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
):
    """List productivity metrics with optional date range filter."""
    user, token, _org_id = auth
    db = get_user_client(token)

    query = (
        db.table("metricas_produtividade")
        .select("*", count="exact")
        .eq("user_id", str(user.id))
    )

    if data_inicio:
        query = query.gte("data", data_inicio)
    if data_fim:
        query = query.lte("data", data_fim)

    query = query.order("data", desc=True)

    offset = (page - 1) * page_size
    result = query.range(offset, offset + page_size - 1).execute()

    return paginated_response(result.data or [], result.count or 0, page, page_size)


@router.post("")
async def criar_metrica(body: MetricCreate, auth: tuple = Depends(get_current_user_org)):
    """Create a daily metric snapshot."""
    user, token, _org_id = auth
    db = get_user_client(token)

    result = db.table("metricas_produtividade").insert({
        "user_id": str(user.id),
        "data": str(body.data),
        "tarefas_concluidas": body.tarefas_concluidas,
        "tarefas_criadas": body.tarefas_criadas,
        "checkins_realizados": body.checkins_realizados,
        "eventos_do_dia": body.eventos_do_dia,
        "notas_criadas": body.notas_criadas,
        "score_produtividade": body.score_produtividade,
    }).execute()

    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=500, detail="Erro ao criar metrica")

    return success_response(row)
