"""Inbound Grupo OLX lead deliveries — persist-then-200-then-process.

The shape is forced by the vendor's contract, not chosen:

* OLX reads **only** our HTTP status code (the body is explicitly
  ignored), so we must answer fast and correctly;
* a non-2xx is retried 3× and then the lead is **discarded after 14
  days**, with no replay API;
* therefore the durable inbox row — not the status code — is what makes a
  processing failure recoverable.

Every collaborator is a keyword DI seam, mirroring
``meta_ads/services/leadgen_webhook_service.py``: a test drives the real
handler path with fakes, and nothing about this module is patched.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Optional
from uuid import UUID

from noctusai_lib.integrations.olx import OlxLead, parse_olx_lead_webhook

from app.modules.portal_leads.services import olx_ingest_service

logger = logging.getLogger(__name__)

_EVENTS = "olx_lead_events"

STATUS_RECEIVED = "received"
STATUS_PROCESSED = "processed"
STATUS_ERROR = "error"
STATUS_UNRESOLVED = "unresolved"
STATUS_IGNORED = "ignored"

PENDING_STATUSES = (STATUS_RECEIVED, STATUS_ERROR, STATUS_UNRESOLVED)

#: Give up after this many attempts. The row stays for inspection — it is
#: never deleted, because "we failed to process a real lead" is exactly
#: the thing an operator needs to be able to find.
MAX_ATTEMPTS = 5


@dataclass(frozen=True)
class ProcessResult:
    """Outcome of processing one delivery."""

    origin_lead_id: str
    status: str
    created: bool = False
    lead_id: Optional[str] = None
    detail: Optional[str] = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class OlxWebhookService:
    """Record → resolve org → ingest, with the inbox as the safety net."""

    def __init__(
        self,
        *,
        client: Any,
        org_resolver: Optional[Callable[[Any, OlxLead], Optional[UUID]]] = None,
        ingest_fn: Optional[Callable[[Any, UUID, OlxLead], dict]] = None,
        default_org_id: Optional[UUID] = None,
        dedup: Any = None,
    ) -> None:
        self._client = client
        self._org_resolver = org_resolver or self._resolve_org
        self._ingest = ingest_fn or olx_ingest_service.ingest_olx_lead
        self._default_org_id = default_org_id
        self._dedup = dedup

    # ── inbox ────────────────────────────────────────────────────────

    def _table(self, name: str):
        return self._client.table(name)

    def record_event(self, lead: OlxLead) -> bool:
        """Persist the delivery. Returns False when already seen.

        Called BEFORE any processing and before the 200 goes out, so a
        crash mid-processing still leaves the body recoverable.
        """
        existing = (
            self._table(_EVENTS).select("id").eq("id", lead.origin_lead_id).execute()
        )
        if list(existing.data or []):
            return False
        self._table(_EVENTS).insert({
            "id": lead.origin_lead_id,
            "org_id": None,
            "client_listing_id": lead.client_listing_id,
            "lead_origin": lead.lead_origin or None,
            "lead_type": lead.lead_type,
            "payload": lead.raw,
            "status": STATUS_RECEIVED,
            "attempts": 0,
            "received_at": _now(),
        }).execute()
        return True

    def _update_event(self, origin_lead_id: str, **fields: Any) -> None:
        self._table(_EVENTS).update(fields).eq("id", origin_lead_id).execute()

    def _get_event(self, origin_lead_id: str) -> Optional[dict]:
        resp = self._table(_EVENTS).select("*").eq("id", origin_lead_id).execute()
        rows = list(resp.data or [])
        return rows[0] if rows else None

    def is_duplicate(self, origin_lead_id: str) -> bool:
        """Redis-backed first line of dedup, if a store was injected.

        Three layers total (Redis → `olx_lead_events` PK → the
        `(org, source, external id)` unique index on `leads`), because
        duplicate delivery is ORDINARY traffic here, not an anomaly. A
        Redis outage degrades to the DB layers rather than failing.
        """
        if self._dedup is None:
            return False
        try:
            return not self._dedup.claim(origin_lead_id)
        except Exception:  # noqa: BLE001 — dedup is an optimisation, never a gate
            logger.warning("olx-webhook: dedup unavailable — relying on DB idempotency")
            return False

    # ── org resolution ───────────────────────────────────────────────

    def _resolve_org(self, client: Any, lead: OlxLead) -> Optional[UUID]:
        """Which tenant does this lead belong to?

        One secret and one endpoint serve the whole CRM, so the payload
        has to tell us. In order, never guessing:

        1. `clientListingId` → `imoveis.codigo` → `org_id`. This is OUR
           listing code, published by us in the feed, so it is the only
           field that genuinely identifies the advertiser.
        2. the configured single org (`OLX_LEADS_ORG_ID`), for the
           single-tenant deployments this starts life in.

        Returns ``None`` when neither answers — the caller parks the
        event as `unresolved` and writes nothing. A guessed org would
        leak one client's lead into another client's CRM, which is worse
        than a lead that needs a human to place it.
        """
        if lead.client_listing_id:
            resp = (
                client.table("imoveis")
                .select("org_id")
                .eq("codigo", lead.client_listing_id)
                .execute()
            )
            rows = list(resp.data or [])
            if rows and rows[0].get("org_id"):
                return UUID(str(rows[0]["org_id"]))
        return self._default_org_id

    # ── processing ───────────────────────────────────────────────────

    def process_lead(self, lead: OlxLead) -> ProcessResult:
        """Resolve + ingest one recorded delivery, updating its row."""
        event = self._get_event(lead.origin_lead_id)
        attempts = int((event or {}).get("attempts") or 0) + 1

        org_id = self._org_resolver(self._client, lead)
        if org_id is None:
            self._update_event(
                lead.origin_lead_id,
                status=STATUS_UNRESOLVED,
                attempts=attempts,
                error=(
                    "could not resolve the org — clientListingId "
                    f"{lead.client_listing_id!r} matched no imovel and no default "
                    "org is configured (OLX_LEADS_ORG_ID)"
                ),
            )
            logger.warning(
                "olx-webhook: lead %s unresolved (clientListingId=%s)",
                lead.origin_lead_id, lead.client_listing_id,
            )
            return ProcessResult(lead.origin_lead_id, STATUS_UNRESOLVED,
                                 detail="org-unresolved")

        try:
            result = self._ingest(self._client, org_id, lead)
        except Exception as exc:  # noqa: BLE001 — recorded, never swallowed
            self._update_event(
                lead.origin_lead_id,
                org_id=str(org_id),
                status=STATUS_ERROR,
                attempts=attempts,
                error=str(exc)[:1000],
            )
            logger.exception("olx-webhook: ingest failed for %s", lead.origin_lead_id)
            return ProcessResult(lead.origin_lead_id, STATUS_ERROR, detail=str(exc)[:200])

        self._update_event(
            lead.origin_lead_id,
            org_id=str(org_id),
            status=STATUS_PROCESSED,
            attempts=attempts,
            error=None,
            processed_at=_now(),
        )
        return ProcessResult(
            lead.origin_lead_id,
            STATUS_PROCESSED,
            created=bool(result.get("created")),
            lead_id=str((result.get("lead") or {}).get("id") or "") or None,
        )

    def record_unparseable(self, payload: Any, reason: str) -> None:
        """A body we cannot key on is still evidence.

        It cannot go in the inbox (whose PK is the vendor's own id), so it
        is logged loudly with the body. "Arrived and we could not read it"
        and "never arrived" are opposite problems — one is our parser, the
        other is the registration — and only a log distinguishes them.
        """
        logger.warning("olx-webhook: unusable delivery (%s): %r", reason, payload)

    # ── retry drain ──────────────────────────────────────────────────

    def drain_pending(self, limit: int = 100) -> dict[str, Any]:
        """Re-process events left pending by an earlier failure.

        Driven by the scheduler every 15 minutes. Bounded by
        ``MAX_ATTEMPTS`` so a permanently-bad row does not spin forever,
        and it is never deleted — an unprocessable real lead is precisely
        what an operator must be able to find.
        """
        resp = (
            self._table(_EVENTS)
            .select("*")
            .in_("status", list(PENDING_STATUSES))
            .order("received_at")
            .limit(limit)
            .execute()
        )
        rows = list(resp.data or [])
        processed = 0
        still_pending = 0
        exhausted = 0

        for row in rows:
            if int(row.get("attempts") or 0) >= MAX_ATTEMPTS:
                exhausted += 1
                continue
            lead = parse_olx_lead_webhook(row.get("payload") or {})
            if lead is None:
                self._update_event(
                    row["id"], status=STATUS_IGNORED,
                    error="stored payload is no longer parseable",
                )
                continue
            result = self.process_lead(lead)
            if result.status == STATUS_PROCESSED:
                processed += 1
            else:
                still_pending += 1

        logger.info(
            "olx-webhook.drain_pending: examined=%s processed=%s pending=%s exhausted=%s",
            len(rows), processed, still_pending, exhausted,
        )
        return {
            "examined": len(rows),
            "processed": processed,
            "still_pending": still_pending,
            "exhausted": exhausted,
        }


__all__ = [
    "MAX_ATTEMPTS",
    "PENDING_STATUSES",
    "STATUS_ERROR",
    "STATUS_IGNORED",
    "STATUS_PROCESSED",
    "STATUS_RECEIVED",
    "STATUS_UNRESOLVED",
    "OlxWebhookService",
    "ProcessResult",
]
