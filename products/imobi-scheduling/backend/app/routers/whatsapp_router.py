"""
WhatsApp inbound webhook — wires the seed factory into Imobi Scheduling.

Consumes ``noctusai_lib.integrations.whatsapp.create_whatsapp_webhook_router``
per `KB § PATTERNS/whatsapp-chatbot-seed.md`. The seed router owns:

* HMAC-SHA256 hex signature verification (Pin 1-3 of the 5-pin contract).
* WAHA event parsing → ``WhatsAppInboundMessage``.
* In-process idempotency on ``provider_message_id``.

This module owns the **product on_message handler** — the consumer-supplied
callable that the seed router invokes once per fresh inbound. The handler:

  1. Resolves authorization via ``AuthorizationService.authorize_inbound``
     (LID-aware 3-path resolution — see ``app/services/authorization.py``).
  2. On authorized + pushName drift, the service already runs
     opportunistic LID capture via ``_attach_lid_to_user`` during
     ``authorize_inbound``. The handler additionally refreshes
     ``users.linked_identity`` when pushName changed but no LID write yet
     happened (path 2 phone match with stale ``from_name``).
  3. On unauthorized + LID present, parks a row in
     ``pending_chat_identities`` for later admin resolution.

The mount-shape decision (option (b) in PROJECT.md Phase 5 Q): we register
this APIRouter via ``routers=[...]`` in ``create_product_app(...)``, not
via ``standard_routers=[...]`` — the seed registry at
``seed/framework/backend/noctusai_seed/routers.py:_STANDARD_ROUTERS``
does NOT yet include ``whatsapp_webhook``. Promotion is deferred until
N=2 consumers surface (e.g. mailing / therapy needing inbound WhatsApp);
filed in the project's ``Improvements:`` block.

Webhook compliance 5-pin contract status:

  * Pins 1-3 (resolve secret / verify-before-side-effect / bypass-when-unset):
    handled by the seed router's built-in HMAC verification + the
    ``bypass_when_unset`` shape (``webhook_hmac_secret=None`` → no
    verification, log a WARNING below).
  * Pin 4 (per-IP rate-limit): NOT YET WIRED. The seed router does not
    expose a rate-limit seam. Tracked as a follow-up against the
    ``noctusai_lib.integrations.whatsapp`` seed module (filed in
    ``Improvements:`` block).
  * Pin 5 (status-pinned tests): covered in
    ``tests/routers/test_whatsapp_router.py``.

Rate-limit gap is the only methodology divergence in this wiring; flagged
loud rather than silent per the no-silent-errors rule.
"""
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter

from noctusai_lib.integrations.whatsapp import (
    WhatsAppInboundMessage,
    WhatsAppSettings,
    create_whatsapp_webhook_router,
)

