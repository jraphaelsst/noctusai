"""
Admin Users Router — Admin-only user management.

GET    /api/admin/users           — List all users (search, filter, pagination)
GET    /api/admin/users/{user_id} — Get single user with org info
PATCH  /api/admin/users/{user_id} — Update user fields
DELETE /api/admin/users/{user_id} — Delete user
"""
import logging
from typing import Optional
from fastapi import APIRouter, Header, HTTPException, Query

from app.database import get_admin_client
from app.dependencies import get_current_admin
from app.schemas.users import UserUpdate
from noctusai_lib.primitives.responses import paginated_response, success_response, ok_response, calculate_pagination

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin/users", tags=["Admin Users"])


@router.get("")
async def listar_users(
    authorization: Optional[str] = Header(None),
    busca: Optional[str] = Query(None, description="Busca por nome ou email"),
    role: Optional[str] = Query(None, description="Filtrar por role"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List all users with optional search and role filter. Admin only."""
    await get_current_admin(authorization)
    db = get_admin_client()

    validated_page, validated_page_size, offset = calculate_pagination(page, page_size)

    # Count query
    count_query = db.table("noctus_users").select("id")
    if busca:
        count_query = count_query.or_(f"nome.ilike.%{busca}%,email.ilike.%{busca}%")
    if role:
        count_query = count_query.eq("role", role)
    count_result = count_query.execute()
    total = len(count_result.data) if count_result.data else 0

    # Data query
    query = db.table("noctus_users").select("*")
    if busca:
        query = query.or_(f"nome.ilike.%{busca}%,email.ilike.%{busca}%")
    if role:
        query = query.eq("role", role)
    query = query.order("created_at", desc=True).range(offset, offset + validated_page_size - 1)

    result = query.execute()
    return paginated_response(result.data or [], total, validated_page, validated_page_size)


@router.get("/{user_id}")
async def get_user(user_id: str, authorization: Optional[str] = Header(None)):
    """Get a single user with their organization info. Admin only."""
    await get_current_admin(authorization)
    db = get_admin_client()

    user_result = db.table("noctus_users").select("*").eq("id", user_id).single().execute()
    if not user_result.data:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    # Fetch organization info if user has an org_id
    user_data = user_result.data
    if user_data.get("org_id"):
        org_result = db.table("organizations").select("id, nome, slug, plano").eq(
            "id", user_data["org_id"]
        ).single().execute()
        user_data["organization"] = org_result.data
    else:
        user_data["organization"] = None

    return success_response(user_data)


@router.patch("/{user_id}")
async def atualizar_user(user_id: str, body: UserUpdate, authorization: Optional[str] = Header(None)):
    """Update user fields (role, org_role, nome). Admin only."""
    await get_current_admin(authorization)
    db = get_admin_client()

    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    # Verify user exists
    check = db.table("noctus_users").select("id").eq("id", user_id).single().execute()
    if not check.data:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    result = db.table("noctus_users").update(data).eq("id", user_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    return success_response(result.data[0])


@router.delete("/{user_id}")
async def deletar_user(user_id: str, authorization: Optional[str] = Header(None)):
    """Delete a user. Admin only. Pre-checks existence."""
    await get_current_admin(authorization)
    db = get_admin_client()

    # DELETE pre-check
    check = db.table("noctus_users").select("id").eq("id", user_id).single().execute()
    if not check.data:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    db.table("noctus_users").delete().eq("id", user_id).execute()
    return ok_response("Usuário excluído com sucesso")
