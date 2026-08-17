"""Map an `olx_leads` ledger row onto the unified ``leads`` base.

Sibling of ``app/modules/leads/services/meta_ingest_service.py`` — same
two-stage shape (lossless vendor ledger → source-agnostic projection),
same reasons. The mapping itself is NOT here: it lives in the seed
(``noctusai_lib.integrations.olx.normalizers``) because ``mcp/olx`` and
this module must agree on it exactly.

Idempotency is keyed on ``(org_id, 'grupo-olx', origin_lead_id)`` via
migration 051's ``uq_sw_leads_org_external_lead``, checked read-then-write
before inserting rather than with ``upsert()`` (``MockRequestBuilder.
upsert()`` is a documented no-op, so an upsert-based path tests green and
duplicates live).
"""
from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from noctusai_lib.integrations.olx import (
    OLX_SOURCE_SLUG,
    OlxLead,
    olx_lead_to_lead_payload,
    parse_olx_lead_webhook,
)

from app.modules.leads.services import dimensions_service, leads_service
from app.modules.leads.services.query import backfill_generated_columns

logger = logging.getLogger(__name__)

#: PostgREST page size for the bulk backfill. A bare `.select().execute()`
#: silently caps at PostgREST's default page and reports success — the
#: 98377d26 bug class, which `MockSupabaseClient.range()` (a no-op) cannot
#: catch in tests. Paginate explicitly.
_BACKFILL_PAGE_SIZE = 500


def _table(client: Any, name: str):
    # `client` is already `social_wiring`-scoped — see
    # `app/modules/leads/deps.py::get_leads_client`.
    return client.table(name)


def _find_existing(client: Any, org_id: UUID, origin_lead_id: str) -> Optional[dict]:
    resp = (
        _table(client, "leads")
        .select("*")
        .eq("org_id", str(org_id))
        .eq("external_source", OLX_SOURCE_SLUG)
        .eq("external_lead_id", origin_lead_id)
        .execute()
    )
    rows = list(resp.data or [])
    return rows[0] if rows else None


def get_or_create_olx_source(client: Any, org_id: UUID) -> dict:
    """The org's canonical ``grupo-olx`` ``lead_sources`` row.

    Provisioned the same idempotent way every other canonical source is
    (``ensure_default_dimensions``); called here because this is a real
    write path, not a bare read.
    """
    for row in dimensions_service.list_sources(client, org_id):
        if row["slug"] == OLX_SOURCE_SLUG:
            return row
    dimensions_service.ensure_default_dimensions(client, org_id)
    for row in dimensions_service.list_sources(client, org_id):
        if row["slug"] == OLX_SOURCE_SLUG:
            return row
    raise RuntimeError(
        f"olx_ingest_service: {OLX_SOURCE_SLUG!r} source missing after "
        "ensure_default_dimensions — seed_data.CANONICAL_SOURCES drifted"
    )


def store_olx_lead(client: Any, org_id: UUID, lead: OlxLead) -> None:
    """Write the lossless ledger row. Idempotent on the PK.

    The ledger is written BEFORE the projection: if the mapping raises
    (an unparseable timestamp, say), the vendor's body is still durably
    ours and the event can be re-processed once the mapping is fixed.
    Losing it would be permanent — OLX discards after 14 days.
    """
    existing = (
        _table(client, "olx_leads").select("id").eq("id", lead.origin_lead_id).execute()
    )
    if list(existing.data or []):
        return
    _table(client, "olx_leads").insert({
        "id": lead.origin_lead_id,
        "org_id": str(org_id),
        "lead_origin": lead.lead_origin or None,
        "origin_listing_id": lead.origin_listing_id,
        "client_listing_id": lead.client_listing_id,
        "name": lead.name,
        "email": lead.email,
        "phone": lead.full_phone,
        "message": lead.message,
        "temperature": lead.temperature,
        "transaction_type": lead.transaction_type,
        "lead_type": lead.lead_type,
        "lead_timestamp": lead.timestamp or None,
        "extra_data": lead.extra_data or {},
        "raw": lead.raw,
    }).execute()


