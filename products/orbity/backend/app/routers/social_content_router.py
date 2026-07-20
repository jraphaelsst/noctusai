"""
Social/Content Studio router — campaigns, posts, approvals (authed CRUD)
and the public client-approval flow.

Auth boundary:
  - All /api/content/* → Depends(get_current_user_org) → strict 401
  - GET  /api/content/approve/{token} → PUBLIC (unauthenticated) — token IS auth
  - POST /api/content/approve/{token} → PUBLIC (unauthenticated) — token IS auth

The public approve endpoints mirror capture_router: they use the admin
(service_role) client, so RLS is bypassed. Security is: token must exist,
not be expired, not already decided. No client-supplied org_id is ever trusted.

Endpoints:
  GET    /api/content/campaigns                       list campaigns
  POST   /api/content/campaigns                       create campaign → 201
  GET    /api/content/campaigns/{id}                  campaign detail
  PATCH  /api/content/campaigns/{id}                  update campaign
  DELETE /api/content/campaigns/{id}                  delete campaign

  GET    /api/content/posts                           list posts
  POST   /api/content/posts                           create post → 201
  GET    /api/content/posts/{id}                      post detail
  PATCH  /api/content/posts/{id}                      update post
  DELETE /api/content/posts/{id}                      delete post

  GET    /api/content/posts/{post_id}/approvals       list approvals for post
  POST   /api/content/posts/{post_id}/approvals       create approval link → 201
  GET    /api/content/approvals                       list all approvals (org-wide)
  GET    /api/content/approvals/{id}                  approval detail

  GET    /api/content/approve/{token}                 PUBLIC — fetch post for client
  POST   /api/content/approve/{token}                 PUBLIC — submit decision
"""
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.dependencies import (
    coerce_org_uuid,
    get_admin_client,
    get_current_user_org,
    get_user_client,
)
from app.schemas.social_content import (
    ApprovalCreate,
    ApprovalDecision,
    ApprovalOut,
    CampaignCreate,
    CampaignOut,
    CampaignUpdate,
    PostCreate,
    PostOut,
    PostUpdate,
    PublicApprovalView,
)
from app.services.social_content_service import PublicApprovalService, SocialContentService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Social/Content"])
approve_router = APIRouter(tags=["Content Approval"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _svc(token: str, org_id) -> SocialContentService:
    return SocialContentService(get_user_client(token), org_id=org_id)


def _admin_approval_svc() -> PublicApprovalService:
    """Public approval service backed by the admin (service_role) client.

    Mirrors _admin_crm() in crm_router — service_role bypasses RLS for the
    public approve path. Security guarantee is entirely at the token level.
    """
    return PublicApprovalService(get_admin_client())


# ---------------------------------------------------------------------------
# Campaigns
# ---------------------------------------------------------------------------

@router.get("/api/content/campaigns", status_code=status.HTTP_200_OK)
async def list_campaigns(
    client_id: str | None = Query(default=None),
    month: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    auth: tuple = Depends(get_current_user_org),
) -> dict:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        return _svc(token, org_id).list_campaigns(
            client_id=client_id,
            month=month,
            status=status_filter,
            page=page,
            page_size=page_size,
        )
    except Exception:
        logger.exception("content.list_campaigns failed org=%s", org_id)
        raise HTTPException(status_code=502, detail="Falha ao listar campanhas")


@router.post(
    "/api/content/campaigns",
    response_model=CampaignOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_campaign(
    payload: CampaignCreate,
    auth: tuple = Depends(get_current_user_org),
) -> CampaignOut:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        row = _svc(token, org_id).create_campaign(
            payload.model_dump(exclude_none=True)
        )
    except Exception:
        logger.exception("content.create_campaign failed org=%s", org_id)
        raise HTTPException(status_code=502, detail="Falha ao criar campanha")
    return CampaignOut(**row)


@router.get(
    "/api/content/campaigns/{campaign_id}",
    response_model=CampaignOut,
    status_code=status.HTTP_200_OK,
)
async def get_campaign(
    campaign_id: str,
    auth: tuple = Depends(get_current_user_org),
) -> CampaignOut:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        row = _svc(token, org_id).get_campaign(campaign_id)
    except Exception:
        logger.exception("content.get_campaign failed org=%s id=%s", org_id, campaign_id)
        raise HTTPException(status_code=502, detail="Falha ao buscar campanha")
    if not row:
        raise HTTPException(status_code=404, detail="Campanha não encontrada")
    return CampaignOut(**row)


@router.patch(
    "/api/content/campaigns/{campaign_id}",
    response_model=CampaignOut,
    status_code=status.HTTP_200_OK,
)
async def update_campaign(
    campaign_id: str,
    payload: CampaignUpdate,
    auth: tuple = Depends(get_current_user_org),
) -> CampaignOut:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    data = payload.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")
    try:
        row = _svc(token, org_id).update_campaign(campaign_id, data)
    except Exception:
        logger.exception("content.update_campaign failed org=%s id=%s", org_id, campaign_id)
        raise HTTPException(status_code=502, detail="Falha ao atualizar campanha")
    if not row:
        raise HTTPException(status_code=404, detail="Campanha não encontrada")
    return CampaignOut(**row)


@router.delete("/api/content/campaigns/{campaign_id}", status_code=status.HTTP_200_OK)
async def delete_campaign(
    campaign_id: str,
    auth: tuple = Depends(get_current_user_org),
) -> dict:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        ok = _svc(token, org_id).delete_campaign(campaign_id)
    except Exception:
        logger.exception("content.delete_campaign failed org=%s id=%s", org_id, campaign_id)
        raise HTTPException(status_code=502, detail="Falha ao deletar campanha")
    if not ok:
        raise HTTPException(status_code=404, detail="Campanha não encontrada")
    return {"ok": True, "id": campaign_id}


# ---------------------------------------------------------------------------
# Posts
# ---------------------------------------------------------------------------

@router.get("/api/content/posts", status_code=status.HTTP_200_OK)
async def list_posts(
    campaign_id: str | None = Query(default=None),
    client_id: str | None = Query(default=None),
    platform: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    auth: tuple = Depends(get_current_user_org),
) -> dict:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        return _svc(token, org_id).list_posts(
            campaign_id=campaign_id,
            client_id=client_id,
            platform=platform,
            status=status_filter,
            page=page,
            page_size=page_size,
        )
    except Exception:
        logger.exception("content.list_posts failed org=%s", org_id)
        raise HTTPException(status_code=502, detail="Falha ao listar posts")


@router.post(
    "/api/content/posts",
    response_model=PostOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_post(
    payload: PostCreate,
    auth: tuple = Depends(get_current_user_org),
) -> PostOut:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        row = _svc(token, org_id).create_post(
            payload.model_dump(exclude_none=True)
        )
    except Exception:
        logger.exception("content.create_post failed org=%s", org_id)
        raise HTTPException(status_code=502, detail="Falha ao criar post")
    return PostOut(**row)


@router.get(
    "/api/content/posts/{post_id}",
    response_model=PostOut,
    status_code=status.HTTP_200_OK,
)
async def get_post(
    post_id: str,
    auth: tuple = Depends(get_current_user_org),
) -> PostOut:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        row = _svc(token, org_id).get_post(post_id)
    except Exception:
        logger.exception("content.get_post failed org=%s id=%s", org_id, post_id)
        raise HTTPException(status_code=502, detail="Falha ao buscar post")
    if not row:
        raise HTTPException(status_code=404, detail="Post não encontrado")
    return PostOut(**row)


@router.patch(
    "/api/content/posts/{post_id}",
    response_model=PostOut,
    status_code=status.HTTP_200_OK,
)
async def update_post(
    post_id: str,
    payload: PostUpdate,
    auth: tuple = Depends(get_current_user_org),
) -> PostOut:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    data = payload.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")
    try:
        row = _svc(token, org_id).update_post(post_id, data)
    except Exception:
        logger.exception("content.update_post failed org=%s id=%s", org_id, post_id)
        raise HTTPException(status_code=502, detail="Falha ao atualizar post")
    if not row:
        raise HTTPException(status_code=404, detail="Post não encontrado")
    return PostOut(**row)


@router.delete("/api/content/posts/{post_id}", status_code=status.HTTP_200_OK)
async def delete_post(
    post_id: str,
    auth: tuple = Depends(get_current_user_org),
) -> dict:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        ok = _svc(token, org_id).delete_post(post_id)
    except Exception:
        logger.exception("content.delete_post failed org=%s id=%s", org_id, post_id)
        raise HTTPException(status_code=502, detail="Falha ao deletar post")
    if not ok:
        raise HTTPException(status_code=404, detail="Post não encontrado")
    return {"ok": True, "id": post_id}


# ---------------------------------------------------------------------------
# Approvals — authed side
# ---------------------------------------------------------------------------

@router.post(
    "/api/content/posts/{post_id}/approvals",
    response_model=ApprovalOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_approval(
    post_id: str,
    payload: ApprovalCreate,
    auth: tuple = Depends(get_current_user_org),
) -> ApprovalOut:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        row = _svc(token, org_id).create_approval(
            post_id, expires_in_days=payload.expires_in_days
        )
    except Exception:
        logger.exception(
            "content.create_approval failed org=%s post=%s", org_id, post_id
        )
        raise HTTPException(status_code=502, detail="Falha ao criar link de aprovação")
    return ApprovalOut(**row)


@router.get(
    "/api/content/posts/{post_id}/approvals",
    status_code=status.HTTP_200_OK,
)
async def list_post_approvals(
    post_id: str,
    auth: tuple = Depends(get_current_user_org),
) -> list:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        return _svc(token, org_id).list_approvals(post_id=post_id)
    except Exception:
        logger.exception(
            "content.list_post_approvals failed org=%s post=%s", org_id, post_id
        )
        raise HTTPException(status_code=502, detail="Falha ao listar aprovações")


@router.get("/api/content/approvals", status_code=status.HTTP_200_OK)
async def list_approvals(
    post_id: str | None = Query(default=None),
    auth: tuple = Depends(get_current_user_org),
) -> list:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        return _svc(token, org_id).list_approvals(post_id=post_id)
    except Exception:
        logger.exception("content.list_approvals failed org=%s", org_id)
        raise HTTPException(status_code=502, detail="Falha ao listar aprovações")


@router.get(
    "/api/content/approvals/{approval_id}",
    response_model=ApprovalOut,
    status_code=status.HTTP_200_OK,
)
async def get_approval(
    approval_id: str,
    auth: tuple = Depends(get_current_user_org),
) -> ApprovalOut:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        row = _svc(token, org_id).get_approval(approval_id)
    except Exception:
        logger.exception(
            "content.get_approval failed org=%s id=%s", org_id, approval_id
        )
        raise HTTPException(status_code=502, detail="Falha ao buscar aprovação")
    if not row:
        raise HTTPException(status_code=404, detail="Aprovação não encontrada")
    return ApprovalOut(**row)


# ---------------------------------------------------------------------------
# Public approval endpoints (unauthenticated — token-gated)
# ---------------------------------------------------------------------------

@approve_router.get(
    "/api/content/approve/{token}",
    response_model=PublicApprovalView,
    status_code=status.HTTP_200_OK,
)
async def public_get_approval(token: str) -> PublicApprovalView:
    """Public — fetch the post for the client via approval token.

    No auth required. Returns a safe PublicApprovalView (no org_id).
    Returns 404 if token not found or malformed. Returns 410 if expired.

    A malformed token (not a valid UUID) is validated away before the DB
    round-trip — same non-guessable-link-is-404 reasoning as reports_router
    (avoids postgres 22P02 being misreported as 502).
    """
    not_found_detail = "Link de aprovação não encontrado"

    try:
        UUID(token)
    except ValueError:
        raise HTTPException(status_code=404, detail=not_found_detail)

    svc = _admin_approval_svc()
    try:
        pair = svc.fetch_by_token(token)
    except ValueError as exc:
        logger.info("public_get_approval: token expired or invalid token=%s", token)
        raise HTTPException(status_code=410, detail=str(exc))
    except Exception:
        logger.exception("public_get_approval failed token=%s", token)
        raise HTTPException(status_code=502, detail="Falha ao buscar aprovação")
    if pair is None:
        raise HTTPException(status_code=404, detail=not_found_detail)
    approval, post = pair
    return PublicApprovalView(
        approval_id=approval["id"],
        post_id=post["id"],
        platform=post["platform"],
        caption=post.get("caption"),
        hashtags=post.get("hashtags"),
        media_url=post.get("media_url"),
        scheduled_for=post.get("scheduled_for"),
        approval_status=approval["status"],
        expires_at=approval["expires_at"],
    )


@approve_router.post(
    "/api/content/approve/{token}",
    status_code=status.HTTP_200_OK,
)
async def public_submit_approval(
    token: str,
    payload: ApprovalDecision,
) -> dict:
    """Public — submit client decision (approved|revision) via token.

    No auth required. Token IS the authorization.
    Returns 404 if token not found or malformed. Returns 410 if expired or
    already decided.
    """
    try:
        UUID(token)
    except ValueError:
        raise HTTPException(status_code=404, detail="Approval token not found")

    svc = _admin_approval_svc()
    try:
        updated = svc.decide(token, payload.decision, feedback=payload.feedback)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=410, detail=str(exc))
    except Exception:
        logger.exception("public_submit_approval failed token=%s", token)
        raise HTTPException(status_code=502, detail="Falha ao registrar decisão")
    return {"ok": True, "approval_id": updated.get("id"), "status": updated.get("status")}
