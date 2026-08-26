"""`/api/portals/imovelweb/*` — the inbound ImovelWeb / OpenNavent receiver.

Public + Basic-authenticated on the delivery route, session-authenticated on
the operator routes.

The status codes are the protocol, and they diverge from the OLX sibling in
two places that a reviewer will be tempted to "fix" back. Both divergences
are deliberate:

* **A listing lead with no `clientListingId` gets 200, not 422.** OLX
  documents a requeue path for that field; ImovelWeb documents none, and the
  field is legitimately absent when the listing was never associated. A 4xx
  here would start a 72-hour retry loop over a field that will never arrive.
* **A failed durable write returns 5xx, on purpose.** Everywhere else in
  this codebase a non-2xx to a vendor is a mistake. Here it is correct: the
  vendor retries for 72 hours and we have a pull API, so a 5xx costs us a
  redelivery while a 200 over a failed write costs a real customer.

The vendor allows **1.5 seconds** for the whole response, so the request
path does: parse (pure) → dedupe → one durable write → answer. Org
resolution, ingest and any re-fetch happen strictly after.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, Request
from fastapi.responses import JSONResponse
from starlette.background import BackgroundTasks as StarletteBackgroundTasks

from noctusai_lib.integrations.imovelweb import (
    IMOVELWEB_LEAD_EVENT_TYPES,
    detect_callback_language,
    make_imovelweb_client,
    parse_imovelweb_callback,
)
from noctusai_lib.security.webhook_signatures import (
    ResolvedSecret,
    VerifiedWebhook,
    webhook_endpoint,
)

from app.config import settings
from app.dependencies import coerce_org_uuid, get_current_user_org_unified
from app.modules.leads.deps import get_leads_client
from app.modules.portal_leads.services import (
    imovelweb_callback_service,
    imovelweb_ingest_service,
    imovelweb_reconcile_service,
)
from app.modules.portal_leads.services.imovelweb_webhook_service import (
    STATUS_IGNORED,
    ImovelWebWebhookService,
    ResponseBudget,
)
from app.rate_limit import limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/portals/imovelweb", tags=["portal-leads-imovelweb"])

#: The events route returns an explicit column list — never `select("*")`.
#: `payload` is excluded because it is the lossless vendor body and can
#: contain a CPF (`identificationId`). Returning it would hand full lead PII
#: to any authenticated member of the org.
#: → `KB § PATTERNS/security/lgpd.md`
_EVENT_COLUMNS = (
    "id, org_id, event_type, codigo_imobiliaria, client_listing_id, "
    "lead_origin, callback_language, source, status, error, attempts, "
    "received_at, processed_at"
)


async def _resolve_imovelweb_secret(request: Request, body: bytes) -> ResolvedSecret:
    """The webhook secret — DB-first, env fallback.

    Resolved per-request, never captured at import: an import-time capture
    cannot be replaced by a test, which silently defeats the tests meant to
    prove this works.
    """
    from app.modules.portal_leads.deps import get_imovelweb_config

    return ResolvedSecret(secret=get_imovelweb_config().webhook_secret or None)


def get_imovelweb_service(
    client: Any = Depends(get_leads_client),
) -> ImovelWebWebhookService:
    """DI seam — the named dependency a test overrides."""
    from app.modules.portal_leads.deps import get_imovelweb_config

    config = get_imovelweb_config()
    default_org = None
    if config.leads_org_id:
        try:
            default_org = coerce_org_uuid(config.leads_org_id)
        except Exception:  # noqa: BLE001 — a malformed config must not 500 the receiver
            logger.warning(
                "imovelweb-webhook: IMOVELWEB_LEADS_ORG_ID is not a UUID (%r) — "
                "ignoring it; leads will park as unresolved rather than land in "
                "a guessed org",
                config.leads_org_id,
            )
    return ImovelWebWebhookService(client=client, default_org_id=default_org)


def get_imovelweb_adapter() -> Any:
    """DI seam — the OpenNavent client for the operator routes.

    Built per-request from resolved config. Construction is lenient by the
    seed's contract: with no credentials this returns a client that raises a
    typed 424 on its first call rather than failing here, so an unconfigured
    tenant gets "not set up" instead of a 500 that reads like an outage.
    """
    import httpx

    from app.modules.portal_leads.deps import get_imovelweb_config

    config = get_imovelweb_config()
    return make_imovelweb_client(
        client_id=config.client_id,
        client_secret=config.client_secret,
        region=config.region,
        sandbox=config.sandbox,
        http_client=httpx.AsyncClient(timeout=20.0),
    )


@router.post("/leads")
@limiter.limit(settings.webhook_rate_limit)
async def receive_imovelweb_lead(
    request: Request,
    verified: VerifiedWebhook = webhook_endpoint(
        secret_resolver=_resolve_imovelweb_secret,
        scheme="basic_shared_secret",
        basic_username="noctusai-imovelweb",
        bypass_when_unset=False,
        log_prefix="imovelweb-lead-webhook",
    ),
    svc: ImovelWebWebhookService = Depends(get_imovelweb_service),
) -> JSONResponse:
    """Receive one authenticated ImovelWeb delivery.

    `basic_username` is not the seed default: leaving it would require the
    vendor's header to decode to `vivareal:<secret>`, which is Grupo OLX's
    convention and nonsense on this pipe. We register the value ourselves, so
    it must match what `basic_credential` builds.

    `bypass_when_unset=False`: with no secret configured this answers 401
    rather than accepting anything. An open endpoint that writes leads into a
    CRM is worse than a receiver that is temporarily down.
    """
    with ResponseBudget() as budget:
        try:
            payload = json.loads(verified.body or b"{}")
        except (ValueError, TypeError):
            svc.record_unparseable(verified.body, "malformed-json")
            return JSONResponse({"status": STATUS_IGNORED, "reason": "malformed-json"})
        if not isinstance(payload, dict):
            svc.record_unparseable(payload, "not-an-object")
            return JSONResponse({"status": STATUS_IGNORED, "reason": "not-an-object"})

        # No refusal for a missing listing code — see the module docstring.
        # The parser tolerates an unexpected language variant rather than
        # rejecting it, because a 4xx burns the 72-hour window.
        language = detect_callback_language(payload)
        lead = parse_imovelweb_callback(payload, language=language)
        if lead is None:
            # No event id ⇒ no dedup key. 200 is still right: the retry
            # arrives equally unkeyable, so a non-2xx would only delay the
            # same outcome for three days.
            svc.record_unparseable(payload, "no-event-id")
            return JSONResponse({"status": STATUS_IGNORED, "reason": "no-event-id"})

        if svc.is_duplicate(lead.event_id):
            return JSONResponse({"status": "duplicate", "eventId": lead.event_id})

        try:
            is_new = svc.record_event(lead)
        except Exception:  # noqa: BLE001 — deliberately surfaced as 5xx
            # The ONE place a non-2xx is correct. We could not store the
            # body, so answering 200 would tell the vendor to forget a lead
            # we do not have. It retries for 72 hours and the pull API
            # backstops that; a 200 here has no backstop at all.
            logger.exception(
                "imovelweb-webhook: durable write FAILED for event %s — "
                "answering 5xx so the vendor redelivers", lead.event_id,
            )
            return JSONResponse(
                {"status": "error", "reason": "durable-write-failed"},
                status_code=503,
            )

        if not is_new:
            return JSONResponse({"status": "duplicate", "eventId": lead.event_id})

    # Processing runs strictly AFTER the response is on the wire. The body is
    # already durably in `imovelweb_lead_events`, so nothing scheduled here
    # can lose it, and the vendor is never kept waiting on our database.
    #
    # 🔴 Attached to the RESPONSE, not taken as a `BackgroundTasks`
    # parameter: `@limiter.limit` wraps this endpoint with `functools.wraps`,
    # so FastAPI resolves the annotations against SlowAPI's module globals
    # where `BackgroundTasks` does not exist — the parameter form raises
    # `PydanticUndefinedAnnotation` at import and takes the whole app down.
    # Documented at `meta_ads/routers/leadgen_router.py`, hit once already.
    background = StarletteBackgroundTasks()
    background.add_task(svc.process_lead, lead)
    return JSONResponse(
        {
            "status": "accepted",
            "eventId": lead.event_id,
            # The vendor ignores our body; this is for us and for
            # `imovelweb.webhook.simulate`, which reads it back.
            "elapsedMs": budget.elapsed_ms,
            "withinBudget": not budget.exceeded,
        },
        background=background,
    )


@router.get("/events")
def list_imovelweb_events(
    limit: int = 50,
    auth: tuple = Depends(get_current_user_org_unified),
    client: Any = Depends(get_leads_client),
) -> dict:
    """Delivery health for the operator card: what arrived, what stuck.

    Selects an explicit column list. `payload` is deliberately absent: it is
    the lossless vendor body and can contain a CPF, so returning it would
    hand full lead PII to every authenticated member of the org.
    """
    _, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    resp = (
        client.table("imovelweb_lead_events")
        .select(_EVENT_COLUMNS)
        .eq("org_id", str(org_id))
        .order("received_at", desc=True)
        .limit(min(max(limit, 1), 200))
        .execute()
    )
    rows = list(resp.data or [])
    by_source = {
        source: sum(1 for r in rows if r.get("source") == source)
        for source in ("callback", "reconcile")
    }
    return {
        "events": rows,
        "counts": {
            status: sum(1 for r in rows if r.get("status") == status)
            for status in {r.get("status") for r in rows if r.get("status")}
        },
        # A rising reconcile share is the operator-visible symptom of missing
        # the 1.5-second budget: the leads still arrive, just late and by the
        # slower path. Surfaced as a first-class number rather than something
        # to be inferred from a list.
        "bySource": by_source,
    }


@router.post("/backfill", status_code=200)
def backfill_imovelweb_leads_route(
    auth: tuple = Depends(get_current_user_org_unified),
    client: Any = Depends(get_leads_client),
) -> dict:
    """Project every stored `imovelweb_leads` row into `leads`. Explicit,
    human-triggered, idempotent — never run from a sync path."""
    _, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    return imovelweb_ingest_service.backfill_imovelweb_leads(client, org_id)


@router.get("/callback")
async def read_imovelweb_callback_config(
    auth: tuple = Depends(get_current_user_org_unified),
    adapter: Any = Depends(get_imovelweb_adapter),
) -> JSONResponse:
    """Read the registration back from the vendor — the health check.

    Reports `delivers_nothing` as its own flag: a configuration with a
    perfect URL and no subscriptions is legal to the vendor, useless to us,
    and invisible to everything else.
    """
    from noctusai_lib.integrations.imovelweb import ImovelWebError

    try:
        result = await imovelweb_callback_service.read_config(adapter)
    except ImovelWebError as exc:
        return JSONResponse(
            {"error": exc.message, "configured": False},
            status_code=exc.status or 502,
        )
    return JSONResponse(result)


@router.post("/callback/register")
async def register_imovelweb_callback(
    auth: tuple = Depends(get_current_user_org_unified),
    adapter: Any = Depends(get_imovelweb_adapter),
    body: dict = Body(default_factory=dict),
) -> JSONResponse:
    """Register OUR receiver with the vendor.

    ⚠️ **INTEGRATOR-WIDE.** There is no agency code in this call, so it
    redirects every agency's leads at once. `confirm: true` is required in
    the body — the same gate the MCP tool carries, for the same reason, and
    it is checked before anything is read or resolved.
    """
    from noctusai_lib.integrations.imovelweb import ImovelWebError

    from app.modules.portal_leads.deps import get_imovelweb_config
    from app.services.app_config_store import build_app_config_store

    if not body.get("confirm"):
        return JSONResponse(
            {
                "error": (
                    "registering the callback rewrites the INTEGRATOR-WIDE "
                    "configuration — it redirects EVERY agency's leads at once. "
                    "Re-send with confirm=true. NO side-effect was performed."
                ),
                "registered": False,
            },
            status_code=412,
        )

    config = get_imovelweb_config()
    store = None
    try:
        store = build_app_config_store()
    except Exception as exc:  # noqa: BLE001 — persistence is the rollback copy, not the write
        logger.warning(
            "imovelweb-callback: no app-config store (%s) — the registration "
            "will apply but the rollback copy will not be kept", exc,
        )

    try:
        result = await imovelweb_callback_service.register_callback(
            adapter,
            public_base_url=body.get("publicBaseUrl") or config.public_base_url or "",
            webhook_secret=config.webhook_secret or "",
            language=body.get("language") or config.callback_language,
            events=tuple(body.get("events") or IMOVELWEB_LEAD_EVENT_TYPES),
            allow_local_url=bool(body.get("allowLocalUrl")),
            store=store,
        )
    except imovelweb_callback_service.CallbackRegistrationError as exc:
        return JSONResponse(
            {"error": exc.message, "registered": False}, status_code=exc.status
        )
    except ImovelWebError as exc:
        return JSONResponse(
            {"error": exc.message, "registered": False},
            status_code=exc.status or 502,
        )
    return JSONResponse(result)


@router.post("/reconcile")
async def reconcile_imovelweb_route(
    auth: tuple = Depends(get_current_user_org_unified),
    client: Any = Depends(get_leads_client),
    adapter: Any = Depends(get_imovelweb_adapter),
    body: dict = Body(default_factory=dict),
) -> JSONResponse:
    """Pull recent messages and recover anything the callback never
    delivered. Idempotent — an already-ingested lead is deduplicated on the
    vendor's `messageId`, not re-created."""
    from noctusai_lib.integrations.imovelweb import ImovelWebError

    lookback = int(
        body.get("lookbackDays")
        or imovelweb_reconcile_service.DEFAULT_LOOKBACK_DAYS
    )
    try:
        result = await imovelweb_reconcile_service.reconcile_all_agencies(
            client, adapter, lookback_days=lookback
        )
    except ImovelWebError as exc:
        return JSONResponse({"error": exc.message}, status_code=exc.status or 502)
    return JSONResponse(result)


__all__ = ["get_imovelweb_adapter", "get_imovelweb_service", "router"]