def ingest_olx_lead(client: Any, org_id: UUID, lead: OlxLead) -> dict[str, Any]:
    """Idempotent single-lead ingest: one `OlxLead` → one ``leads`` row.

    Re-running with the same ``origin_lead_id`` is a no-op returning the
    EXISTING row — which is not an edge case here but ordinary traffic:
    OLX retries a non-2xx 3 times and stores failures for 14 days.

    Raises ``ValueError`` (from the seed normalizer) when the timestamp is
    unparseable. That is deliberate: ``data_entrada`` is NOT NULL and this
    path will not invent one. The caller records the failure on the event
    row so it is visible and retryable, never silently dropped.
    """
    existing = _find_existing(client, org_id, lead.origin_lead_id)
    if existing is not None:
        return {"lead": backfill_generated_columns(existing), "created": False}

    store_olx_lead(client, org_id, lead)

    source = get_or_create_olx_source(client, org_id)
    payload = olx_lead_to_lead_payload(lead, origem_source_id=source["id"])
    created = leads_service.create_lead(client, org_id, payload)
    return {"lead": created, "created": True}


def ingest_olx_payload(client: Any, org_id: UUID, payload: dict) -> dict[str, Any]:
    """`ingest_olx_lead` from a raw delivery body. Raises `ValueError`
    when the body has no `originLeadId` — without it there is no dedup
    key, so storing it would risk duplicating on the retry."""
    lead = parse_olx_lead_webhook(payload)
    if lead is None:
        raise ValueError(
            "ingest_olx_payload: body has no usable originLeadId — refusing to "
            "store a lead that cannot be deduplicated against its retries"
        )
    return ingest_olx_lead(client, org_id, lead)


def backfill_olx_leads(
    client: Any, org_id: UUID, *, page_size: int = _BACKFILL_PAGE_SIZE
) -> dict[str, Any]:
    """Project every existing ``olx_leads`` row for ``org_id`` into
    ``leads``. Explicit, logged, idempotent, and never called from a
    sync/import path automatically — a real trigger is required each time.

    Paged: see `_BACKFILL_PAGE_SIZE`.
    """
    ingested = 0
    skipped_existing = 0
    errors: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    offset = 0
    while True:
        resp = (
            _table(client, "olx_leads")
            .select("*")
            .eq("org_id", str(org_id))
            .order("id")
            .range(offset, offset + page_size - 1)
            .execute()
        )
        rows = list(resp.data or [])
        if not rows:
            break

        # No-progress guard. The loop's termination must not depend on the
        # backend honouring `range()` — `MockSupabaseClient.range()` is a
        # documented no-op, so under the mock every page returns the FULL
        # set and an offset-only loop spins forever. A real client that
        # ignored the header would hang production the same way. Advancing
        # on rows we have not already processed makes progress the
        # termination condition instead of the pager's cooperation.
        fresh = [row for row in rows if str(row.get("id")) not in seen_ids]
        if not fresh:
            logger.warning(
                "olx_ingest_service.backfill_olx_leads: page at offset %s returned "
                "%s row(s), none of them new — the backend appears to ignore "
                "range(); stopping rather than looping",
                offset, len(rows),
            )
            break

        for row in fresh:
            seen_ids.add(str(row.get("id")))
            body = row.get("raw") or {}
            try:
                result = ingest_olx_payload(client, org_id, body)
            except ValueError as exc:
                errors.append({"origin_lead_id": row.get("id"), "error": str(exc)})
                continue
            if result["created"]:
                ingested += 1
            else:
                skipped_existing += 1

        if len(rows) < page_size:
            break
        offset += page_size

    logger.info(
        "olx_ingest_service.backfill_olx_leads: org=%s ingested=%s "
        "skipped_existing=%s errors=%s",
        org_id, ingested, skipped_existing, len(errors),
    )
    return {"ingested": ingested, "skipped_existing": skipped_existing, "errors": errors}


__all__ = [
    "backfill_olx_leads",
    "get_or_create_olx_source",
    "ingest_olx_lead",
    "ingest_olx_payload",
    "store_olx_lead",
]
