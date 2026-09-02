"""
Admin Users Router — Admin-only user management.

GET    /api/admin/users           — List all users with org (search, filter, pagination)
GET    /api/admin/users/{user_id} — Get single user with org info
PATCH  /api/admin/users/{user_id} — Update user fields, incl. org assign/revoke
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
    rows = result.data or []

    # Attach the org so the list's "Org" column can render a name. Without this
    # the FE read `u.organization?.nome` against a payload that never carried
    # `organization` (only GET /{user_id} attached it), so the column rendered
    # "—" for every row — a lying column that made org membership invisible
    # exactly where an admin goes to look at it.
    _attach_organizations(db, rows)

    return paginated_response(rows, total, validated_page, validated_page_size)


def _attach_organizations(db, rows: list[dict]) -> None:
    """Attach `organization` to each user row, in ONE query for the page."""
    org_ids = {r["org_id"] for r in rows if r.get("org_id")}
    if not org_ids:
        for row in rows:
            row["organization"] = None
        return

    orgs = (
        db.table("organizations")
        .select("id, nome, slug, plano")
        # postgrest-unbounded-ok: one page of users, so at most `page_size`
        # distinct org ids — capped at 100 by the Query(le=100) on the route.
        .in_("id", list(org_ids))
        .execute()
    )
    by_id = {o["id"]: o for o in (orgs.data or [])}
    for row in rows:
        row["organization"] = by_id.get(row.get("org_id"))


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
    """Update user fields (nome, role, org_role, org_id). Admin only.

    `org_id` is the org assign/revoke lever. A user belongs to exactly one org
    (`noctus_users.org_id` is NOT NULL, no membership join table), so "revoke"
    is a move to another org, never a detach. The move is what actually grants
    product data access: every product's RLS resolves through
    `public.current_org_id()` → `noctus_users.org_id`, and the platform
    `role='admin'` flag grants nothing at the data layer.
    """
    admin_user, _token = await get_current_admin(authorization)
    db = get_admin_client()

    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    # Verify user exists (and capture the pre-change org for the guards + audit)
    check = (
        db.table("noctus_users")
        .select("id, org_id, org_role")
        .eq("id", user_id)
        .single()
        .execute()
    )
    if not check.data:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    current_org_id = check.data.get("org_id")
    new_org_id = str(data["org_id"]) if data.get("org_id") else None
    data.pop("org_id", None)

    moving_org = new_org_id is not None and new_org_id != current_org_id
    if moving_org:
        _guard_org_reassignment(db, user_id, current_org_id, new_org_id, data, check.data)
        data["org_id"] = new_org_id

    result = db.table("noctus_users").update(data).eq("id", user_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    if moving_org:
        try:
            from app.services import audit_service
            await audit_service.log(
                user_id=admin_user.id,
                org_id=new_org_id,
                action="org_reassign",
                resource_type="user",
                resource_id=user_id,
                details={"from_org_id": current_org_id, "to_org_id": new_org_id},
            )
        except Exception as exc:
            logger.warning(
                "users: org_reassign audit log failed for user_id=%s (%s); reassignment succeeded",
                user_id, exc,
            )

    return success_response(result.data[0])


def _guard_org_reassignment(
    db, user_id: str, current_org_id: Optional[str], new_org_id: str,
    data: dict, profile: dict,
) -> None:
    """Refuse the org moves that would corrupt ownership. Raises HTTPException.

    Two things can go wrong when a user changes org, and both leave the tenant
    graph inconsistent rather than merely wrong:
      1. Moving an org's `owner_id` out of that org orphans it — the org would
         be owned by someone who is not a member and cannot administer it.
      2. Landing in the target org as `owner` when that org already has a
         different `owner_id` creates two owners disagreeing across two tables.
    """
    target = (
        db.table("organizations")
        .select("id, nome, owner_id")
        .eq("id", new_org_id)
        .execute()
    )
    if not target.data:
        raise HTTPException(status_code=404, detail="Organização não encontrada")

    if current_org_id:
        source = (
            db.table("organizations")
            .select("id, nome, owner_id")
            .eq("id", current_org_id)
            .execute()
        )
        source_row = source.data[0] if source.data else None
        if source_row and source_row.get("owner_id") == user_id:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Este usuário é o proprietário de '{source_row['nome']}'. "
                    "Transfira a propriedade da organização antes de movê-lo."
                ),
            )

    # Resulting org_role: the one being set in this same request, else the one
    # already on the profile (an unspecified role carries over on a move).
    resulting_role = data.get("org_role") or profile.get("org_role")
    target_owner = target.data[0].get("owner_id")
    if resulting_role == "owner" and target_owner and target_owner != user_id:
        raise HTTPException(
            status_code=409,
            detail=(
                f"'{target.data[0]['nome']}' já tem um proprietário. "
                "Escolha outro cargo de organização para este usuário."
            ),
        )


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
