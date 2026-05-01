"""User-facing AI consent endpoints — Phase 19 (X6 / LGPD).

  - GET  /api/me/consents       → catalog merged with caller's decisions.
  - PUT  /api/me/consents/{key} → upsert grant/revoke.

The catalog is the platform-wide registry of consent-gated AI features
(`noctusai_lib.ai.consent.get_catalog()`). Products register their
features at import-time; this router is a thin auth + read/write layer.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from noctusai_lib.domain.ai.consent import (
    get_feature,
    list_user_consent_view,
    pending_count,
    upsert_decision,
)

from app.dependencies import get_current_user, get_org_id, get_user_client

logger = logging.getLogger(__name__)
router = APIRouter(tags=["AI Consent"])


class ConsentToggle(BaseModel):
    granted: bool


@router.get("/api/me/consents")
async def list_my_consents(authorization: Optional[str] = Header(None)):
    """Return the consent catalog merged with the caller's decisions plus
    a `pending` count (for `LayoutEnrichment.aiBadge`)."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)
    view = await list_user_consent_view(db, str(user.id))
    return {"data": {"items": view, "pending": pending_count(view)}}


@router.put("/api/me/consents/{feature_key}")
async def upsert_my_consent(
    feature_key: str,
    body: ConsentToggle,
    authorization: Optional[str] = Header(None),
):
    """Grant or revoke consent for a single feature."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)
    feature = get_feature(feature_key)
    if feature is None:
        raise HTTPException(
            status_code=404,
            detail=f"Recurso de IA não registrado no catálogo: {feature_key}",
        )
    if not feature.toggleable:
        # Infrastructure-tier features are visible in the catalog for billing
        # transparency but cannot be toggled by users. The lib also raises
        # MandatoryFeatureCannotBeToggled defensively if reached.
        raise HTTPException(
            status_code=403,
            detail=(
                f"Este recurso de IA ({feature.title}) é infraestrutura "
                f"essencial e não pode ser desativado individualmente."
            ),
        )
    org_id: Optional[str] = None
    try:
        org_id = await get_org_id(user)
    except Exception as exc:
        # Personal-context features may have no org — that's OK.
        logger.debug("me_consents: get_org_id returned no org for user=%s (%s); proceeding with org_id=None", user.id, exc)
    try:
        row = await upsert_decision(
            db, str(user.id), feature_key, granted=body.granted, org_id=org_id
        )
    except Exception as e:
        logger.error("me_consents.upsert failed for user=%s key=%s: %s", user.id, feature_key, e)
        raise HTTPException(status_code=500, detail="Erro ao salvar preferência")
    return {"data": row}
