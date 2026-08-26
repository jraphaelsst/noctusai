"""Pull the leads the callback never delivered — the durability guarantee.

This is what makes ImovelWeb's tight response budget survivable. The vendor
allows 1.5 seconds and retries for 72 hours before giving up, but it also
exposes a **pull API**: every message an agency received, by date. So a
delivery we missed — because we were slow, or down, or answered a 500 — is
recoverable as long as this job runs well inside the 72-hour window.

Three things it must get right, and each is a real failure mode:

* **Idempotency across two id spaces.** A pulled ``Mensaje`` has no
  ``eventId``. This job mints a synthetic ``reconcile:<idMensaje>`` key for
  the inbox, and the ingest layer additionally de-duplicates on the vendor's
  ``messageId`` — see ``imovelweb_ingest_service._linked_lead_by_message``.
  Without that second check, every lead that arrived by callback would be
  created a second time the next hour.
* **Tenant isolation without RLS.** This runs on the admin client, which
  bypasses row-level security. The ``imovelweb_agencies`` map IS the
  isolation boundary here, so every query carries an explicit
  ``org_id`` filter. A bug in this file is a cross-tenant leak, not a
  glitch.
* **Bounded reads.** ``fromDate`` is a window, never a full history re-pull:
  LGPD minimization applies to what we fetch, not only to what we store.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional
from uuid import UUID

from noctusai_lib.integrations.imovelweb import ImovelWebLead

from app.modules.portal_leads.services import imovelweb_ingest_service
from app.modules.portal_leads.services.imovelweb_webhook_service import (
    SOURCE_RECONCILE,
    STATUS_RECEIVED,
)

logger = logging.getLogger(__name__)

_EVENTS = "imovelweb_lead_events"
_AGENCIES = "imovelweb_agencies"

#: How far back each run looks. Well inside the vendor's 72-hour retry
#: window, and generous enough to absorb a multi-day outage of ours without
#: a manual backfill.
DEFAULT_LOOKBACK_DAYS = 7

#: Page size for the vendor's paged read. Their pageable API, not ours.
DEFAULT_PAGE_SIZE = 100

#: Stop after this many pages per agency in one run. A runaway pager (a
#: vendor that ignores `page` and returns the same rows forever) would
#: otherwise spin until the scheduler killed it, and the symptom would be a
#: job that never finishes rather than one that reports a problem.
MAX_PAGES_PER_AGENCY = 50


def _synthetic_event_id(message_id: Any) -> str:
    """The inbox key for a pulled message.

    Prefixed rather than bare so an operator reading `imovelweb_lead_events`
    can tell at a glance which rows we pulled and which the vendor pushed —
    the `source` column says the same thing, but the id is what appears in
    logs and error messages.
    """
    return f"reconcile:{message_id}"


def _from_date(days: int) -> str:
    """`yyyyMMdd`, the format the v2 endpoint takes."""
    return (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y%m%d")


def _message_to_lead(message: dict[str, Any], codigo_imobiliaria: str) -> Optional[ImovelWebLead]:
    """One pulled `Mensaje` → the same `ImovelWebLead` a callback produces.

    Built directly rather than through `parse_imovelweb_callback`: this is a
    different vendor shape (the pull API's `Mensaje`, not a callback body),
    and running it through the callback parser would silently produce a lead
    with almost every field empty. The raw message is carried verbatim so the
    ledger stays lossless either way.
    """
    message_id = message.get("idMensaje") or message.get("id")
    if message_id is None:
        # No message id ⇒ no key we can deduplicate on, and this row would
        # be re-created on every run. Skipped loudly by the caller.
        return None
    try:
        message_id_int = int(message_id)
    except (TypeError, ValueError):
        return None

    return ImovelWebLead(
        event_id=_synthetic_event_id(message_id_int),
        event_type="CONTACTO_MENSAJE",
        codigo_imobiliaria=codigo_imobiliaria,
        contact_type_id=message.get("idContactoAccion"),
        origin_lead_id=(
            str(message["idContacto"]) if message.get("idContacto") is not None else None
        ),
        message_id=message_id_int,
        timestamp=message.get("fecha"),
        name=message.get("nombre"),
        email=message.get("email"),
        phone_number=message.get("telefono"),
        message=message.get("textoMensaje"),
        client_listing_id=message.get("codigoAviso"),
        origin_listing_id=(
            str(message["idAvisoNavplat"])
            if message.get("idAvisoNavplat") is not None
            else None
        ),
        raw=message,
    )


def list_agencies(client: Any) -> list[dict[str, Any]]:
    """Every agency→org mapping we know about."""
    resp = client.table(_AGENCIES).select("codigo_imobiliaria, org_id").execute()
    return [
        row for row in list(resp.data or [])
        if row.get("codigo_imobiliaria") and row.get("org_id")
    ]


def _already_known(client: Any, org_id: UUID, event_id: str) -> bool:
    resp = (
        client.table(_EVENTS)
        .select("id")
        .eq("id", event_id)
        .eq("org_id", str(org_id))
        .execute()
    )
    return bool(list(resp.data or []))


async def reconcile_agency(
    client: Any,
    adapter: Any,
    *,
    codigo_imobiliaria: str,
    org_id: UUID,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    page_size: int = DEFAULT_PAGE_SIZE,
    ingest_fn: Optional[Callable[..., dict]] = None,
) -> dict[str, Any]:
    """Pull one agency's recent messages and ingest anything new.

    Returns counts rather than raising on a per-message failure: one bad row
    must not stop the rest of the agency's window from being recovered.
    """
    ingest = ingest_fn or imovelweb_ingest_service.ingest_imovelweb_lead
    from_date = _from_date(lookback_days)

    examined = 0
    recovered = 0
    already_had = 0
    skipped = 0
    errors: list[dict[str, Any]] = []

    for page in range(MAX_PAGES_PER_AGENCY):
        result = await adapter.list_agency_messages(
            codigo_imobiliaria, from_date=from_date, page=page, size=page_size
        )
        content = list((result or {}).get("content") or [])
        if not content:
            break

        for message in content:
            examined += 1
            lead = _message_to_lead(message, codigo_imobiliaria)
            if lead is None:
                skipped += 1
                logger.warning(
                    "imovelweb-reconcile: agency %s returned a message with no "
                    "usable id — cannot deduplicate it, skipping: %r",
                    codigo_imobiliaria, message,
                )
                continue

            if _already_known(client, org_id, lead.event_id):
                already_had += 1
                continue

            client.table(_EVENTS).insert({
                "id": lead.event_id,
                "org_id": str(org_id),
                "event_type": lead.event_type,
                "codigo_imobiliaria": codigo_imobiliaria,
                "client_listing_id": lead.client_listing_id,
                "lead_origin": None,
                "callback_language": None,
                "source": SOURCE_RECONCILE,
                "payload": lead.raw,
                "status": STATUS_RECEIVED,
                "attempts": 0,
            }).execute()

            try:
                outcome = ingest(client, org_id, lead)
            except Exception as exc:  # noqa: BLE001 — recorded per row, never swallowed
                errors.append({"event_id": lead.event_id, "error": str(exc)[:300]})
                client.table(_EVENTS).update({
                    "status": "error", "error": str(exc)[:1000],
                }).eq("id", lead.event_id).execute()
                continue

            client.table(_EVENTS).update({
                "status": "processed", "org_id": str(org_id),
            }).eq("id", lead.event_id).execute()

            if outcome.get("created"):
                recovered += 1
            else:
                # The callback had already delivered it — deduplicated on
                # messageId. This is the GOOD case: the pull found nothing
                # missing, which is what a healthy integration looks like.
                already_had += 1

        if len(content) < page_size:
            break
    else:
        logger.warning(
            "imovelweb-reconcile: agency %s hit the %d-page cap — either the "
            "window is genuinely huge or the vendor is ignoring `page`. "
            "Remaining messages were NOT examined this run.",
            codigo_imobiliaria, MAX_PAGES_PER_AGENCY,
        )

    return {
        "codigo_imobiliaria": codigo_imobiliaria,
        "org_id": str(org_id),
        "from_date": from_date,
        "examined": examined,
        "recovered": recovered,
        "already_had": already_had,
        "skipped": skipped,
        "errors": errors,
    }


async def reconcile_all_agencies(
    client: Any,
    adapter: Any,
    *,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> dict[str, Any]:
    """Run the pull for every agency we have an org mapping for.

    An agency whose run fails is recorded and the loop continues: one
    vendor-side error on one agency must not cost every other tenant their
    recovery window.
    """
    agencies = list_agencies(client)
    if not agencies:
        logger.info(
            "imovelweb-reconcile: no agencies mapped — nothing to reconcile. "
            "Agencies are populated at onboarding via the vendor's login "
            "button; until then every callback parks as unresolved."
        )
        return {"agencies": 0, "results": [], "recovered": 0}

    results: list[dict[str, Any]] = []
    recovered = 0
    for agency in agencies:
        try:
            result = await reconcile_agency(
                client,
                adapter,
                codigo_imobiliaria=agency["codigo_imobiliaria"],
                org_id=UUID(str(agency["org_id"])),
                lookback_days=lookback_days,
                page_size=page_size,
            )
        except Exception as exc:  # noqa: BLE001 — one agency must not kill the run
            logger.warning(
                "imovelweb-reconcile: agency %s failed: %s",
                agency.get("codigo_imobiliaria"), exc, exc_info=True,
            )
            results.append({
                "codigo_imobiliaria": agency.get("codigo_imobiliaria"),
                "error": str(exc)[:300],
            })
            continue
        recovered += result["recovered"]
        results.append(result)

    logger.info(
        "imovelweb-reconcile: agencies=%d recovered=%d", len(agencies), recovered
    )
    return {"agencies": len(agencies), "results": results, "recovered": recovered}


__all__ = [
    "DEFAULT_LOOKBACK_DAYS",
    "DEFAULT_PAGE_SIZE",
    "MAX_PAGES_PER_AGENCY",
    "list_agencies",
    "reconcile_agency",
    "reconcile_all_agencies",
]
