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
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from noctusai_lib.api.rate_limit import client_ip_key

from app.dependencies import (
    coerce_org_uuid,
    get_admin_client,
    get_core_client,
    get_current_user_org,
    get_org_client,
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
from noctusai_lib.api.access_tiers import access_tier
from noctusai_lib.api.token_link import TokenLinkGone, TokenLinkNotFound, resolve_token_link, token_fingerprint

from app.rate_limit import limiter
from app.services.social_content_service import PublicApprovalService, SocialContentService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Social/Content"])
approve_router = APIRouter(tags=["Content Approval"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _svc(token: str, org_id) -> SocialContentService:
    return SocialContentService(get_org_client(org_id), org_id=org_id)


def _admin_approval_svc() -> PublicApprovalService:
    """Public approval service backed by the admin (service_role) client.

    Mirrors _admin_crm() in crm_router — service_role bypasses RLS for the
    public approve path. Security guarantee is entirely at the token level.
    """
    return PublicApprovalService(get_admin_client(), core_db=get_core_client())  # org-scope-ok: public token link, org derived from the token row


# ---------------------------------------------------------------------------
# Campaigns
# ---------------------------------------------------------------------------

@router.get("/api/content/campaigns", status_code=status.HTTP_200_OK)
def list_campaigns(
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
    except HTTPException:
        raise
    except Exception:
        logger.exception("content.list_campaigns failed org=%s", org_id)
        raise HTTPException(status_code=502, detail="Falha ao listar campanhas")


@router.post(
    "/api/content/campaigns",
    response_model=CampaignOut,
    status_code=status.HTTP_201_CREATED,
)
def create_campaign(
    payload: CampaignCreate,
    auth: tuple = Depends(get_current_user_org),
) -> CampaignOut:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        row = _svc(token, org_id).create_campaign(
            payload.model_dump(mode="json", exclude_none=True)
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("content.create_campaign failed org=%s", org_id)
        raise HTTPException(status_code=502, detail="Falha ao criar campanha")
    return CampaignOut(**row)


@router.get(
    "/api/content/campaigns/{campaign_id}",
    response_model=CampaignOut,
    status_code=status.HTTP_200_OK,
)
def get_campaign(
    campaign_id: str,
    auth: tuple = Depends(get_current_user_org),
) -> CampaignOut:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        row = _svc(token, org_id).get_campaign(campaign_id)
    except HTTPException:
        raise
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
def update_campaign(
    campaign_id: str,
    payload: CampaignUpdate,
    auth: tuple = Depends(get_current_user_org),
) -> CampaignOut:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    data = payload.model_dump(mode="json", exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")
    try:
        row = _svc(token, org_id).update_campaign(campaign_id, data)
    except HTTPException:
        raise
    except Exception:
        logger.exception("content.update_campaign failed org=%s id=%s", org_id, campaign_id)
        raise HTTPException(status_code=502, detail="Falha ao atualizar campanha")
    if not row:
        raise HTTPException(status_code=404, detail="Campanha não encontrada")
    return CampaignOut(**row)


@router.delete("/api/content/campaigns/{campaign_id}", status_code=status.HTTP_200_OK)
def delete_campaign(
    campaign_id: str,
    auth: tuple = Depends(get_current_user_org),
) -> dict:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        ok = _svc(token, org_id).delete_campaign(campaign_id)
    except HTTPException:
        raise
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
def list_posts(
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
    except HTTPException:
        raise
    except Exception:
        logger.exception("content.list_posts failed org=%s", org_id)
        raise HTTPException(status_code=502, detail="Falha ao listar posts")


@router.post(
    "/api/content/posts",
    response_model=PostOut,
    status_code=status.HTTP_201_CREATED,
)
def create_post(
    payload: PostCreate,
    auth: tuple = Depends(get_current_user_org),
) -> PostOut:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        row = _svc(token, org_id).create_post(
            payload.model_dump(mode="json", exclude_none=True)
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("content.create_post failed org=%s", org_id)
        raise HTTPException(status_code=502, detail="Falha ao criar post")
    return PostOut(**row)


@router.get(
    "/api/content/posts/{post_id}",
    response_model=PostOut,
    status_code=status.HTTP_200_OK,
)
def get_post(
    post_id: str,
    auth: tuple = Depends(get_current_user_org),
) -> PostOut:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        row = _svc(token, org_id).get_post(post_id)
    except HTTPException:
        raise
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
def update_post(
    post_id: str,
    payload: PostUpdate,
    auth: tuple = Depends(get_current_user_org),
) -> PostOut:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    data = payload.model_dump(mode="json", exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")
    try:
        row = _svc(token, org_id).update_post(post_id, data)
    except HTTPException:
        raise
    except Exception:
        logger.exception("content.update_post failed org=%s id=%s", org_id, post_id)
        raise HTTPException(status_code=502, detail="Falha ao atualizar post")
    if not row:
        raise HTTPException(status_code=404, detail="Post não encontrado")
    return PostOut(**row)


@router.delete("/api/content/posts/{post_id}", status_code=status.HTTP_200_OK)
def delete_post(
    post_id: str,
    auth: tuple = Depends(get_current_user_org),
) -> dict:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        ok = _svc(token, org_id).delete_post(post_id)
    except HTTPException:
        raise
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
def create_approval(
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
    except HTTPException:
        raise
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
def list_post_approvals(
    post_id: str,
    auth: tuple = Depends(get_current_user_org),
) -> list:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        return _svc(token, org_id).list_approvals(post_id=post_id)
    except HTTPException:
        raise
    except Exception:
        logger.exception(
            "content.list_post_approvals failed org=%s post=%s", org_id, post_id
        )
        raise HTTPException(status_code=502, detail="Falha ao listar aprovações")


@router.get("/api/content/approvals", status_code=status.HTTP_200_OK)
def list_approvals(
    post_id: str | None = Query(default=None),
    auth: tuple = Depends(get_current_user_org),
) -> list:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        return _svc(token, org_id).list_approvals(post_id=post_id)
    except HTTPException:
        raise
    except Exception:
        logger.exception("content.list_approvals failed org=%s", org_id)
        raise HTTPException(status_code=502, detail="Falha ao listar aprovações")


@router.get(
    "/api/content/approvals/{approval_id}",
    response_model=ApprovalOut,
    status_code=status.HTTP_200_OK,
)
def get_approval(
    approval_id: str,
    auth: tuple = Depends(get_current_user_org),
) -> ApprovalOut:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        row = _svc(token, org_id).get_approval(approval_id)
    except HTTPException:
        raise
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
@access_tier("public", reason="client approval link: unguessable token, server-checked expiry (fails closed), org-scoped reads, no internal ids returned", category="token-link")
# shared_limit(scope=) pins the bucket: slowapi's default scope is the request PATH, which here contains the token -- every guess would get a
# fresh bucket and the limit would never trip.
@limiter.shared_limit("30/minute;300/hour", scope="approve-get", key_func=client_ip_key)
def public_get_approval(request: Request, token: str) -> PublicApprovalView:
    """Public -- the post for the client behind an approval link (``token-link`` tier).

    The token is resolved ONLY through ``resolve_token_link``: a malformed or unknown token is 404, an expired one 410
    (a missing/unparsable expiry counts as expired). The response is an explicit public view with no internal ids."""
    svc = _admin_approval_svc()
    try:
        approval = resolve_token_link(token, svc.fetch_approval_row)
        post = svc.post_of(approval)
    except TokenLinkNotFound:
        raise HTTPException(status_code=404, detail="Link de aprovação não encontrado")
    except TokenLinkGone:
        raise HTTPException(status_code=410, detail="Link de aprovação expirado")
    except HTTPException:
        raise
    except Exception:
        logger.exception("public_get_approval failed %s", token_fingerprint(token))
        raise HTTPException(status_code=502, detail="Falha ao buscar aprovação")
    if post is None:
        raise HTTPException(status_code=404, detail="Link de aprovação não encontrado")
    return PublicApprovalView(
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
@access_tier("public", reason="client approval link: one-time decision (UPDATE ... status='pending'), expiry fails closed, org-scoped writes", category="token-link")
@limiter.shared_limit("10/minute;60/hour", scope="approve-post", key_func=client_ip_key)
def public_submit_approval(
    request: Request,  # required positionally by @limiter.limit (slowapi)
    token: str,
    payload: ApprovalDecision,
) -> dict:
    """Public -- the client's decision (approved|revision) via the approval link (``token-link`` tier).

    404 for a malformed/unknown token, 410 for an expired or already-decided link (one-time use)."""
    svc = _admin_approval_svc()
    try:
        approval = resolve_token_link(token, svc.fetch_approval_row)
        if approval.get("status") != "pending":
            raise TokenLinkGone("already decided")
        updated = svc.decide(approval, payload.decision, feedback=payload.feedback)
    except (TokenLinkNotFound, LookupError):
        raise HTTPException(status_code=404, detail="Approval token not found")
    except TokenLinkGone:
        raise HTTPException(status_code=410, detail="Link de aprovação expirado ou já respondido")
    except HTTPException:
        raise
    except Exception:
        logger.exception("public_submit_approval failed %s", token_fingerprint(token))
        raise HTTPException(status_code=502, detail="Falha ao registrar decisão")
    return {"ok": True, "status": updated.get("status"), "team_notified": updated.get("team_notified", 0)}
