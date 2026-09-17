"""Payment webhook receivers — Stripe + Asaas. Contract §Webhooks,
amendments A4, A5, A9, A11.

Deliberately NOT built on `noctusai_lib.security.webhook_signatures.
webhook_endpoint(...)` (the generic 4-scheme decorator the inherited
`app/routers/webhook_router.py` skeleton uses) — Stripe's signature
scheme is the documented carve-out (`stripe.Webhook.construct_event`)
and Asaas' bare shared-secret token needs its own header-name handling;
both are already implemented, ONE call each, by
`noctusai_lib.integrations.payments.webhook_events.parse_webhook_event`
— reused verbatim here, never re-derived.

`parse_webhook_event` has NO `bypass_when_unset` escape hatch: an unset
secret/token raises `PaymentWebhookSignatureError` unconditionally,
which this router maps to a strict 401 (amendment A9's fail-closed
pin — these are financial webhooks, never an early-dev bypass surface).

Amendment A5's ordering (verify → claim → side effects → release-on-
failure) is split across two files by construction: THIS router owns
"verify" (nothing below runs until `parse_webhook_event` returns
without raising); `app/services/webhooks_service.WebhooksService.handle`
owns "claim → dispatch → release".
"""
import logging

from fastapi import APIRouter, Request

from noctusai_lib.domain.payments import make_event_inbox
from noctusai_lib.integrations.payments.webhook_events import (
    PaymentWebhookSignatureError,
    parse_webhook_event,
)
from noctusai_lib.security.api_keys import resolve_api_key

from app.config import settings
from app.dependencies import http_error, get_admin_client, resolve_public_org_id
from app.rate_limit import limiter
from app.services.webhooks_service import WebhooksService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])

_INBOX_SCHEMA = "community"
_INBOX_TABLE = "webhook_eventos"


async def _receive(gateway: str, request: Request) -> dict:
    body = await request.body()

    # Slice C (user decision 2026-09-17): resolve THIS single-tenant
    # product's org first — `resolve_api_key` needs it to check the
    # org-scoped `community.credentials` override before the platform
    # chain's `settings.stripe_webhook_secret`/`.asaas_webhook_token`
    # env-var fallback (unchanged). A misconfigured deploy (no active
    # license) 503s here rather than accepting an unverifiable webhook.
    org_id = resolve_public_org_id()

    try:
        event = parse_webhook_event(
            body,
            request.headers,
            gateway=gateway,
            stripe_webhook_secret=resolve_api_key("stripe_webhook_secret", str(org_id)) or None,
            asaas_webhook_token=resolve_api_key("asaas_webhook_token", str(org_id)) or None,
        )
    except PaymentWebhookSignatureError as exc:
        logger.warning("webhooks: %s signature verification failed: %s", gateway, exc.detail)
        raise http_error(401, "Assinatura do webhook inválida.") from exc

    client = get_admin_client()
    inbox = make_event_inbox(
        supabase_client=client, schema_name=_INBOX_SCHEMA, table_name=_INBOX_TABLE,
    )
    service = WebhooksService(client, inbox=inbox, org_id=org_id)
    await service.handle(event)
    return {"received": True}


@router.post("/stripe")
@limiter.limit(settings.webhook_rate_limit)
async def stripe_webhook(request: Request) -> dict:
    return await _receive("stripe", request)


@router.post("/asaas")
@limiter.limit(settings.webhook_rate_limit)
async def asaas_webhook(request: Request) -> dict:
    return await _receive("asaas", request)
