"""Meta Lead-Ads webhook receiver + Page-subscription management.

Mounted at ``/api/meta/leadgen`` — deliberately NOT under ``/api/meta/ads``.
That prefix is the authenticated ads console, and hanging a PUBLIC
unauthenticated route inside an otherwise-uniformly-authed namespace is
precisely how an auth-boundary review misses one. The two public routes here
are also listed explicitly in
``tests/modules/meta_ads/test_leadgen_auth_boundary.py`` so their
publicness is asserted rather than assumed.

Two secrets, two jobs — the distinction this whole module turns on:
  • ``META_WEBHOOK_VERIFY_TOKEN`` — ours, used ONCE on the GET handshake,
    proves to META that we own this URL.
  • ``META_APP_SECRET``           — Meta's, used on EVERY POST, signs the raw
    body into ``X-Hub-Signature-256``, proves to US the call came from Meta.
Conflating them is a live defect in ``erp-imobiliario``
(``app/routers/meta_api.py:70`` resolves the verify token as the signing
secret), which is why both are named explicitly everywhere here.

``bypass_when_unset=False`` is a DELIBERATE deviation from the seed
skeleton's ``True``. A forged POST here writes lead PII into
``meta_ads_leads`` AND auto-spawns a ``negociacoes_venda`` funnel card via
migration 034's trigger — unauthenticated write-through to the operator's
CRM. The bypass affordance exists for early-dev; this credential is already
live in production, so an unset secret must fail LOUDLY rather than silently
disable verification.
"""
from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import PlainTextResponse

from noctusai_lib.api import StrictHttpModel
from noctusai_lib.integrations.meta import MetaGraphError
from noctusai_lib.integrations.meta.leadgen_webhook import (
    leadgen_challenge_response,
    parse_leadgen_webhook,
)
from noctusai_lib.security.webhook_signatures import (
    ResolvedSecret,
    VerifiedWebhook,
    webhook_endpoint,
)

from app.config import settings
from app.dependencies import coerce_org_uuid, get_admin_client, get_current_user_org
from app.modules.meta_ads.services.leadgen_webhook_service import (
    PENDING_STATUSES,
    STATUS_IGNORED,
    LeadgenWebhookService,
)
from app.rate_limit import limiter
from app.routers._meta_common import handle_meta_graph_error
from app.services.meta import MetaAdapter, get_meta_adapter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/meta/leadgen", tags=["meta-leadgen"])

_SCHEMA = "social_wiring"
_EVENTS = "meta_webhook_events"

_SUBSCRIBE_SCOPE_HINT = (
    "O token do Sistema não tem a permissão `pages_manage_metadata`, "
    "necessária para inscrever a Página no webhook de leads. Gere um novo "
    "token de Usuário do Sistema com essa permissão marcada."
)


# ─── secret resolvers (pin 2: per-request, never captured at import) ──────
async def _resolve_meta_app_secret(request: Request, body: bytes) -> ResolvedSecret:
    """The HMAC secret — the Meta **App Secret**, never the verify token.

    Resolved through ``resolve_meta_app_creds`` (DB-first Fernet vault, env
    fallback), so it is correct whether prod vaults it or reads the root
    ``.env``. Resolved per-request, not at import time: an import-time
    capture cannot be monkeypatched, which silently defeats the tests that
    are supposed to prove this works.
    """
    from app.services.app_config_store import resolve_meta_app_creds

    _app_id, app_secret = resolve_meta_app_creds()
    return ResolvedSecret(secret=app_secret or None)


