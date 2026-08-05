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

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse, PlainTextResponse
from starlette.background import BackgroundTasks as StarletteBackgroundTasks

from noctusai_lib.api import StrictHttpModel
from noctusai_lib.integrations.meta import MetaGraphError
from noctusai_lib.integrations.meta.leadgen_webhook import (
    leadgen_challenge_response,
    parse_leadgen_update_webhook,
    parse_leadgen_webhook,
)
from noctusai_lib.realtime import create_sse_router
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
from app.services.meta_leads_realtime import get_meta_leads_bus, meta_leads_scope

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
) -> JSONResponse:
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
        return JSONResponse(
            {"status": STATUS_IGNORED, "reason": "malformed-json", "events": 0}
        )
    if not isinstance(payload, dict):
        # Valid JSON, wrong shape (a bare list or scalar). Distinguished from
        # `malformed-json` because they point at different causes, and nothing
        # downstream may assume `.get()` exists on it.
        logger.warning("meta-leadgen: verified body was JSON but not an object")
        return JSONResponse(
            {"status": STATUS_IGNORED, "reason": "not-an-object", "events": 0}
        )

    # `leadgen_update` is a DIFFERENT event class, not a variant of `leadgen`:
    # it reports that an EXISTING lead's AI-agent qualification changed, and
    # can fire many times for one lead. Routed first and separately so a
    # qualification change can never be mistaken for a new lead submission.
    updates = parse_leadgen_update_webhook(payload)
    update_results = [
        {"leadgen_id": u.leadgen_id, "status": svc.process_qualification_event(u)}
        for u in updates
    ]

    events = parse_leadgen_webhook(payload)

    # Anything STILL unrecognised is recorded, unconditionally — not only when
    # the delivery contained nothing else. Meta batches, so one body can carry
    # a lead, a qualification update AND a field we have never seen; an
    # early-return on either of the first two would silently swallow the third.
    # "Arrived and we ignored it" must stay distinguishable from "never
    # arrived": those are opposite problems (our parser vs. the dashboard
    # subscription) and the inbox is the only thing that tells them apart.
    recorded = svc.record_unhandled(payload)

    if not events:
        return JSONResponse({
            "status": "ok" if update_results else STATUS_IGNORED,
            "reason": None if update_results else "no-leadgen-events",
            "events": 0,
            "qualification_updates": len(update_results),
            "results": update_results,
            "recorded": recorded,
        })

    results: list[dict[str, Any]] = []
    # The announcement half — operator alert (in-app + WhatsApp + email) and
    # the realtime push that puts the lead on open screens with no refresh.
    # It runs strictly AFTER this 200 is on the wire: SMTP and WAHA are slow
    # third parties, and Meta retries any non-2xx and can disable the
    # subscription outright. `process_event` has already stored + normalized
    # the lead durably by then, so nothing scheduled here can lose it.
    #
    # 🔴 Attached to the RESPONSE rather than taken as a `BackgroundTasks`
    # parameter, and that is not a style choice: `@limiter.limit` wraps this
    # endpoint with `functools.wraps`, so FastAPI resolves the signature's
    # annotations against SlowAPI's module globals, where `BackgroundTasks`
    # does not exist. The parameter form raises `PydanticUndefinedAnnotation`
    # at import and takes the whole app down with it. Starlette's
    # response-level `background=` has identical run-after-response semantics
    # and needs no annotation resolution.
    announce = StarletteBackgroundTasks()
    for event in events:
        is_new = svc.record_event(event)
        if not is_new or not svc.claim(event.leadgen_id):
            results.append({"leadgen_id": event.leadgen_id, "status": "duplicate"})
            continue
        outcome = svc.process_event(event)
        results.append({"leadgen_id": event.leadgen_id, "status": outcome.status})
        if outcome.announceable:
            announce.add_task(svc.fan_out, outcome)
    return JSONResponse(
        {
            "status": "ok",
            "events": len(events),
            "results": results,
            "qualification_updates": len(update_results),
            "recorded": recorded,
        },
        background=announce if announce.tasks else None,
    )


