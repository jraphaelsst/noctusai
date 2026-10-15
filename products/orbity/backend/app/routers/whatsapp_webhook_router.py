"""Per-connection inbound WAHA webhook — `POST /api/whatsapp/webhook/{token}`.

The URL the `whatsapp_connections_router` mints for each connection. The opaque
`token` resolves the connection (hence the ORG) via `resolve_by_webhook_token`;
the message is then handed to `whatsapp_inbound.process_inbound`, which emits
`whatsapp_message_received` / `keyword_received` for KNOWN leads only (see that
module for the conservative-by-design rules).

Auth model: unauthenticated by nature (WAHA calls it). Protections: unknown
token -> generic 404 (no enumeration, token never logged); optional fail-closed
HMAC (`settings.waha_webhook_hmac_secret`, unset => unsigned accepted, early-dev
only — same posture as community); slowapi rate limit; in-memory dedup (the
DB-level `trigger_key` makes redelivery idempotent regardless).
"""
# No `from __future__ import annotations`: slowapi's @limiter.limit inspects the
# endpoint signature at runtime and breaks on PEP 563 string annotations
# (repo check check_slowapi_with_pep563).

import logging

import anyio
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status

from noctusai_lib.integrations.whatsapp import (
    WhatsAppIgnoredEvent,
    WhatsAppPayloadError,
    build_whatsapp_connection_store,
    get_webhook_dedup,
    parse_waha_inbound_message,
    resolve_by_webhook_token,
)
from noctusai_lib.security.api_keys import EncryptionNotConfigured
from noctusai_lib.security.webhook_signatures import verify_hmac_sha256_hex

from app.config import settings
from app.dependencies import get_admin_client
from app.rate_limit import limiter
from app.services.whatsapp_inbound import process_inbound

logger = logging.getLogger(__name__)

router = APIRouter(tags=["whatsapp-webhook"])

_dedup = get_webhook_dedup(redis_client=None)


def _store_dep():
    """None (never raises) when ENCRYPTION_KEY is unusable — the route maps that
    to 404 rather than leaking config state to an unauthenticated caller."""
    try:
        return build_whatsapp_connection_store(
            get_admin_client(), encryption_key=settings.encryption_key, schema="orbity",
        )
    except EncryptionNotConfigured:
        return None


@router.post("/api/whatsapp/webhook/{token}")
@limiter.limit(settings.webhook_rate_limit)
async def whatsapp_webhook_by_token(
    token: str,
    request: Request,
    x_webhook_hmac_sha256: str | None = Header(default=None, alias="X-Webhook-Hmac-SHA256"),
    store=Depends(_store_dep),
) -> Response:
    body = await request.body()

    if settings.waha_webhook_hmac_secret:
        if not x_webhook_hmac_sha256 or not verify_hmac_sha256_hex(
            body,
            signature_hex=x_webhook_hmac_sha256,
            secret=settings.waha_webhook_hmac_secret,
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook signature"
            )

    if store is None:
        logger.warning("orbity whatsapp webhook: encryption not configured, cannot resolve token")
        return Response(status_code=status.HTTP_404_NOT_FOUND)

    connection = resolve_by_webhook_token(store, token)
    if connection is None:
        logger.debug("orbity whatsapp webhook: unknown token (404)")
        return Response(status_code=status.HTTP_404_NOT_FOUND)

    try:
        payload = await request.json()
    except ValueError:
        return Response(status_code=status.HTTP_200_OK)

    try:
        inbound = parse_waha_inbound_message(payload)
    except WhatsAppIgnoredEvent as exc:
        logger.debug("orbity whatsapp webhook: ignored (%s)", exc)
        return Response(status_code=status.HTTP_200_OK)
    except WhatsAppPayloadError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if inbound.provider_message_id and not _dedup.claim(inbound.provider_message_id):
        logger.debug("orbity whatsapp webhook: dedup hit")
        return Response(status_code=status.HTTP_200_OK)

    org_id = str(connection.org_id)
    try:
        result = await anyio.to_thread.run_sync(
            lambda: process_inbound(get_admin_client(), org_id, inbound)
        )
        logger.info("orbity whatsapp webhook org=%s: %s", org_id, result)
    except Exception:  # noqa: BLE001 — never make WAHA retry-storm us over our own bug
        logger.exception("orbity whatsapp webhook: processamento falhou org=%s", org_id)
    return Response(status_code=status.HTTP_200_OK)