# ─── public: GET handshake ───────────────────────────────────────────────
@router.get("/webhook", response_class=PlainTextResponse)
@limiter.limit(settings.webhook_rate_limit)
async def leadgen_verify(
    request: Request,
    hub_mode: str | None = Query(default=None, alias="hub.mode"),
    hub_verify_token: str | None = Query(default=None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(default=None, alias="hub.challenge"),
):
    """Meta's one-time subscription handshake.

    Fired SYNCHRONOUSLY the moment the operator clicks "Verify and Save" in
    the App Dashboard — Meta refuses to save the subscription if this fails,
    so this route must be deployed to prod BEFORE that click.

    🔴 Echoes the challenge as an opaque STRING. ``erp-imobiliario``
    returns ``int(hub_challenge)`` (``meta_api.py:326``), which raises on a
    non-numeric challenge; Meta does not promise digits.

    Rate-limited despite being a GET: it is public, unauthenticated, and
    performs a Fernet-backed config read.
    """
    from app.services.app_config_store import resolve_meta_webhook_verify_token

    expected = resolve_meta_webhook_verify_token()
    challenge = leadgen_challenge_response(
        mode=hub_mode,
        verify_token=hub_verify_token,
        challenge=hub_challenge,
        expected_token=expected,
    )
    if challenge is None:
        # Deliberately uniform: never distinguish "token unset" from "token
        # mismatch" to an unauthenticated caller.
        logger.warning("meta-leadgen: handshake refused (mode=%r)", hub_mode)
        return PlainTextResponse("forbidden", status_code=status.HTTP_403_FORBIDDEN)
    return PlainTextResponse(challenge)


def get_leadgen_service() -> LeadgenWebhookService:
    """FastAPI dependency: compose the receiver's collaborators, including
    the Redis dedup pre-filter — this is that seed module's first production
    consumer.

    A named dependency rather than an inline construction so tests can
    substitute it via ``app.dependency_overrides`` and exercise the REAL
    route (signature verification, parsing, status codes) against a fake
    service — instead of patching the module under test, which would stop
    the test exercising the thing it claims to."""
    dedup = None
    try:
        from noctusai_lib.integrations.whatsapp.dedup import get_webhook_dedup

        redis_client = None
        redis_url = getattr(settings, "redis_url", "") or ""
        if redis_url:
            from noctusai_lib.integrations.redis import make_redis_client

            redis_client = make_redis_client(redis_url)
        dedup = get_webhook_dedup(
            redis_client=redis_client,
            key_prefix="meta:leadgen:dedup:",
            # 24h, not the module default 1h: Meta's retry window is
            # hours-to-a-day, unlike the millisecond WAHA double-delivery
            # race that default was tuned for.
            ttl_seconds=86400,
        )
    except Exception:  # noqa: BLE001
        logger.warning("meta-leadgen: dedup unavailable — relying on DB idempotency")
    return LeadgenWebhookService(admin_supabase=get_admin_client(), dedup=dedup)


# ─── public: POST receiver ───────────────────────────────────────────────
@router.post("/webhook")
@limiter.limit(settings.webhook_rate_limit)
async def leadgen_receive(
    request: Request,
    verified: VerifiedWebhook = webhook_endpoint(
        secret_resolver=_resolve_meta_app_secret,
        scheme="sha256_prefixed",
        signature_header="X-Hub-Signature-256",
        bypass_when_unset=False,
        log_prefix="meta-leadgen-webhook",
    ),
    svc: LeadgenWebhookService = Depends(get_leadgen_service),
) -> dict[str, Any]:
    """Receive a verified `leadgen` delivery.

    Returns 200 for EVERYTHING past signature verification — malformed
    bodies, non-leadgen page events, duplicates, unmappable orgs, Graph
    failures. 401 (raised by the dependency) is the one legitimate
    rejection. Meta retries non-2xx with backoff and can disable the
    subscription outright; it never re-sends after a 200. So the durable
    inbox row, not the status code, is what makes a failure recoverable.
    """
    try:
        payload = json.loads(verified.body or b"{}")
    except (ValueError, TypeError):
        logger.warning("meta-leadgen: verified body was not JSON — ignoring")
        return {"status": STATUS_IGNORED, "reason": "malformed-json", "events": 0}

    events = parse_leadgen_webhook(payload)
    if not events:
        # Meta sends other Page events on the same subscription; a non-leadgen
        # change is normal traffic, not an error.
        return {"status": STATUS_IGNORED, "reason": "no-leadgen-events", "events": 0}

    results: list[dict[str, Any]] = []
    for event in events:
        is_new = svc.record_event(event)
        if not is_new or not svc.claim(event.leadgen_id):
            results.append({"leadgen_id": event.leadgen_id, "status": "duplicate"})
            continue
        results.append(
            {"leadgen_id": event.leadgen_id, "status": svc.process_event(event)}
        )
    return {"status": "ok", "events": len(events), "results": results}


# ─── authed: subscription management ─────────────────────────────────────
class PageSubscriptionOut(StrictHttpModel):
    page_id: str
    page_name: str = ""
    subscribed: bool = False
    subscribed_fields: list[str] = []
    app_id: str | None = None


class SubscriptionsOut(StrictHttpModel):
    pages: list[PageSubscriptionOut] = []
    callback_url: str = ""
    verify_token_configured: bool = False
    gated: bool = False
    reason: str | None = None


class SubscribeIn(StrictHttpModel):
    page_ids: list[str] | None = None


class SubscribeResultOut(StrictHttpModel):
    page_id: str
    ok: bool
    error: str | None = None


class SubscribeOut(StrictHttpModel):
    results: list[SubscribeResultOut] = []


class EventOut(StrictHttpModel):
    id: str
    page_id: str | None = None
    form_id: str | None = None
    status: str
    error: str | None = None
    received_at: str | None = None
    processed_at: str | None = None


class EventsOut(StrictHttpModel):
    counts: dict[str, int] = {}
    last_received_at: str | None = None
    events: list[EventOut] = []


def _resolve_adapter(
    auth: tuple = Depends(get_current_user_org),
) -> tuple[UUID, MetaAdapter]:
    """Same org-scoped auth every other Meta router uses."""
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    return org_id, get_meta_adapter(org_id=str(org_id))


def _callback_url() -> str:
    """The exact URL the operator pastes into the Meta dashboard.

    Derived from the product-URL resolver rather than hardcoded, so it stays
    correct across dev tunnels and prod.
    """
    try:
        from noctusai_lib.config.product_urls import resolve_product_url

        return f"{resolve_product_url('social-wiring').rstrip('/')}/api/meta/leadgen/webhook"
    except Exception:  # noqa: BLE001
        return "/api/meta/leadgen/webhook"


@router.get("/subscriptions", response_model=SubscriptionsOut)
def list_subscriptions(
    org_and_adapter: tuple[UUID, MetaAdapter] = Depends(_resolve_adapter),
):
    """Which Pages are actually subscribed to `leadgen`.

    App-level subscription (dashboard) and Page-level subscription (this)
    are BOTH required — either alone delivers nothing, silently. This
    endpoint is what makes the Page half visible.
    """
    from app.services.app_config_store import resolve_meta_webhook_verify_token

    _org_id, adapter = org_and_adapter
    verify_configured = bool(resolve_meta_webhook_verify_token())
    try:
        pages = adapter.list_facebook_pages()
    except MetaGraphError as exc:
        return handle_meta_graph_error(exc)

    out: list[PageSubscriptionOut] = []
    gated = False
    reason: str | None = None
    for page in pages:
        try:
            subs = adapter.list_page_subscribed_apps(page.id)
        except MetaGraphError as exc:
            if getattr(exc, "is_permission", False) or getattr(exc, "requires_app_review", False):
                gated, reason = True, _SUBSCRIBE_SCOPE_HINT
                subs = []
            else:
                raise
        fields = sorted({f for s in subs for f in (s.subscribed_fields or [])})
        out.append(
            PageSubscriptionOut(
                page_id=page.id,
                page_name=page.name or "",
                subscribed="leadgen" in fields,
                subscribed_fields=fields,
                app_id=next((s.app_id for s in subs if s.app_id), None),
            )
        )
    return SubscriptionsOut(
        pages=out,
        callback_url=_callback_url(),
        verify_token_configured=verify_configured,
        gated=gated,
        reason=reason,
    )


@router.post("/subscriptions", response_model=SubscribeOut)
def subscribe_pages(
    payload: SubscribeIn,
    org_and_adapter: tuple[UUID, MetaAdapter] = Depends(_resolve_adapter),
):
    """Subscribe Pages to `leadgen`. ``page_ids: null`` ⇒ all Pages.

    Per-page try/except: one Page failing NEVER fails the whole call. An
    operator with five Pages and one permission problem should end up with
    four working subscriptions and one named error, not zero and a 500.
    """
    _org_id, adapter = org_and_adapter
    page_ids = payload.page_ids
    if page_ids is None:
        try:
            page_ids = [p.id for p in adapter.list_facebook_pages()]
        except MetaGraphError as exc:
            return handle_meta_graph_error(exc)

    results: list[SubscribeResultOut] = []
    for page_id in page_ids:
        try:
            ok = adapter.subscribe_page_to_leadgen(page_id)
            results.append(SubscribeResultOut(page_id=page_id, ok=bool(ok)))
        except MetaGraphError as exc:
            msg = _SUBSCRIBE_SCOPE_HINT if getattr(exc, "is_permission", False) else str(exc)
            logger.warning("meta-leadgen: subscribe failed for page %s: %s", page_id, exc)
            results.append(SubscribeResultOut(page_id=page_id, ok=False, error=msg))
    return SubscribeOut(results=results)


@router.delete("/subscriptions/{page_id}", response_model=SubscribeResultOut)
def unsubscribe_page(
    page_id: str,
    org_and_adapter: tuple[UUID, MetaAdapter] = Depends(_resolve_adapter),
):
    """Undo a subscription in-product, so a mis-subscribed Page does not
    require a Graph Explorer session to fix."""
    _org_id, adapter = org_and_adapter
    try:
        ok = adapter.unsubscribe_page_from_leadgen(page_id)
        return SubscribeResultOut(page_id=page_id, ok=bool(ok))
    except MetaGraphError as exc:
        return SubscribeResultOut(page_id=page_id, ok=False, error=str(exc))


@router.get("/events", response_model=EventsOut)
def list_events(
    limit: int = Query(default=20, ge=1, le=200),
    auth: tuple = Depends(get_current_user_org),
):
    """Delivery health.

    ``last_received_at is None`` is the most diagnostic state in this whole
    feature: it means Meta has NEVER called us, i.e. the App-Dashboard half
    is not configured. Distinguishing that from "configured but no leads
    yet" is exactly what was impossible before the inbox existed.
    """
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    admin = get_admin_client()
    resp = (
        admin.schema(_SCHEMA).table(_EVENTS)
        .select("id,page_id,form_id,status,error,received_at,processed_at")
        .eq("org_id", str(org_id))
        .order("received_at", desc=True)
        .limit(limit)
        .execute()
    )
    rows = resp.data or []

    counts: dict[str, int] = {}
    try:
        all_resp = (
            admin.schema(_SCHEMA).table(_EVENTS)
            .select("status,received_at").eq("org_id", str(org_id)).execute()
        )
        all_rows = all_resp.data or []
    except Exception:  # noqa: BLE001
        all_rows = rows
    for r in all_rows:
        key = str(r.get("status") or "unknown")
        counts[key] = counts.get(key, 0) + 1
    stamps = [r.get("received_at") for r in all_rows if r.get("received_at")]

    return EventsOut(
        counts=counts,
        last_received_at=max(stamps) if stamps else None,
        events=[EventOut(**r) for r in rows],
    )


__all__ = ["router", "PENDING_STATUSES"]
