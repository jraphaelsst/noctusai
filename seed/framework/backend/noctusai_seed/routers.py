"""
Standard routers that NoctusAI products can opt into.

Bundled routers live here:
  - "health"       → `/api/health`
  - "notificacoes" → `/api/notificacoes` (proxy to core `public.notifications`)
  - "team"         → `/api/team` (invitations, members)
  - "llm"          → `/api/llm/providers|models|preferences`
  - "ai_outputs"   → `/api/ai/outputs` (per-entity AI-output lookup; P1 pattern)
  - "ai_feedback"  → `/api/ai/feedback` (thumbs feedback on AI outputs; P1)
  - "scheduler"    → `/api/scheduler/jobs[/{job_id}]` (read-only APScheduler view)
  - "status_paginas" → `/api/status-paginas` (list + change page-visibility status; admin/dev-gated)

Products declare which ones they want via the `standard_routers=[...]` kwarg
on `create_product_app()`. `build_standard_routers()` resolves that list
against the `_STANDARD_ROUTERS` registry. Unknown names raise `ValueError`.

Usage::

    # Inside create_product_app — products never call this directly.
    for router in build_standard_routers(
        deps, settings, product_name="Mailing", version="0.1.0",
        names=["health", "notificacoes", "team"],
    ):
        app.include_router(router)
"""
import logging
from typing import Optional, Sequence

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from noctusai_lib.domain.invitations import (
    create_invitation,
    validate_invitation,
    accept_invitation,
    cancel_invitation,
    list_pending_invitations,
)
from noctusai_lib.integrations.email.templates import send_product_invitation_email
from noctusai_lib.domain.notifications import map_notification_to_pt
from noctusai_lib.primitives.roles import ORG_ROLE_LABELS

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
            .eq("read", False)
            .execute()
        )
        return {"nao_lidas": result.count or 0}

    @router.patch("/{notificacao_id}/ler")
    async def marcar_lida(notificacao_id: str, authorization: Optional[str] = Header(None)):
        user, _ = await deps.get_current_user(authorization)
        core = deps.get_core_client()
        core.table("notifications").update({"read": True}).eq("id", notificacao_id).eq("user_id", str(user.id)).execute()
        return {"ok": True}

    @router.post("/ler-todas")
    async def marcar_todas_lidas(authorization: Optional[str] = Header(None)):
        user, _ = await deps.get_current_user(authorization)
        core = deps.get_core_client()
        core.table("notifications").update({"read": True}).eq("user_id", str(user.id)).eq("read", False).execute()
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
            admin, f"{deps._db.schema}.invitations", email=body["email"], org_id=org_id, role=body.get("role", "member"), invited_by=str(user.id))
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
        result = validate_invitation(admin, f"{deps._db.schema}.invitations", token)
        if not result:
            raise HTTPException(status_code=400, detail="Convite invalido ou expirado")
        return {"data": result}

    @router.post("/accept")
    async def accept_invite(body: dict):
        admin = deps.get_admin_client()
        table = f"{deps._db.schema}.invitations"
        inv = validate_invitation(admin, table, body["token"])
        accept_invitation(admin, table, inv["id"])
        return {"data": inv}

    @router.get("/invitations")
    async def list_invitations(authorization: Optional[str] = Header(None)):
        user, _ = await deps.get_current_user(authorization)
        role = deps.get_user_role(user)
        if role not in ("platform_admin", "owner", "admin"):
            raise HTTPException(status_code=403, detail="Sem permissao")
        org_id = deps.get_org_id(user)
        admin = deps.get_admin_client()
        result = list_pending_invitations(admin, f"{deps._db.schema}.invitations", org_id)
        return {"data": result}

    @router.delete("/invitations/{invitation_id}")
    async def cancel_invite(invitation_id: str, authorization: Optional[str] = Header(None)):
        user, _ = await deps.get_current_user(authorization)
        role = deps.get_user_role(user)
        if role not in ("platform_admin", "owner", "admin"):
            raise HTTPException(status_code=403, detail="Sem permissao")
        admin = deps.get_admin_client()
        cancel_invitation(admin, f"{deps._db.schema}.invitations", invitation_id)
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


