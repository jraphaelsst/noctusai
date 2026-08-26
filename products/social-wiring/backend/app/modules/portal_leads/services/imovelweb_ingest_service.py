"""Map an `imovelweb_leads` ledger row onto the unified ``leads`` base.

Sibling of ``olx_ingest_service`` — same two-stage shape (lossless vendor
ledger → source-agnostic projection), same reasons, and the mapping itself
lives in the seed (``noctusai_lib.integrations.imovelweb.normalizers``) so
``mcp/imovelweb`` and this module agree on it exactly.

Two things differ from the OLX sibling, and both are load-bearing:

**The dedup key is the DELIVERY, not the lead.** Idempotency is keyed on
``(org_id, 'imovelweb', eventId)``. The vendor's ``originLeadId`` is the
*contact*, and one contact legitimately fans out to several events — a
phone reveal, then a message, on the same listing. Keying on the contact
would silently collapse two real leads into one.

**The pipe and the portal are separate fields.** ``external_source`` is the
constant ``'imovelweb'`` — the pipe, and half of the idempotency key.
``origem_id`` is the per-portal ``lead_sources`` row resolved from
``leadOrigin``. If ``external_source`` varied with the portal, the same
``eventId`` re-delivered with an absent or changed ``leadOrigin`` would
insert a second row. The OLX pipe could conflate them because it has only
one slug; here it would be a duplication bug.

Read-then-write rather than ``upsert()``: ``MockRequestBuilder.upsert()`` is
a documented no-op, so an upsert-based path tests green and duplicates live.
"""
from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from noctusai_lib.integrations.persistence import iter_paged_rows

from noctusai_lib.integrations.imovelweb import (
    IMOVELWEB_PIPE,
    ImovelWebLead,
    imovelweb_lead_to_lead_payload,
    parse_imovelweb_callback,
    resolve_source_slug,
)

from app.modules.leads.services import dimensions_service, leads_service
from app.modules.leads.services.query import backfill_generated_columns

logger = logging.getLogger(__name__)

_LEDGER = "imovelweb_leads"

#: PostgREST page size for the bulk backfill. A bare `.select().execute()`
#: silently caps at PostgREST's default page and reports success — the
#: 98377d26 bug class (`KB § PATTERNS/backend/postgrest-row-cap.md`).
#: Matches the OLX and Meta ledgers, whose rows likewise carry a full `raw`.
_BACKFILL_PAGE_SIZE = 500


def _table(client: Any, name: str):
    # `client` is already `social_wiring`-scoped — see
    # `app/modules/leads/deps.py::get_leads_client`.
    return client.table(name)


def _find_existing(client: Any, org_id: UUID, event_id: str) -> Optional[dict]:
    resp = (
        _table(client, "leads")
        .select("*")
        .eq("org_id", str(org_id))
        .eq("external_source", IMOVELWEB_PIPE)
        .eq("external_lead_id", event_id)
        .execute()
    )
    rows = list(resp.data or [])
    return rows[0] if rows else None


def _linked_lead_by_message(
    client: Any, org_id: UUID, lead: ImovelWebLead
) -> Optional[dict]:
    """The `leads` row for this MESSAGE, if one already exists under a
    different event id.

    This is the guard against the reconcile/callback duplicate, and it is the
    practical answer to an open vendor question. A `Mensaje` pulled by the
    reconciliation job carries **no eventId** — whether its `idMensaje` shares
    an id space with the callback's `messageId` is Gate 0.6, still unanswered.
    So the reconcile path mints its own synthetic event id, which means the
    same human enquiry can arrive twice under two different keys: once pulled,
    once pushed.

    `message_id` closes it without needing that answer. It is the vendor's own
    id for the message, it appears on both surfaces, and it is present on
    exactly the class where the overlap can happen — reconciliation pulls
    MESSAGES, so it can only ever produce `CONTACTO_MENSAJE` leads, and those
    are the only ones carrying a `messageId` at all. A `CONTACTO` (a phone
    reveal, no message) has no twin to collide with.

    The ledger keeps BOTH rows, because both deliveries genuinely happened and
    that is what a lossless ledger is for. Only the `leads` projection is
    deduplicated.
    """
    if lead.message_id is None:
        return None
    resp = (
        _table(client, _LEDGER)
        .select("id")
        .eq("org_id", str(org_id))
        .eq("message_id", lead.message_id)
        .execute()
    )
    for row in list(resp.data or []):
        twin_id = str(row.get("id") or "")
        if not twin_id or twin_id == lead.event_id:
            continue
        existing = _find_existing(client, org_id, twin_id)
        if existing is not None:
            return existing
    return None


