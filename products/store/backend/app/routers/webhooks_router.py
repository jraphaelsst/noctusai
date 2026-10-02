"""Asaas webhook receiver — `POST /api/webhooks/asaas`. Contract §3.

The webhook 5-pin compliance contract
(`KB § PATTERNS/security/webhook-signatures.md`), Asaas flavour:

1. VERIFY via the seed (`parse_webhook_event`, constant-time token compare) —
   never a hand-rolled compare. Verification runs BEFORE any DB work.
2. Secret resolved PER REQUEST (`get_asaas_webhook_token`), never captured at import.
3. Fail-closed: `parse_webhook_event` has no bypass — an unset token is a
   401, not an early-dev pass (a financial webhook is never an open door).
4. `@limiter.limit(settings.webhook_rate_limit)` — the only throttle on an
   unauthenticated surface.
5. Status-code-pinned tests (tests/routers/test_webhooks_router.py).

Always 200 for an event we verified but do not act on — webhooks retry
forever on a non-2xx.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from noctusai_lib.integrations.payments.webhook_events import PaymentWebhookSignatureError, parse_webhook_event

from app.config import settings
from app.rate_limit import limiter
from app.services.webhook_service import WebhookService
from app.store_deps import get_asaas_webhook_token, get_webhook_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


@router.post("/asaas")
@limiter.limit(settings.webhook_rate_limit)
async def asaas_webhook(
    request: Request,
    token: str = Depends(get_asaas_webhook_token),
    service: WebhookService = Depends(get_webhook_service),
) -> dict:
    body = await request.body()
    try:
        event = parse_webhook_event(body, request.headers, gateway="asaas", asaas_webhook_token=token or None)
    except PaymentWebhookSignatureError as exc:
        logger.warning("webhooks: asaas verification failed: %s", getattr(exc, "detail", exc))
        raise HTTPException(status_code=401, detail="Assinatura do webhook inválida.") from exc
    outcome = await service.handle(event)
    return {"received": True, "outcome": outcome}


__all__ = ["router"]
