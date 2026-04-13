"""
Notifications router — proxies to public.notifications via get_core_client().
Portuguese field mapping for product frontends.
"""
from typing import Optional
from fastapi import APIRouter, Header, HTTPException
from noctusai_shared.responses import success_response, paginated_response, ok_response
from app.dependencies import get_current_user
from app.database import get_core_client

router = APIRouter(prefix="/api/notificacoes", tags=["Notificações"])


def _map_notification(n: dict) -> dict:
    """Map core English fields to Portuguese."""
    return {
        "id": n["id"],
        "tipo": n.get("type"),
        "titulo": n.get("title"),
        "mensagem": n.get("message"),
        "is_read": n.get("read", False),
        "link": (n.get("metadata") or {}).get("link"),
        "created_at": n.get("created_at"),
    }


@router.get("")
async def listar(
    page: int = 1,
    page_size: int = 20,
    apenas_nao_lidas: bool = False,
    authorization: Optional[str] = Header(None),
):
    user, token = await get_current_user(authorization)
    db = get_core_client()

    query = db.table("notifications").select("*", count="exact").eq("user_id", user.id)
    if apenas_nao_lidas:
        query = query.eq("read", False)

    query = query.order("created_at", desc=True)
    start = (page - 1) * page_size
    query = query.range(start, start + page_size - 1)
    result = query.execute()

    mapped = [_map_notification(n) for n in (result.data or [])]
    return paginated_response(mapped, result.count or 0, page, page_size)


@router.get("/contagem")
async def contagem_nao_lidas(authorization: Optional[str] = Header(None)):
    user, token = await get_current_user(authorization)
    db = get_core_client()
    result = db.table("notifications").select("id", count="exact").eq(
        "user_id", user.id
    ).eq("read", False).execute()
    return {"nao_lidas": result.count or 0}


@router.patch("/{notificacao_id}/ler")
async def marcar_como_lida(notificacao_id: str, authorization: Optional[str] = Header(None)):
    user, token = await get_current_user(authorization)
    db = get_core_client()
    result = db.table("notifications").update({"read": True}).eq(
        "id", notificacao_id
    ).eq("user_id", user.id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Notificação não encontrada")
    return success_response(_map_notification(result.data[0]))


@router.post("/ler-todas")
async def marcar_todas_como_lidas(authorization: Optional[str] = Header(None)):
    user, token = await get_current_user(authorization)
    db = get_core_client()
    result = db.table("notifications").update({"read": True}).eq(
        "user_id", user.id
    ).eq("read", False).execute()
    count = len(result.data) if result.data else 0
    return ok_response(f"{count} notificações marcadas como lidas")