def get_or_create_imovelweb_source(client: Any, org_id: UUID, slug: str) -> dict:
    """The org's ``lead_sources`` row for ``slug``.

    ``slug`` is a parameter rather than a constant because this vendor
    genuinely names the portal: ``leadOrigin`` is ``Imovelweb`` /
    ``Wimoveis`` / ``CasaMineira``, so attribution is a lookup, not the
    inference the OLX pipe needs. Every slug it can resolve to already ships
    in ``seed_data.CANONICAL_SOURCES``, so no migration is involved.
    """
    for row in dimensions_service.list_sources(client, org_id):
        if row["slug"] == slug:
            return row
    dimensions_service.ensure_default_dimensions(client, org_id)
    for row in dimensions_service.list_sources(client, org_id):
        if row["slug"] == slug:
            return row
    raise RuntimeError(
        f"imovelweb_ingest_service: {slug!r} source missing after "
        "ensure_default_dimensions — seed_data.CANONICAL_SOURCES drifted"
    )


def store_imovelweb_lead(client: Any, org_id: UUID, lead: ImovelWebLead) -> None:
    """Write the lossless ledger row. Idempotent on the PK.

    Written BEFORE the projection: if the mapping raises (an unparseable
    timestamp, say), the vendor's body is still durably ours and the event
    is re-processable once the mapping is fixed.

    🔴 `identification_id` (a CPF) is deliberately NOT given a column. It
    survives only inside `raw`, which is what makes that column personal
    data — see the migration's COMMENT and
    `KB § PATTERNS/security/lgpd.md`.
    """
    existing = _table(client, _LEDGER).select("id").eq("id", lead.event_id).execute()
    if list(existing.data or []):
        return
    _table(client, _LEDGER).insert({
        "id": lead.event_id,
        "org_id": str(org_id),
        "event_type": lead.event_type,
        "contact_type_id": lead.contact_type_id,
        "contact_type": lead.contact_type,
        "origin_lead_id": lead.origin_lead_id,
        "message_id": lead.message_id,
        "lead_origin": lead.lead_origin,
        "origin_listing_id": lead.origin_listing_id,
        "client_listing_id": lead.client_listing_id,
        "internal_reference": lead.internal_reference,
        "codigo_imobiliaria": lead.codigo_imobiliaria,
        "id_navplat_development": lead.id_navplat_development,
        "development_code": lead.development_code,
        "name": lead.name,
        "email": lead.email,
        "ddd": lead.ddd,
        "phone": lead.phone,
        "phone_number": lead.phone_number,
        "message": lead.message,
        "user_id_navplat": lead.user_id_navplat,
        "lead_timestamp": lead.timestamp or None,
        "raw": lead.raw,
    }).execute()


def ingest_imovelweb_lead(
    client: Any, org_id: UUID, lead: ImovelWebLead
) -> dict[str, Any]:
    """Idempotent single-delivery ingest: one `ImovelWebLead` → one ``leads``
    row.

    Re-running with the same ``eventId`` is a no-op returning the EXISTING
    row. That is ordinary traffic here, not an edge case: the vendor retries
    for 72 hours, and the reconciliation job re-reads the same window — so
    the same event arrives more than once, by two different paths, by design.

    Raises ``ValueError`` (from the seed normalizer) when the timestamp is
    unparseable. Deliberate: ``data_entrada`` is NOT NULL and this path will
    not invent one. The caller records the failure on the event row so it is
    visible and retryable, never silently dropped.
    """
    existing = _find_existing(client, org_id, lead.event_id)
    if existing is not None:
        return {"lead": backfill_generated_columns(existing), "created": False}

    # The delivery is real evidence whether or not it produces a new lead, so
    # the ledger row is written first and unconditionally.
    store_imovelweb_lead(client, org_id, lead)

    twin = _linked_lead_by_message(client, org_id, lead)
    if twin is not None:
        logger.info(
            "imovelweb_ingest_service: event %s is the same message as an "
            "already-ingested delivery (messageId=%s) — ledger row kept, no "
            "second lead created",
            lead.event_id, lead.message_id,
        )
        return {
            "lead": backfill_generated_columns(twin),
            "created": False,
            "deduped_on": "message_id",
        }

    slug = resolve_source_slug(lead.lead_origin)
    source = get_or_create_imovelweb_source(client, org_id, slug)
    payload = imovelweb_lead_to_lead_payload(lead, origem_source_id=source["id"])
    created = leads_service.create_lead(client, org_id, payload)
    return {"lead": created, "created": True, "source_slug": slug}


