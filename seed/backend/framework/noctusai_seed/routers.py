"""
Standard routers that every product gets out of the box.

Every NoctusAI product includes:
  - Health check endpoint
  - Notification proxy (to core public.notifications)
  - Team management (invitations, members)

Products get these by calling create_standard_routers() and including
them in their app. No need to write health.py, notificacoes.py, or
team.py in every product.

Usage::

    standard = create_standard_routers(deps, settings, product_name="Mailing")
    for router in standard:
        app.include_router(router)
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from noctusai_lib.invitations import (
    create_invitation,
    validate_invitation,
    accept_invitation,
    cancel_invitation,
    list_pending_invitations,
)
from noctusai_lib.email_templates import send_product_invitation_email
from noctusai_lib.notifications import map_notification_to_pt
from noctusai_lib.roles import ORG_ROLE_LABELS

logger = logging.getLogger(__name__)


def _create_health_router(product_name: str, version: str = "0.1.0") -> APIRouter:
    router = APIRouter(tags=["Health"])

    @router.get("/api/health")
    async def health_check():
        return {"status": "ok", "version": version, "product": product_name}

    return router


def _create_notificacoes_router(deps) -> APIRouter:
    router = APIRouter(prefix="/api/notificacoes", tags=["Notificacoes"])

    @router.get("")
    async def listar(
        authorization: Optional[str] = Header(None),
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
    ):
        user, token = await deps.get_current_user(authorization)
        core = deps.get_core_client()
        offset = (page - 1) * page_size
        result = (
            core.table("notifications")
            .select("*", count="exact")
            .eq("user_id", str(user.id))
            .order("created_at", desc=True)
            .range(offset, offset + page_size - 1)
            .execute()
        )
        items = [map_notification_to_pt(n) for n in (result.data or [])]
        return {"data": items, "total": result.count or 0, "page": page, "page_size": page_size}

    @router.get("/contagem")
    async def contagem(authorization: Optional[str] = Header(None)):
        user, token = await deps.get_current_user(authorization)
        core = deps.get_core_client()
        result = (
            core.table("notifications")
            .select("id", count="exact")
            .eq("user_id", str(user.id))
            .eq("is_read", False)
            .execute()
        )
        return {"nao_lidas": result.count or 0}

    @router.patch("/{notificacao_id}/ler")
    async def marcar_lida(notificacao_id: str, authorization: Optional[str] = Header(None)):
        user, _ = await deps.get_current_user(authorization)
        core = deps.get_core_client()
        core.table("notifications").update({"is_read": True}).eq("id", notificacao_id).eq("user_id", str(user.id)).execute()
        return {"ok": True}

    @router.post("/ler-todas")
    async def marcar_todas_lidas(authorization: Optional[str] = Header(None)):
        user, _ = await deps.get_current_user(authorization)
        core = deps.get_core_client()
        core.table("notifications").update({"is_read": True}).eq("user_id", str(user.id)).eq("is_read", False).execute()
        return {"ok": True}

    return router


def _create_team_router(deps, settings, product_name: str) -> APIRouter:
    router = APIRouter(prefix="/api/team", tags=["Team"])

    @router.get("")
    async def list_members(authorization: Optional[str] = Header(None)):
        user, _ = await deps.get_current_user(authorization)
        org_id = deps.get_org_id(user)
        core = deps.get_core_client()
        result = core.table("noctus_users").select("*").eq("org_id", org_id).execute()
        return {"data": result.data or []}

    @router.post("/invite")
    async def invite_member(
        body: dict,
        authorization: Optional[str] = Header(None),
    ):
        user, _ = await deps.get_current_user(authorization)
        role = deps.get_user_role(user)
        if role not in ("platform_admin", "owner", "admin", "manager"):
            raise HTTPException(status_code=403, detail="Sem permissao para convidar")
        org_id = deps.get_org_id(user)
        admin = deps.get_admin_client()
        invite = create_invitation(
            db=admin,
            schema=deps._db._schema,
            email=body["email"],
            org_id=org_id,
            role=body.get("role", "member"),
            invited_by=str(user.id),
        )
        inviter_name = (user.user_metadata or {}).get("name", "Um administrador")
        org_name = (user.user_metadata or {}).get("org_name", "sua organizacao")
        role_label = ORG_ROLE_LABELS.get(body.get("role", "member"), body.get("role", "member"))
        base_url = settings.cors_origins.split(",")[0] if settings.cors_origins else "http://localhost:3000"
        send_product_invitation_email(
            to=body["email"],
            product_name=product_name,
            org_name=org_name,
            role_label=role_label,
            invite_token=invite["token"],
            invited_by=inviter_name,
            base_url=base_url,
        )
        return {"data": invite}

    @router.get("/accept/validate")
    async def validate_invite(token: str = Query(...)):
        admin = deps.get_admin_client()
        result = validate_invitation(db=admin, schema=deps._db._schema, token=token)
        if not result:
            raise HTTPException(status_code=400, detail="Convite invalido ou expirado")
        return {"data": result}

    @router.post("/accept")
    async def accept_invite(body: dict):
        admin = deps.get_admin_client()
        result = accept_invitation(
            db=admin,
            schema=deps._db._schema,
            token=body["token"],
            user_id=body.get("user_id"),
            email=body["email"],
            password=body.get("password"),
            name=body.get("name"),
        )
        if not result:
            raise HTTPException(status_code=400, detail="Erro ao aceitar convite")
        return {"data": result}

    @router.get("/invitations")
    async def list_invitations(authorization: Optional[str] = Header(None)):
        user, _ = await deps.get_current_user(authorization)
        role = deps.get_user_role(user)
        if role not in ("platform_admin", "owner", "admin"):
            raise HTTPException(status_code=403, detail="Sem permissao")
        org_id = deps.get_org_id(user)
        admin = deps.get_admin_client()
        result = list_pending_invitations(db=admin, schema=deps._db._schema, org_id=org_id)
        return {"data": result}

    @router.delete("/invitations/{invitation_id}")
    async def cancel_invite(invitation_id: str, authorization: Optional[str] = Header(None)):
        user, _ = await deps.get_current_user(authorization)
        role = deps.get_user_role(user)
        if role not in ("platform_admin", "owner", "admin"):
            raise HTTPException(status_code=403, detail="Sem permissao")
        admin = deps.get_admin_client()
        cancel_invitation(db=admin, schema=deps._db._schema, invitation_id=invitation_id)
        return {"ok": True}

    @router.delete("/{user_id}")
    async def remove_member(user_id: str, authorization: Optional[str] = Header(None)):
        user, _ = await deps.get_current_user(authorization)
        role = deps.get_user_role(user)
        if role not in ("platform_admin", "owner", "admin"):
            raise HTTPException(status_code=403, detail="Sem permissao")
        if str(user.id) == user_id:
            raise HTTPException(status_code=400, detail="Nao pode remover a si mesmo")
        core = deps.get_core_client()
        core.table("noctus_users").delete().eq("id", user_id).execute()
        return {"ok": True}

    return router


def create_standard_routers(deps, settings, product_name: str, version: str = "0.1.0") -> list:
    """Create the standard routers every product includes.

    Returns a list of APIRouter instances: [health, notificacoes, team].
    """
    return [
        _create_health_router(product_name, version),
        _create_notificacoes_router(deps),
        _create_team_router(deps, settings, product_name),
    ]
