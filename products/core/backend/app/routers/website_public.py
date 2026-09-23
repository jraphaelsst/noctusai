"""Public website API — `/api/website/*` (contract §3, "Public").

No auth. Every POST is rate-limited via the core `limiter`; the two
lead-capture / event endpoints never require Turnstile — it is enforced
ONLY when `settings.website_turnstile_secret` is configured (the seed
factory's dev-safe default: `make_turnstile_verifier` returns a Fake that
still rejects an EMPTY token, so a missing submission still 403s even
unconfigured).

NOTE: deliberately NOT `from __future__ import annotations` — combined
with `@limiter.limit(...)` (slowapi's `functools.wraps`-based decorator),
PEP 563 string annotations make FastAPI mis-resolve a Pydantic body model
and `BackgroundTasks` as query parameters (reproduced in isolation; a
platform-wide gotcha, not code-review paranoia — see this file's
`drift-found:` footer). Every other rate-limited router in this codebase
(`auth.py`, `billing.py`, `team.py`, ...) already avoids the future import
for the same reason, just never documented.
"""
import json
import logging
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response, status

from app.config import settings
from app.database import get_admin_client
from app.rate_limit import limiter
from app.schemas.website import WebsiteEventCreate, WebsiteLeadCreate
from app.services import website_leads_service, website_settings_service
from app.services.website_lead_fanout import run_fanout
from noctusai_lib.integrations.turnstile import make_turnstile_verifier

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/website", tags=["Website (public)"])

_MAX_EVENT_PROPS_BYTES = 2048


def _client_ip(request: Request) -> Optional[str]:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


async def _verify_turnstile(token: Optional[str], request: Request) -> None:
    secret = settings.website_turnstile_secret
    if not secret:
        return  # not configured — the whole gate is opt-in (contract §3)
    verifier = make_turnstile_verifier(secret=secret)
    result = await verifier.verify(token or "", remote_ip=_client_ip(request))
    if not result.success:
        # `{"detail": <code>, "code": <code>}` is the seed's escape hatch
        # (`noctusai_lib.primitives.exceptions.http_exception_handler`) for
        # a caller that needs the LITERAL `{"detail": "..."}` shape the
        # contract specifies — the platform's historical default instead
        # wraps every HTTPException as `{"error": {"code", "message"}}`.
        raise HTTPException(status_code=403, detail={"detail": "turnstile_failed", "code": "turnstile_failed"})


def _whatsapp_url(public_settings: dict, locale: str) -> Optional[str]:
    whatsapp = public_settings.get("whatsapp") or {}
    number = whatsapp.get("number_e164")
    if not number:
        return None
    message = (whatsapp.get("default_message") or {}).get(locale) or ""
    digits = number.lstrip("+")
    return f"https://wa.me/{digits}?text={quote(message)}"


@router.get("/settings")
async def get_public_settings():
    version, data = website_settings_service.get_current()
    return {"data": website_settings_service.public_subset(data), "version": version}


@router.get("/plans")
async def get_public_plans():
    db = get_admin_client()
    result = (
        db.table("plans")
        .select("id, slug, nome, descricao, price_monthly, price_yearly, max_users, max_products, features, is_custom")
        .eq("ativo", True)
        .order("price_monthly")
        .execute()
    )
    return {"data": result.data or []}


@router.post("/leads", status_code=201)
@limiter.limit("10/minute")
async def create_lead(request: Request, body: WebsiteLeadCreate, background_tasks: BackgroundTasks):
    await _verify_turnstile(body.turnstile_token, request)

    try:
        lead, _created = website_leads_service.create_or_merge_lead(
            body, ip_hash=website_leads_service.hash_ip(_client_ip(request))
        )
    except website_leads_service.WebsiteLeadContactMissing as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    background_tasks.add_task(run_fanout, lead)

    _, current_settings = website_settings_service.get_current()
    public_data = website_settings_service.public_subset(current_settings)
    whatsapp_url = _whatsapp_url(public_data, body.locale)
    return {"data": {"id": lead["id"], "whatsapp_url": whatsapp_url}}


@router.post("/events", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("60/minute")
async def create_event(request: Request, body: WebsiteEventCreate):
    props = body.props or {}
    if len(json.dumps(props, ensure_ascii=False).encode("utf-8")) > _MAX_EVENT_PROPS_BYTES:
        raise HTTPException(status_code=422, detail="props exceeds 2KB")

    db = get_admin_client()
    db.table("website_events").insert({
        "anon_id": body.anon_id,
        "session_id": body.session_id,
        "event": body.event,
        "path": body.path,
        "props": props,
    }).execute()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