# ─── authed: subscription management ─────────────────────────────────────
class PageSubscriptionOut(StrictHttpModel):
    page_id: str
    page_name: str = ""
    subscribed: bool = False
    subscribed_fields: list[str] = []
    app_id: str | None = None
    #: Which client this Page's leads belong to, for notification routing.
    #: NULL = unattributed → alerts fall back to the org-wide recipient tier.
    #: Derived from the Page's lead forms, which is where the mapping lives
    #: (`integration_accounts` cannot answer it — its `meta` row holds an
    #: Instagram business id, not the Facebook Page id the webhook sends).
    client_id: str | None = None
    #: How many of this Page's forms carry that client. Surfaced because a
    #: Page whose forms disagree is a real state (a form synced before the
    #: assignment) and silently showing one of them would hide it.
    forms_total: int = 0
    forms_attributed: int = 0


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
    #: Active rows in `notification_recipients`. ZERO means every arriving
    #: lead is stored correctly and silently — nobody is alerted. That state
    #: is invisible from the lead list (the leads are all there) and from the
    #: logs (nothing errored), so the health card is the one place it can be
    #: surfaced to the person who can fix it.
    notification_recipients_active: int = 0


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
        attribution = _page_client_attribution(_org_id, page.id)
        out.append(
            PageSubscriptionOut(
                page_id=page.id,
                page_name=page.name or "",
                subscribed="leadgen" in fields,
                subscribed_fields=fields,
                app_id=next((s.app_id for s in subs if s.app_id), None),
                client_id=attribution["client_id"],
                forms_total=attribution["total"],
                forms_attributed=attribution["attributed"],
            )
        )
    return SubscriptionsOut(
        pages=out,
        callback_url=_callback_url(),
        verify_token_configured=verify_configured,
        gated=gated,
        reason=reason,
    )


def _page_client_attribution(org_id: UUID, page_id: str) -> dict[str, Any]:
    """Summarise which client a Page's lead forms are attributed to.

    Reports the MAJORITY client plus the counts rather than a single id,
    because "3 of 5 forms are One Consultoria" is a real and actionable state
    (a form synced after the assignment carries NULL) and collapsing it to one
    value would hide the two that still route to the org tier.
    """
    try:
        rows = (
            get_admin_client().schema(_SCHEMA).table("meta_ads_lead_forms")
            .select("client_id").eq("org_id", str(org_id))
            .eq("page_id", page_id).execute()
        ).data or []
    except Exception:  # noqa: BLE001 — the card must render without this
        logger.warning("meta-leadgen: could not read client attribution for page %s", page_id)
        return {"client_id": None, "total": 0, "attributed": 0}

    assigned = [r["client_id"] for r in rows if r.get("client_id")]
    majority = max(set(assigned), key=assigned.count) if assigned else None
    return {"client_id": majority, "total": len(rows), "attributed": len(assigned)}


class PageClientIn(StrictHttpModel):
    #: `None` clears the attribution back to unattributed (org-wide alerts).
    client_id: str | None = None


