"""Public double opt-in confirmation — no auth; the signed token IS the credential.

``GET  /api/email-marketing/confirm/{token}`` → ``{email, valid}`` (the page shows
the address before the visitor confirms).
``POST /api/email-marketing/confirm/{token}`` → ``email_optin='confirmed'`` +
``email_confirmed_at``; a replay answers ``{ok: true, already: true}``.
Only an unexpired ``email_confirm`` token verifies (P1b(d), 2026-10-10): a forged,
expired, unsubscribe or click token → 400.
"""
# NO `from __future__ import annotations` — slowapi's @limiter.limit resolves the
# endpoint signature at runtime (keeper `check_slowapi_with_pep563`).
import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from app.config import settings
from app.dependencies import get_admin_client, get_settings
from app.modules.email_marketing.services.contact_service import ContactService
from app.modules.email_marketing.services.email_optin import verify_token
from app.rate_limit import limiter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/email-marketing/confirm", tags=["Double opt-in"])

INVALID = "Link de confirmação inválido ou expirado"


def _verified(cfg, token: str) -> dict:
    data = verify_token(cfg.jwt_secret, token)
    if not data:
        raise HTTPException(status_code=400, detail=INVALID)
    return data


@router.get("/{token}")
@limiter.limit(settings.webhook_rate_limit)
async def confirmation_info(request: Request, token: str, cfg=Depends(get_settings)):
    data = _verified(cfg, token)
    return {"email": data["email"], "valid": True}


@router.post("/{token}")
@limiter.limit(settings.webhook_rate_limit)
async def confirm_email(request: Request, token: str, cfg=Depends(get_settings)):
    data = _verified(cfg, token)
    outcome = ContactService(get_admin_client(), data["org_id"]).confirm_email(
        data["contact_id"], data["email"],
    )
    if outcome == "not_found":
        raise HTTPException(status_code=404, detail="Contato não encontrado")
    if outcome == "mismatch":
        # The contact's address changed after this link was minted: confirming
        # it would opt in an address that never clicked.
        raise HTTPException(status_code=400, detail=INVALID)
    if outcome == "already":
        return {"ok": True, "already": True, "email": data["email"]}
    logger.info("double opt-in: contact %s confirmed (org=%s)", data["contact_id"], data["org_id"])
    return {"ok": True, "email": data["email"], "message": "E-mail confirmado com sucesso"}