def ingest_imovelweb_payload(
    client: Any, org_id: UUID, payload: dict, *, language: Optional[str] = None
) -> dict[str, Any]:
    """`ingest_imovelweb_lead` from a raw delivery body.

    Raises `ValueError` when the body has no event id — without one there is
    no dedup key, so storing it would risk duplicating on the retry, and the
    vendor retries for 72 hours.
    """
    lead = parse_imovelweb_callback(payload, language=language)
    if lead is None:
        raise ValueError(
            "ingest_imovelweb_payload: body has no usable eventId — refusing to "
            "store a lead that cannot be deduplicated against its retries"
        )
    return ingest_imovelweb_lead(client, org_id, lead)


def attach_smartlead(
    client: Any, org_id: UUID, event_id: str, smartlead: dict[str, Any]
) -> bool:
    """Attach buyer-intent enrichment to an already-stored ledger row.

    Separate from ingest, and downstream of it, on purpose: enrichment is an
    upstream round-trip that cannot happen inside the vendor's 1.5-second
    response budget, and its failure must be a degradation rather than a lost
    lead. `smartlead` is nullable in the schema for exactly this reason.

    Returns False when there is no such row — the caller decides whether that
    is worth reporting. It is never an exception, because a missing ledger
    row means the enrichment simply has nothing to attach to.
    """
    if not smartlead:
        return False
    existing = (
        _table(client, _LEDGER)
        .select("id")
        .eq("id", event_id)
        .eq("org_id", str(org_id))
        .execute()
    )
    if not list(existing.data or []):
        return False
    _table(client, _LEDGER).update({"smartlead": smartlead}).eq(
        "id", event_id
    ).eq("org_id", str(org_id)).execute()
    return True


def backfill_imovelweb_leads(
    client: Any, org_id: UUID, *, page_size: int = _BACKFILL_PAGE_SIZE
) -> dict[str, Any]:
    """Project every existing ``imovelweb_leads`` row for ``org_id`` into
    ``leads``. Explicit, logged, idempotent, never called automatically from
    a sync path — a real trigger is required each time.

    Paged via the seed's ``iter_paged_rows``, which owns the loop: its
    termination rests on progress over unseen rows rather than on the backend
    honouring ``range()``. An offset-only loop here spins forever the moment
    the pager is a no-op, which is what hung the OLX equivalent on its first
    run against the then-no-op mock.
    """
    ingested = 0
    skipped_existing = 0
    errors: list[dict[str, Any]] = []

    def fetch_page(start: int, end: int):
        return (
            _table(client, _LEDGER)
            .select("*")
            .eq("org_id", str(org_id))
            .order("id")
            .range(start, end)
            .execute()
            .data
        )

    for row in iter_paged_rows(
        fetch_page,
        page_size=page_size,
        label=f"imovelweb_leads backfill for org_id={org_id}",
    ):
        body = row.get("raw") or {}
        try:
            result = ingest_imovelweb_payload(client, org_id, body)
        except ValueError as exc:
            errors.append({"event_id": row.get("id"), "error": str(exc)})
            continue
        if result["created"]:
            ingested += 1
        else:
            skipped_existing += 1

    logger.info(
        "imovelweb_ingest_service.backfill_imovelweb_leads: org=%s ingested=%s "
        "skipped_existing=%s errors=%s",
        org_id, ingested, skipped_existing, len(errors),
    )
    return {"ingested": ingested, "skipped_existing": skipped_existing, "errors": errors}


__all__ = [
    "attach_smartlead",
    "backfill_imovelweb_leads",
    "get_or_create_imovelweb_source",
    "ingest_imovelweb_lead",
    "ingest_imovelweb_payload",
    "store_imovelweb_lead",
]
