"""Inbound ImovelWeb deliveries — persist-then-answer-then-process.

The same shape as the OLX sibling, forced by a tighter contract:

* the vendor allows **1.5 seconds** for our response, and a slower answer is
  scored an error regardless of the status code;
* a failure is retried until **72 hours** have passed, then the callback
  goes ``VENCIDO``;
* but unlike OLX there is a **pull API**, so a miss is recoverable —
  reconciliation, not the webhook, is the durability guarantee here. That is
  the fact that makes the tight budget survivable, and it is why
  ``imovelweb_lead_events.source`` records whether a row arrived by callback
  or by reconcile.

Every collaborator is a keyword DI seam: a test drives the real handler path
with fakes, and nothing about this module is patched.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from time import perf_counter
from typing import Any, Callable, Optional
from uuid import UUID

from noctusai_lib.integrations.imovelweb import (
    ImovelWebLead,
    parse_imovelweb_callback,
)

from app.modules.portal_leads.services import imovelweb_ingest_service

logger = logging.getLogger(__name__)

_EVENTS = "imovelweb_lead_events"
_AGENCIES = "imovelweb_agencies"

STATUS_RECEIVED = "received"
STATUS_PROCESSED = "processed"
STATUS_ERROR = "error"
STATUS_UNRESOLVED = "unresolved"
STATUS_IGNORED = "ignored"

PENDING_STATUSES = (STATUS_RECEIVED, STATUS_ERROR, STATUS_UNRESOLVED)

SOURCE_CALLBACK = "callback"
SOURCE_RECONCILE = "reconcile"

#: Give up after this many attempts. The row stays for inspection — it is
#: never deleted, because "we failed to process a real lead" is exactly what
#: an operator needs to be able to find.
MAX_ATTEMPTS = 5

#: Two-thirds of the vendor's 1.5s limit. Deliberately not the limit itself:
#: by the time we are AT 1.5s the lead is already scored an error, so the
#: number worth alerting on is the one that still leaves room to react.
RESPONSE_BUDGET_SECONDS = 1.0


@dataclass(frozen=True)
class ProcessResult:
    """Outcome of processing one delivery."""

    event_id: str
    status: str
    created: bool = False
    lead_id: Optional[str] = None
    source_slug: Optional[str] = None
    detail: Optional[str] = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ImovelWebWebhookService:
    """Record → resolve org → ingest, with the inbox as the safety net."""

    def __init__(
        self,
        *,
        client: Any,
        org_resolver: Optional[Callable[[Any, ImovelWebLead], Optional[UUID]]] = None,
        ingest_fn: Optional[Callable[[Any, UUID, ImovelWebLead], dict]] = None,
        default_org_id: Optional[UUID] = None,
        dedup: Any = None,
    ) -> None:
        self._client = client
        self._org_resolver = org_resolver or self._resolve_org
        self._ingest = ingest_fn or imovelweb_ingest_service.ingest_imovelweb_lead
        self._default_org_id = default_org_id
        self._dedup = dedup
        #: Round-trips made on the REQUEST path. Read by the router to log a
        #: budget warning, and asserted by tests — a wall-clock assertion
        #: would be flaky, but "how many times did we hit the database before
        #: answering" is deterministic and is the thing that actually varies.
        self.calls_before_response = 0

    # ── inbox ────────────────────────────────────────────────────────

    def _table(self, name: str):
        return self._client.table(name)

    def record_event(
        self,
        lead: ImovelWebLead,
        *,
        source: str = SOURCE_CALLBACK,
    ) -> bool:
        """Persist the delivery. Returns False when already seen.

        Called BEFORE the response goes out, so a crash mid-processing still
        leaves the body recoverable.

        NOC-REMEDIATE[perf-single-write]: this is a SELECT followed by an
        INSERT — two round-trips inside a 1.5-second budget. Collapsing it
        into one `upsert(..., ignore_duplicates=True)` is the obvious fix and
        is deliberately NOT taken yet: `MockRequestBuilder.upsert()` is a
        documented no-op (`noctusai_lib.testing.mocks`), so an upsert-based
        path tests green and duplicates in production. The prerequisite is
        teaching the mock conflict-target propagation, which changes test
        behaviour at ~70 call sites across the fleet and is therefore its own
        piece of work, not a side effect of this one. Gate 1.9 measures
        whether the two round-trips actually threaten the budget before that
        work is scheduled.
        """
        existing = self._table(_EVENTS).select("id").eq("id", lead.event_id).execute()
        self.calls_before_response += 1
        if list(existing.data or []):
            return False
        self._table(_EVENTS).insert({
            "id": lead.event_id,
            "org_id": None,
            "event_type": lead.event_type,
            "codigo_imobiliaria": lead.codigo_imobiliaria,
            "client_listing_id": lead.client_listing_id,
            "lead_origin": lead.lead_origin,
            "callback_language": lead.callback_language,
            "source": source,
            "payload": lead.raw,
            "status": STATUS_RECEIVED,
            "attempts": 0,
            "received_at": _now(),
        }).execute()
        self.calls_before_response += 1
        return True

    def _update_event(self, event_id: str, **fields: Any) -> None:
        self._table(_EVENTS).update(fields).eq("id", event_id).execute()

    def _get_event(self, event_id: str) -> Optional[dict]:
        resp = self._table(_EVENTS).select("*").eq("id", event_id).execute()
        rows = list(resp.data or [])
        return rows[0] if rows else None

    def is_duplicate(self, event_id: str) -> bool:
        """Redis-backed first line of dedup, if a store was injected.

        Three layers total (Redis → the `imovelweb_lead_events` PK → the
        `(org, 'imovelweb', eventId)` unique index on `leads`), because
        duplicate delivery is ORDINARY traffic here: the vendor retries for
        72 hours AND the reconcile job re-reads the same window, so the same
        event legitimately arrives twice by two different paths. A Redis
        outage degrades to the DB layers rather than failing.
        """
        if self._dedup is None:
            return False
        try:
            claimed = self._dedup.claim(event_id)
        except Exception:  # noqa: BLE001 — dedup is an optimisation, never a gate
            logger.warning(
                "imovelweb-webhook: dedup unavailable — relying on DB idempotency"
            )
            return False
        return not claimed

    # ── org resolution ───────────────────────────────────────────────

    def _resolve_org(self, client: Any, lead: ImovelWebLead) -> Optional[UUID]:
        """Which tenant does this lead belong to?

        Four rungs, then a refusal. Never a guess — a misplaced lead is one
        client's customer landing in another client's CRM, which is worse
        than a lead that needs a human to place it.

        1. **`codigoImobiliaria` → `imovelweb_agencies.org_id`.** The strong
           rung, and the reason this integration beats the OLX pipe: WE
           choose the agency code at onboarding (it goes in the vendor's
           login-button URL), so resolution is a pure lookup rather than an
           inference. ⚠️ Only the PT/ES/EN bodies carry this field — the EN2
           body does not, which is the language trade-off recorded in
           `KB § INTEGRATIONS/imovelweb.md § 2`. On EN2 this rung is simply
           unavailable and the chain starts at rung 2.
        2. `clientListingId` → `imoveis.codigo` → `org_id`. Our own listing
           code, so it identifies the advertiser when present.
        3. `internalReference` → `imoveis.codigo`. Weaker: it is the code the
           imobiliária uses in the VENDOR's panel, which may not be ours —
           hence third, not second.
        4. The configured single org, for single-tenant deployments.

        Runs in the BACKGROUND task, never before the response: three
        potential database reads do not fit a 1.5-second budget alongside
        the durable write.
        """
        if lead.codigo_imobiliaria:
            resp = (
                client.table(_AGENCIES)
                .select("org_id")
                .eq("codigo_imobiliaria", lead.codigo_imobiliaria)
                .execute()
            )
            rows = list(resp.data or [])
            if rows and rows[0].get("org_id"):
                return UUID(str(rows[0]["org_id"]))

        for code in (lead.client_listing_id, lead.internal_reference):
            if not code:
                continue
            resp = (
                client.table("imoveis").select("org_id").eq("codigo", code).execute()
            )
            rows = list(resp.data or [])
            if rows and rows[0].get("org_id"):
                return UUID(str(rows[0]["org_id"]))

        return self._default_org_id

    # ── processing ───────────────────────────────────────────────────

    def process_lead(self, lead: ImovelWebLead) -> ProcessResult:
        """Resolve + ingest one recorded delivery, updating its row."""
        event = self._get_event(lead.event_id)
        attempts = int((event or {}).get("attempts") or 0) + 1

        org_id = self._org_resolver(self._client, lead)
        if org_id is None:
            self._update_event(
                lead.event_id,
                status=STATUS_UNRESOLVED,
                attempts=attempts,
                error=(
                    "could not resolve the org — agency code "
                    f"{lead.codigo_imobiliaria!r} is not in imovelweb_agencies, "
                    f"listing code {lead.client_listing_id!r} matched no imovel, "
                    "and no default org is configured (IMOVELWEB_LEADS_ORG_ID)"
                ),
            )
            logger.warning(
                "imovelweb-webhook: event %s unresolved (agency=%s listing=%s)",
                lead.event_id, lead.codigo_imobiliaria, lead.client_listing_id,
            )
            return ProcessResult(lead.event_id, STATUS_UNRESOLVED,
                                 detail="org-unresolved")

        try:
            result = self._ingest(self._client, org_id, lead)
        except Exception as exc:  # noqa: BLE001 — recorded, never swallowed
            self._update_event(
                lead.event_id,
                org_id=str(org_id),
                status=STATUS_ERROR,
                attempts=attempts,
                error=str(exc)[:1000],
            )
            logger.exception("imovelweb-webhook: ingest failed for %s", lead.event_id)
            return ProcessResult(lead.event_id, STATUS_ERROR, detail=str(exc)[:200])

        self._update_event(
            lead.event_id,
            org_id=str(org_id),
            status=STATUS_PROCESSED,
            attempts=attempts,
            error=None,
            processed_at=_now(),
        )
        return ProcessResult(
            lead.event_id,
            STATUS_PROCESSED,
            created=bool(result.get("created")),
            lead_id=str((result.get("lead") or {}).get("id") or "") or None,
            source_slug=result.get("source_slug"),
        )

    def record_unparseable(self, payload: Any, reason: str) -> None:
        """A body we cannot key on is still evidence.

        It cannot go in the inbox (whose PK is the vendor's own event id), so
        it is logged loudly with the body. "Arrived and we could not read it"
        and "never arrived" are opposite problems — one is our parser, the
        other is the registration — and only a log distinguishes them.
        """
        logger.warning("imovelweb-webhook: unusable delivery (%s): %r", reason, payload)

    # ── retry drain ──────────────────────────────────────────────────

    def drain_pending(self, limit: int = 100) -> dict[str, Any]:
        """Re-process events left pending by an earlier failure.

        Driven by the scheduler. Bounded by ``MAX_ATTEMPTS`` so a
        permanently-bad row does not spin forever, and never deleted — an
        unprocessable real lead is precisely what an operator must be able to
        find.
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
            lead = parse_imovelweb_callback(
                row.get("payload") or {}, language=row.get("callback_language")
            )
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
            "imovelweb-webhook.drain_pending: examined=%s processed=%s pending=%s "
            "exhausted=%s", len(rows), processed, still_pending, exhausted,
        )
        return {
            "examined": len(rows),
            "processed": processed,
            "still_pending": still_pending,
            "exhausted": exhausted,
        }


