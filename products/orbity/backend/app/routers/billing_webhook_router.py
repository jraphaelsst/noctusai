"""Payment-gateway webhook -- ``POST /api/billing/webhook/asaas/{org_id}``.

Register this URL (with the org's id) in the org's Asaas account, "Webhooks", and give Asaas the same token that is stored
as the org credential ``asaas_webhook_token``. Unauthenticated by nature (Asaas calls it); protections: the per-org token
(constant-time compare, FAIL CLOSED when the org has none), the durable event inbox (a redelivery is a no-op, a handler that
crashes RELEASES the claim so Asaas' retry is not swallowed), and a slowapi rate limit.
"""
# No `from __future__ import annotations`: slowapi's @limiter.limit inspects the endpoint signature at runtime and
# breaks on PEP 563 string annotations (repo check check_slowapi_with_pep563).

import logging
from uuid import UUID

import anyio
from fastapi import APIRouter, HTTPException, Request, status
from noctusai_lib.domain.payments import make_event_inbox
from noctusai_lib.integrations.payments.webhook_events import PaymentWebhookSignatureError, parse_webhook_event

from app.billing import platform_resolve
from app.dependencies import get_admin_client
from app.rate_limit import limiter
from app.services.billing_webhook import apply_event

logger = logging.getLogger(__name__)

router = APIRouter(tags=["billing-webhook"])

INBOX_TABLE = "payment_gateway_events"
TOKEN_CREDENTIAL = "asaas_webhook_token"


@router.post("/api/billing/webhook/asaas/{org_id}")
@limiter.limit("300/minute")
async def asaas_webhook(request: Request, org_id: UUID) -> dict:
    org = str(org_id)
    token = platform_resolve(TOKEN_CREDENTIAL, org)
    if not token:
        # Fail closed: an org that never configured the token accepts NOTHING (not even a "valid-looking" delivery).
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Webhook não configurado.")
    body = await request.body()
    try:
        event = parse_webhook_event(body, request.headers, gateway="asaas", asaas_webhook_token=token)
    except PaymentWebhookSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Assinatura inválida.")
    db = get_admin_client()
    # ``get_admin_client()`` is ALREADY pinned to the orbity schema (never re-scope it with ``.schema()``): the inbox's
    # ``schema_name="public"`` means "use ``client.table(...)`` as-is", i.e. ``orbity.payment_gateway_events`` here.
    inbox = make_event_inbox(supabase_client=db, schema_name="public", table_name=INBOX_TABLE)
    gateway, event_id = event.inbox_key
    if not inbox.claim(gateway=gateway, event_id=event_id):
        return {"status": "duplicate"}
    try:
        return await anyio.to_thread.run_sync(lambda: apply_event(db, org, event))
    except Exception:
        inbox.release(gateway=gateway, event_id=event_id)  # let Asaas redeliver
        logger.exception("billing webhook: applying %s failed org=%s", event_id, org)
        raise HTTPException(status_code=500, detail="Falha ao processar o evento.")
