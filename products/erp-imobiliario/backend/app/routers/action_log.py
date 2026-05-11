"""
Action Log Router — Server-side action logging and log retrieval.
"""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, Header, Query
from app.dependencies import get_current_user, get_user_client, get_admin_client
from app.responses import success_response

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/logs", tags=["ActionLog"])


@router.get("")
async def listar_logs(
    usuario_id: Optional[str] = Query(None),
    data_inicio: Optional[str] = Query(None),
    data_fim: Optional[str] = Query(None),
    auth = Depends(get_current_user)):
    user, token = auth
    db = get_user_client(token)

    query = db.table("user_actions_log").select("*").order("created_at", desc=True).limit(200)

    if usuario_id and usuario_id != "todos":
        query = query.eq("usuario_id", usuario_id)
    if data_inicio:
        query = query.gte("created_at", data_inicio)
    if data_fim:
        query = query.lte("created_at", data_fim)

    result = query.execute()
    logs = result.data or []

    # Enrich with user names (server-side join)
    if logs:
        user_ids = list({log["usuario_id"] for log in logs})
        profiles = db.table("profiles").select("id, nome, email").in_("id", user_ids).execute()
        users_map = {p["id"]: p for p in (profiles.data or [])}
        for log in logs:
            log["usuario"] = users_map.get(log["usuario_id"])

    return success_response(logs, total=len(logs))