from app.config import settings
from app.dependencies import coerce_org_uuid, get_admin_client
from app.services.authorization import AuthorizationService, looks_like_lid
from app.services.conversation_rate_limit import get_rate_limiter

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Single-agency v1: ``org_id`` is fixed per deployment (Phase 0 Q4 in
# PROJECT.md). Future multi-tenancy lifts this into a session→org map
# resolved at request time from the WAHA payload (mirrors
# ``erp-imobiliario/whatsapp_webhook._resolve_waha_secret`` extras shape).
# ---------------------------------------------------------------------------
SINGLE_AGENCY_ORG_KEY = "imobi-scheduling-default"


def _resolve_admin_client():
    """Indirection so tests patching ``app.database._db.get_admin_client``
    propagate to this module at request-time.

    Late-binding intentional — capturing the bound method at import would
    freeze the pre-patch reference. See ``app/dependencies.py`` for the
    same shape used by the auth deps.
    """
    return get_admin_client()


async def handle_inbound_whatsapp(inbound: WhatsAppInboundMessage) -> None:
    """Persist + authorize a freshly-parsed WhatsApp inbound message.

    Called exactly once per fresh ``provider_message_id`` by the seed
    router (idempotency handled there). Errors raised here propagate up
    to the router, which returns 500 — WAHA will retry. Best-effort
    side effects (pushName refresh, pending-LID park) are wrapped in
    try/except + log to keep transient failures from blocking the
    response path. Authoritative auth lookups bubble up unmasked.

    Args:
        inbound: Parsed WhatsApp inbound message. The seed router has
            already verified the HMAC signature + deduped against
            ``provider_message_id`` before this is called.
    """
    admin = _resolve_admin_client()
    if admin is None:
        # No admin client wired (e.g. service-role key unset in early-dev).
        # Surface loud — webhook still returns 200 to WAHA, but the
        # operator needs to fix the env.
        logger.error(
            "WhatsApp inbound dropped: no admin client. "
            "Set SUPABASE_SERVICE_ROLE_KEY to enable persistence. "
            "chat_id=%s from_phone=%s",
            inbound.chat_id,
            inbound.from_phone,
        )
        return

    # Phase 11 — per-conversation rate limit. Check BEFORE auth resolution
    # so a flood from an unauthenticated chat_id can't burn DB query budget.
    # Limiter is optional (None = disabled, e.g. tests not exercising the
    # security layer). Failure-open semantics live inside the limiter
    # itself; here we only branch on `allowed`.
    rate_limiter = get_rate_limiter()
    if rate_limiter is not None:
        decision = rate_limiter.check(inbound.chat_id)
        if not decision.allowed:
            # Loud log already emitted inside the limiter; this is the
            # second signal at the request boundary (per-conversation
            # rate-limit rejected the inbound). WAHA still gets 200 —
            # the upstream isn't at fault, the conversation is.
            logger.info(
                "WhatsApp inbound throttled by per-conversation rate limit: "
                "chat_id=%s count=%d limit=%d",
                inbound.chat_id,
                decision.current_count,
                decision.limit,
            )
            return

    org_uuid = coerce_org_uuid(SINGLE_AGENCY_ORG_KEY)
    svc = AuthorizationService(admin, org_id=org_uuid)

    result = svc.authorize_inbound(
        chat_id=inbound.chat_id,
        from_phone=inbound.from_phone,
        push_name=inbound.from_name,
    )

    if result.authorized:
        # pushName auto-update: AuthorizationService captures the LID
        # via path 3 (opportunistic). The pushName itself lands on a
        # separate column the service doesn't write — refresh here when
        # the inbound carried a pushName.
        if inbound.from_name and result.user_id is not None:
            _refresh_user_push_name(
                admin,
                user_id=result.user_id,
                org_uuid=org_uuid,
                push_name=inbound.from_name,
            )
        logger.info(
            "WhatsApp inbound authorized: user_id=%s role=%s chat_id=%s",
            result.user_id,
            result.role,
            inbound.chat_id,
        )
        # Phase 6 will dispatch ``inbound`` into the conversation
        # worker here. For Phase 5 the wiring stops at authorize +
        # persist — no LLM tool-loop yet.
        return

    # Unauthorized branch.
    if result.lid:
        # Deferred-auth: park the LID for admin resolution.
        try:
            svc.park_pending_lid(
                chat_id=result.lid,
                push_name=inbound.from_name,
                phone_hint=inbound.from_phone or None,
            )
        except Exception as exc:  # noqa: BLE001 — UNIQUE conflict is benign.
            # ``park_pending_lid`` already logs internally on its own
            # try/except. This outer guard catches anything the service
            # did not — keep the webhook returning 200 to WAHA even on
            # unexpected DB shape so retries don't loop. The error
            # surfaces loud in logs.
            logger.warning(
                "Failed to park pending LID: chat_id=%s err=%s",
                result.lid,
                exc,
            )
        logger.info(
            "WhatsApp inbound parked for admin resolution: lid=%s push_name=%s",
            result.lid,
            inbound.from_name or "<unknown>",
        )
        return

    # No LID + no phone match → silently dropped at the auth boundary.
    # Operator-visible WARN; never raise (WAHA would retry indefinitely
    # for what is a real rejection).
    logger.warning(
        "WhatsApp inbound rejected: chat_id=%s from_phone=%s push_name=%s",
        inbound.chat_id,
        inbound.from_phone,
        inbound.from_name or "<unknown>",
    )


def _refresh_user_push_name(
    admin,
    *,
    user_id: UUID,
    org_uuid: UUID,
    push_name: str,
) -> None:
    """Best-effort UPDATE of ``users.name`` from the inbound pushName.

    The ``users`` table tracks ``name TEXT NOT NULL`` (P3 migration).
    The pushName WAHA exposes is the user's current WhatsApp profile
    name — refresh on each inbound so the bot's outgoing addressing
    stays aligned with how the user identifies today. Race-tolerant:
    if RLS rejects or the row vanished mid-flight, log and continue —
    auth was already decided.
    """
    try:
        (
            admin
            .schema(AuthorizationService.SCHEMA)
            .table("users")
            .update({"name": push_name})
            .eq("id", str(user_id))
            .eq("org_id", str(org_uuid))
            .execute()
        )
        logger.info(
            "Refreshed pushName for user_id=%s push_name=%s",
            user_id,
            push_name,
        )
    except Exception as exc:  # noqa: BLE001 — best-effort.
        logger.warning(
            "pushName refresh failed for user_id=%s: %s",
            user_id,
            exc,
        )


# ---------------------------------------------------------------------------
# Router construction
# ---------------------------------------------------------------------------

def _build_whatsapp_settings() -> WhatsAppSettings:
    """Construct ``WhatsAppSettings`` from product settings at import time.

    ``base_url`` is required by ``WhatsAppSettings`` but our config keeps
    it Optional for early-dev (empty schema valid before WAHA stands up).
    Coerce ``None`` → ``""`` so Pydantic validates; the empty string
    means "no real WAHA" and downstream ``get_whatsapp_client(base_url="")``
    returns the ``FakeWahaClient``.
    """
    return WhatsAppSettings(
        base_url=settings.waha_base_url or "",
        api_key=settings.waha_api_key,
        session=settings.waha_session_name,
        webhook_hmac_secret=settings.imobi_whatsapp_webhook_secret or None,
    )


# Wrap the seed router under our HTTP path. The seed router declares its
# route at the empty path ("") — FastAPI rejects ``include_router(prefix="")``
# on top of an empty inner path, so we attach the prefix at include-time
# on the outer router instead. The seed router is the actual ``router``
# exposed to ``create_product_app``; the project's ``api/webhooks/<vendor>``
# shape is preserved by the include-side prefix.
_whatsapp_settings = _build_whatsapp_settings()
_seed_router = create_whatsapp_webhook_router(
    settings=_whatsapp_settings,
    on_message=handle_inbound_whatsapp,
)

# Outer wrapper so the prefix is settable at include time without bumping
# the seed router's route declaration. ``create_product_app`` calls
# ``app.include_router(r)`` for each entry in ``routers=[...]``; embedding
# the prefix here keeps the wiring boilerplate-free.
router = APIRouter(tags=["whatsapp"])
router.include_router(_seed_router, prefix="/api/webhooks/whatsapp")
