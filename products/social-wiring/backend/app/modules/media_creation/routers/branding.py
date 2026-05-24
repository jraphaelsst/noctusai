"""Branding system endpoints — agents (brand owners) + catalog seeding.

Agency model: one org manages many real-estate agents; each agent has 1+
brandings (brand kits with `design_tokens` the SVG render mode consumes).

- GET  /api/media-creation/branding/owners        — list agents + their brandings
- GET  /api/media-creation/branding/owners/{id}   — one agent + its brandings
- POST /api/media-creation/branding/seed-catalog  — idempotently load the repo
  brand catalog into the caller's org (curated brands; safe to re-run)
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from noctusai_lib.primitives.responses import success_response

from app.dependencies import get_admin_client, get_current_user_org, get_org_id
from app.modules.media_creation.branding import load_catalog, seed_catalog
from app.modules.media_creation.services.brand_owner_service import BrandOwnerService

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/media-creation/branding",
    tags=["Media Creation — Branding"],
)


def _svc(user) -> BrandOwnerService:
    return BrandOwnerService(get_admin_client(), get_org_id(user))


@router.get("/owners")
async def list_owners(auth=Depends(get_current_user_org)):
    user, _, _ = auth
    return success_response(_svc(user).list_owners())


@router.get("/owners/{owner_id}")
async def get_owner(owner_id: str, auth=Depends(get_current_user_org)):
    user, _, _ = auth
    owner = _svc(user).get_owner(owner_id)
    if not owner:
        raise HTTPException(status_code=404, detail="Agente não encontrado")
    return success_response(owner)


@router.post("/seed-catalog")
async def seed_catalog_endpoint(auth=Depends(get_current_user_org)):
    """Load the repo brand catalog into the caller's org (idempotent).

    Writes via the service-role client into the caller's own ``org_id``
    (resolved from the token) — curated, version-controlled brands; safe to
    re-run (slug-keyed upsert, never duplicates).
    """
    user, _, _ = auth
    org_id = get_org_id(user)
    owners = load_catalog()
    user_id = getattr(user, "id", None)
    summary = seed_catalog(get_admin_client(), org_id, owners, created_by=user_id)
    logger.info(
        "branding: seeded catalog into org=%s (owners +%d/~%d, brandings +%d/~%d)",
        org_id,
        summary["owners_created"],
        summary["owners_updated"],
        summary["brandings_created"],
        summary["brandings_updated"],
    )
    return success_response(summary)