@router.put("/pages/{page_id}/client", response_model=PageSubscriptionOut)
def set_page_client(
    page_id: str,
    payload: PageClientIn,
    auth: tuple = Depends(get_current_user_org),
):
    """Attribute every lead form on a Page to a client — the routing key.

    Applied at PAGE level, not per form: a Page belongs to one client in
    practice, and per-form assignment would be tedious and would drift as new
    forms sync in. Every form on the page is updated, so a form created later
    is picked up by re-applying rather than by hunting for the odd one out.

    🔴 Never inferred from the Page name or the ad account. A wrong
    attribution routes one client's lead PII to another client's contacts,
    which is strictly worse than the unattributed fallback it would replace.
    """
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    admin = get_admin_client()

    if payload.client_id:
        owned = (
            admin.schema(_SCHEMA).table("clients")
            .select("id").eq("org_id", str(org_id))
            .eq("id", payload.client_id).limit(1).execute()
        ).data or []
        if not owned:
            # Cross-org assignment would be a PII routing hole, not a 404.
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="client not found in this organisation",
            )

    (
        admin.schema(_SCHEMA).table("meta_ads_lead_forms")
        .update({"client_id": payload.client_id})
        .eq("org_id", str(org_id)).eq("page_id", page_id)
        .execute()
    )
    attribution = _page_client_attribution(org_id, page_id)
    logger.info(
        "meta-leadgen: page %s attributed to client %s (%d/%d forms)",
        page_id, payload.client_id or "—",
        attribution["attributed"], attribution["total"],
    )
    return PageSubscriptionOut(
        page_id=page_id,
        client_id=attribution["client_id"],
        forms_total=attribution["total"],
        forms_attributed=attribution["attributed"],
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

    # Best-effort: a failure to count recipients must never break the health
    # card, which is itself a diagnostic surface. 0 is the honest fallback —
    # it prompts a check rather than falsely reassuring.
    recipients_active = 0
    try:
        rec = (
            admin.schema(_SCHEMA).table("notification_recipients")
            .select("id").eq("org_id", str(org_id)).eq("is_active", True).execute()
        )
        recipients_active = len(rec.data or [])
    except Exception:  # noqa: BLE001
        logger.warning("meta-leadgen: could not count notification recipients")

    return EventsOut(
        counts=counts,
        last_received_at=max(stamps) if stamps else None,
        events=[EventOut(**r) for r in rows],
        notification_recipients_active=recipients_active,
    )


# ── Realtime stream (SSE) ────────────────────────────────────────────────────
# The live half of "a lead appears without a refresh". Mounted on the SAME
# seed primitive the WhatsApp inbox uses (`noctusai_lib.realtime`) rather than
# a second transport — see `app/services/meta_leads_realtime.py` for why that
# decision was made once instead of twice.
#
# `create_sse_router` captures its `bus` argument ONCE at router-construction
# time (module import), not per request. `_MetaLeadsBusProxy` exists so tests
# can still swap the target bus afterwards: a genuinely-live bus cannot be
# driven through `TestClient` at all, because `subscribe()` never terminates.
# Production never reassigns `_meta_leads_bus` after startup, so the
# indirection costs nothing there. This mirrors the WhatsApp router's proxy
# for the same reason — the constraint is the seed's, not either product's.
_meta_leads_bus = get_meta_leads_bus(getattr(settings, "redis_url", "") or "")


class _MetaLeadsBusProxy:
    """Delegates to whatever module-level ``_meta_leads_bus`` CURRENTLY points
    at, read at call time rather than captured once."""

    async def publish(self, scope: str, event: str, payload: dict) -> str | None:
        return await _meta_leads_bus.publish(scope, event, payload)

    def subscribe(self, scope: str, *, last_event_id: str | None = None):
        return _meta_leads_bus.subscribe(scope, last_event_id=last_event_id)


async def _resolve_stream_org(
    request: Request,
    auth: tuple = Depends(get_current_user_org),
) -> UUID:
    """Auth dependency for the SSE stream.

    🔴 The org is taken from the AUTHENTICATED CALLER, never from a path or
    query parameter. A scope string is an opaque subscription key to the seed
    — it performs no authorization of its own — so if the org were
    caller-supplied, any authenticated user could subscribe to any org's lead
    stream and receive its PII in real time. Deriving it from the session is
    what makes the stream honour the same boundary the leads tables' RLS does.
    """
    _user, _token, raw_org = auth
    return coerce_org_uuid(raw_org)


def _stream_scope(request: Request, org_id: UUID) -> str:
    return meta_leads_scope(org_id)


router.include_router(
    create_sse_router(
        _MetaLeadsBusProxy(),
        scope_resolver=_stream_scope,
        auth_dependency=_resolve_stream_org,
        path="/stream",
    )
)


__all__ = ["router", "PENDING_STATUSES"]
