"""
Webhook receiver — placeholder for the new product to fill in.

This is the **canonical webhook router skeleton** every scaffolded
product inherits. It demonstrates the hardened receive pattern that
five real products converged on (core/webhooks, mailing/webhooks,
media-scheduling/webhooks, erp-imobiliario/whatsapp_webhook +
meta_api):

* ``noctusai_lib.security.webhook_signatures.webhook_endpoint(...)`` —
  one decorator that replaces the verify-then-raise dance. Verifies
  signature BEFORE any DB work; mismatch → 401, no side effects.
* Per-request ``ResolvedSecret`` resolver — a tiny lambda that reads
  the secret from settings at *request* time so test-time monkeypatches
  are honored (the import-time-capture trap is real).
* ``bypass_when_unset=True`` so the product boots cleanly in early-dev
  before the secret is configured. Bypass logs a WARNING — never
  silent. Flip to ``False`` once your secret is live.
* ``@limiter.limit(settings.webhook_rate_limit)`` — DDOS guard on a
  public endpoint.
* The handler reads ``verified.body`` (raw bytes the signature was
  checked against) — never re-read ``await request.body()``.

THREE schemes are supported by the lib (pick the one your provider uses):

  - ``"sha256_prefixed"`` — Meta Lead Ads, GitHub, providers using
    ``X-Hub-Signature-256: sha256=<hex>``
  - ``"sha256_hex"`` — WAHA, internal NoctusAI-to-NoctusAI webhooks,
    bare hex digest in ``X-Webhook-Hmac-SHA256``
  - ``"svix"`` — Resend, Clerk, anything built on Svix; headers
    ``svix-id`` + ``svix-timestamp`` + ``svix-signature``

Stripe ships its own verifier (``stripe.Webhook.construct_event``);
DON'T wrap it through this dep — call the SDK directly. See
``products/core/backend/app/services/stripe_service.construct_webhook_event``
for the call shape.

TODO(new-product): rename ``example`` → your vendor (``resend``,
``meta``, ``waha``, …); pick the right ``scheme=``; pull the secret
from a real ``settings.<vendor>_webhook_secret`` field; replace the
log-and-return placeholder body with the real event dispatch.

See ``KB § PATTERNS/webhook-signatures.md`` for the full pattern doc.
"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, HTTPException, Request

from noctusai_lib.security.webhook_signatures import (
    ResolvedSecret,
    VerifiedWebhook,
    webhook_endpoint,
)

from app.config import settings
from app.rate_limit import limiter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


async def _resolve_example_secret(request: Request, body: bytes) -> ResolvedSecret:
    """Per-request lookup of the webhook secret.

    Done at request-time (not import-time) so test monkeypatches on the
    settings module are honored. The ``or None`` collapses empty-string
    secrets to the unset path so ``bypass_when_unset=True`` engages.
    """
    return ResolvedSecret(secret=settings.example_webhook_secret or None)


@router.post("/example")
@limiter.limit(settings.webhook_rate_limit)
async def example_webhook(
    request: Request,
    verified: VerifiedWebhook = webhook_endpoint(
        secret_resolver=_resolve_example_secret,
        scheme="svix",  # TODO(new-product): pick scheme matching your vendor
        bypass_when_unset=True,
        log_prefix="example-webhook",
    ),
):
    """Receive a webhook event from <vendor>.

    Auth: signature verified by ``webhook_endpoint(...)`` BEFORE this
    body runs. Reaching here means either (a) the signature checked out,
    or (b) ``EXAMPLE_WEBHOOK_SECRET`` is unset and bypass fired with a
    WARNING (early-dev only — set the secret in ``.env`` to enforce).

    TODO(new-product): replace this body with the real event dispatch.
    Typical shape:
      1. ``payload = json.loads(verified.body)`` — parse the verified bytes
      2. Pull the event type / resource id
      3. Dispatch to a service (``await event_service.handle(payload)``)
      4. Return ``{"ok": True}`` (or ``{"ok": True, "skipped": True}``
         for events you intentionally ignore — never 4xx on unknown
         event types; webhooks retry indefinitely).
    """
    body = verified.body
    try:
        payload = json.loads(body) if body else {}
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid JSON")

    event_type = payload.get("type") or payload.get("event")
    logger.info(
        "example-webhook received: event_type=%s body_size=%d",
        event_type,
        len(body),
    )
    # TODO(new-product): dispatch payload to your domain service here.
    return {"ok": True, "received": True}