class ResponseBudget:
    """Measure the request path against the vendor's 1.5-second limit.

    A context manager rather than a decorator so the measured region is
    exactly the pre-response work and is visible at the call site — the whole
    point is that someone reading the router can see where the budget ends.

    Over-budget is logged as a WARNING and reported in the response body. The
    vendor ignores our body, so this is for us: a receiver answering in 1.8s
    is not slow, it is losing leads, and the only way that becomes visible
    before Gate 1.9 measures it is if we say so on every request.
    """

    def __init__(self, budget_seconds: float = RESPONSE_BUDGET_SECONDS) -> None:
        self.budget_seconds = budget_seconds
        self.elapsed_ms: float = 0.0
        self._started: float = 0.0

    def __enter__(self) -> "ResponseBudget":
        self._started = perf_counter()
        return self

    def __exit__(self, *exc_info) -> bool:
        self.elapsed_ms = round((perf_counter() - self._started) * 1000, 1)
        if self.exceeded:
            logger.warning(
                "imovelweb-webhook: pre-response work took %.1fms, over the %.0fms "
                "budget — the vendor allows 1500ms total and scores a slower "
                "answer an error regardless of status code",
                self.elapsed_ms, self.budget_seconds * 1000,
            )
        return False

    @property
    def exceeded(self) -> bool:
        return self.elapsed_ms > self.budget_seconds * 1000


__all__ = [
    "MAX_ATTEMPTS",
    "PENDING_STATUSES",
    "RESPONSE_BUDGET_SECONDS",
    "SOURCE_CALLBACK",
    "SOURCE_RECONCILE",
    "STATUS_ERROR",
    "STATUS_IGNORED",
    "STATUS_PROCESSED",
    "STATUS_RECEIVED",
    "STATUS_UNRESOLVED",
    "ImovelWebWebhookService",
    "ProcessResult",
    "ResponseBudget",
]