def _build_llm_router(deps, settings, product_name: str, version: str) -> APIRouter:
    # Deferred import: llm_router imports `noctusai_lib.llm` and a few catalog
    # modules at collection time; keeping it inside the factory avoids pulling
    # that cost for products that opt out of "llm".
    from noctusai_seed.llm_router import create_llm_router
    return create_llm_router(deps)


def _build_ai_outputs_router(deps, settings, product_name: str, version: str) -> APIRouter:
    # Deferred import for the same reason as `_build_llm_router`.
    from noctusai_seed.ai_router import create_ai_outputs_router
    return create_ai_outputs_router(deps)


def _build_ai_feedback_router(deps, settings, product_name: str, version: str) -> APIRouter:
    # Deferred import — keeps Pydantic model collection cost out of the
    # hot path for products that don't opt in.
    from noctusai_seed.ai_feedback_router import create_ai_feedback_router
    return create_ai_feedback_router(deps)


def _build_scheduler_router(deps, settings, product_name: str, version: str) -> APIRouter:
    # Deferred import — keeps `noctusai_lib.api.scheduler` (which pulls
    # APScheduler at module import time) out of the hot path for
    # products that don't run background jobs.
    from noctusai_seed.scheduler_router import create_scheduler_router
    return create_scheduler_router(deps)


def _build_whatsapp_admin_router(deps, settings, product_name: str, version: str) -> APIRouter:
    # Deferred import — keeps the WhatsApp connector import cost off the
    # hot path for products without a WhatsApp chatbot.
    from noctusai_seed.whatsapp_admin_router import create_whatsapp_admin_router
    return create_whatsapp_admin_router(deps, settings)


def _build_status_paginas_router(deps, settings, product_name: str, version: str) -> APIRouter:
    # Deferred import — mirrors the other `_build_*` factories; keeps the
    # module import off the hot path for products that opt out.
    from noctusai_seed.status_pagina_router import _create_status_pagina_router
    return _create_status_pagina_router(deps, settings, product_name)


# Maintenance contract for _STANDARD_ROUTERS:
# Adding a new standard router requires all three of:
#   (a) adding an entry to this registry,
#   (b) updating `seed/framework/backend/tests/test_build_standard_routers.py
#       ::test_registry_keys_match_documented_set` (drift guard),
#   (c) documenting the new capability in `KNOWLEDGE-BASE/CONTEXT/
#       03-SEED-ARCHITECTURE.md § Standard routers`.
# Miss any of (a)-(c) and the drift-guard test will fail opaquely.
_STANDARD_ROUTERS = {
    "health":       lambda deps, s, n, v: _create_health_router(n, v),
    "notificacoes": lambda deps, s, n, v: _create_notificacoes_router(deps),
    "team":         lambda deps, s, n, v: _create_team_router(deps, s, n),
    "llm":          _build_llm_router,
    "ai_outputs":   _build_ai_outputs_router,
    "ai_feedback":  _build_ai_feedback_router,
    "scheduler":    _build_scheduler_router,
    "whatsapp_admin": _build_whatsapp_admin_router,
    "status_paginas": _build_status_paginas_router,
}


def build_standard_routers(
    deps,
    settings,
    product_name: str,
    version: str,
    names: Sequence[str],
) -> list:
    """Return the subset of standard routers named by `names`.

    Order is preserved: `build_standard_routers(..., names=["llm", "health"])`
    returns `[llm_router, health_router]` in that order. FastAPI's
    `include_router` registration is order-sensitive for overlapping routes —
    products that care can enforce ordering by ordering their opt-in list.

    Raises:
        ValueError: if any name is not in the registry. Error message names
            every unknown key and lists the valid keys for quick fixing.
    """
    unknown = [n for n in names if n not in _STANDARD_ROUTERS]
    if unknown:
        raise ValueError(
            f"Unknown standard router(s): {unknown}. "
            f"Valid: {sorted(_STANDARD_ROUTERS)}"
        )
    return [_STANDARD_ROUTERS[n](deps, settings, product_name, version) for n in names]
