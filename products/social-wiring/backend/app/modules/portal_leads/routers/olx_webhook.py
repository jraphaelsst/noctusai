"""`/api/portals/olx/*` — the inbound Grupo OLX lead receiver.

Public + Basic-authenticated. The status codes this route returns are the
entire protocol: OLX ignores the response body, retries a non-2xx three
times, and discards the lead after 14 days with no replay.

So the contract is narrow and deliberate:

* **401** — the dependency rejects a wrong/absent secret. The one
  legitimate rejection.
* **4xx (422)** — a *listing* lead with no `clientListingId`. The vendor
  documents this as the requeue path, and it is the ONLY body-level
  condition we refuse.
* **200** — everything else, including bodies we could not parse,
  duplicates, unresolvable tenants and ingest failures. Each of those is
  durably recorded first; answering non-2xx would ask OLX to redeliver a
  lead we already hold, and eventually to throw it away.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from starlette.background import BackgroundTasks as StarletteBackgroundTasks

from noctusai_lib.integrations.olx import (
    missing_client_listing_id,
    parse_olx_lead_webhook,
    validate_olx_lead_payload,
)
from noctusai_lib.security.webhook_signatures import (
    ResolvedSecret,
    VerifiedWebhook,
    webhook_endpoint,
)

from app.config import settings
from app.dependencies import coerce_org_uuid, get_current_user_org_unified
from app.modules.leads.deps import get_leads_client
from app.modules.portal_leads.deps import get_olx_config
from app.modules.portal_leads.services.olx_webhook_service import (
    STATUS_IGNORED,
    OlxWebhookService,
)
from app.modules.portal_leads.services import olx_ingest_service
from app.rate_limit import limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/portals/olx", tags=["portal-leads-olx"])


async def _resolve_olx_secret(request: Request, body: bytes) -> ResolvedSecret:
    """The per-CRM webhook secret — DB-first, env fallback.

    Resolved per-request through the module's config seam, never captured
    at import: an import-time capture would not see an operator rotating
    the secret, and would force tests to patch our own module to say
    anything about this path (`app/modules/portal_leads/deps.py`).
    """
    config = get_olx_config()
    return ResolvedSecret(secret=config.webhook_secret or None)


def get_olx_service(client: Any = Depends(get_leads_client)) -> OlxWebhookService:
    """DI seam — the named dependency a test overrides."""
    config = get_olx_config()
    default_org = None
    if config.leads_org_id:
        try:
            default_org = coerce_org_uuid(config.leads_org_id)
        except Exception:  # noqa: BLE001 — a malformed config value must not 500 the receiver
            logger.warning(
                "olx-webhook: OLX_LEADS_ORG_ID is not a UUID (%r) — ignoring it; "
                "leads will park as unresolved rather than land in a guessed org",
                config.leads_org_id,
            )
    return OlxWebhookService(client=client, default_org_id=default_org)


@router.post("/leads")
@limiter.limit(settings.webhook_rate_limit)
async def receive_olx_lead(
    request: Request,
    verified: VerifiedWebhook = webhook_endpoint(
        secret_resolver=_resolve_olx_secret,
        scheme="basic_shared_secret",
        bypass_when_unset=False,
        log_prefix="olx-lead-webhook",
    ),
    svc: OlxWebhookService = Depends(get_olx_service),
) -> JSONResponse:
    """Receive one authenticated Grupo OLX lead.

    `bypass_when_unset=False` is not a default worth inheriting quietly:
    with no secret configured this route answers 401 rather than
    accepting anything. The alternative — an open endpoint that writes
    leads — is worse than a receiver that is temporarily down.
    """
    try:
        payload = json.loads(verified.body or b"{}")
    except (ValueError, TypeError):
        svc.record_unparseable(verified.body, "malformed-json")
        return JSONResponse({"status": STATUS_IGNORED, "reason": "malformed-json"})
    if not isinstance(payload, dict):
        svc.record_unparseable(payload, "not-an-object")
        return JSONResponse({"status": STATUS_IGNORED, "reason": "not-an-object"})

    # The one documented refusal, checked BEFORE anything is stored: the
    # vendor asks for a 4xx on a listing lead with no clientListingId so
    # it can requeue the lead with the field filled in.
    violations = validate_olx_lead_payload(payload)
    if missing_client_listing_id(violations):
        logger.warning(
            "olx-webhook: listing lead %r has no clientListingId — 422 so OLX requeues it",
            payload.get("originLeadId"),
        )
        return JSONResponse(
            {"status": "rejected", "reason": "missing-client-listing-id"},
            status_code=422,
        )

    lead = parse_olx_lead_webhook(payload)
    if lead is None:
        # No originLeadId ⇒ no dedup key. Answering 200 is still right:
        # a retry would arrive equally unkeyable, so the three attempts
        # would only delay the same outcome.
        svc.record_unparseable(payload, "no-origin-lead-id")
        return JSONResponse({"status": STATUS_IGNORED, "reason": "no-origin-lead-id"})

    if svc.is_duplicate(lead.origin_lead_id):
        return JSONResponse({"status": "duplicate", "originLeadId": lead.origin_lead_id})

    is_new = svc.record_event(lead)
    if not is_new:
        return JSONResponse({"status": "duplicate", "originLeadId": lead.origin_lead_id})

    # Processing runs strictly AFTER the 200 is on the wire. The body is
    # already durably in `olx_lead_events`, so nothing scheduled here can
    # lose it, and OLX is never kept waiting on our database.
    #
    # 🔴 Attached to the RESPONSE, not taken as a `BackgroundTasks`
    # parameter: `@limiter.limit` wraps this endpoint with
    # `functools.wraps`, so FastAPI resolves the annotations against
    # SlowAPI's module globals where `BackgroundTasks` does not exist —
    # the parameter form raises `PydanticUndefinedAnnotation` at import
    # and takes the whole app down. Documented at
    # `meta_ads/routers/leadgen_router.py`, hit once already.
    background = StarletteBackgroundTasks()
    background.add_task(svc.process_lead, lead)
    return JSONResponse(
        {"status": "accepted", "originLeadId": lead.origin_lead_id},
        background=background,
    )


@router.get("/events")
def list_olx_events(
    limit: int = 50,
    auth: tuple = Depends(get_current_user_org_unified),
    client: Any = Depends(get_leads_client),
) -> dict:
    """Delivery health for the operator card: what arrived, what stuck."""
    _, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    resp = (
        client.table("olx_lead_events")
        .select("*")
        .eq("org_id", str(org_id))
        .order("received_at", desc=True)
        .limit(min(max(limit, 1), 200))
        .execute()
    )
    rows = list(resp.data or [])
    return {
        "events": rows,
        "counts": {
            status: sum(1 for r in rows if r.get("status") == status)
            for status in {r.get("status") for r in rows if r.get("status")}
        },
    }


@router.post("/backfill", status_code=200)
def backfill_olx_leads_route(
    auth: tuple = Depends(get_current_user_org_unified),
    client: Any = Depends(get_leads_client),
) -> dict:
    """Project every stored `olx_leads` row into `leads`. Explicit,
    human-triggered, idempotent — never run from a sync path."""
    _, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    return olx_ingest_service.backfill_olx_leads(client, org_id)


__all__ = ["get_olx_service", "router"]
