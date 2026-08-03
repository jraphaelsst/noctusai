"""Meta Lead-Ads webhook ingest — turn a verified `leadgen` delivery into a
persisted lead, a unified-base row, and an operator alert.

WHY THIS IS SHAPED persist-then-200-then-process
────────────────────────────────────────────────
Meta's delivery contract punishes both failure modes:
  • it RETRIES any non-2xx with backoff and can eventually DISABLE the
    subscription entirely, and
  • it NEVER re-sends after a 200.
So "return 500 and let Meta retry" risks losing the subscription, while
"return 200 and hope" loses the lead on any transient Graph error. The only
safe shape is: verify the signature (the ONE legitimate rejection) → write
the raw payload to ``meta_webhook_events`` → return 200 → process. A
processing failure is then a row, not a lost lead, and ``drain_pending``
re-drives it.

WHY ENRICHMENT IS MANDATORY
───────────────────────────
The webhook body carries NO lead PII — only a ``leadgen_id``. Meta requires
a second authenticated call (``GET /{leadgen_id}``, gated on
``leads_retrieval``) to read the field data. That is what
``adapter.get_lead`` is for; there is no shortcut.

DEDUP — three layers, deliberately
──────────────────────────────────
  1. Redis SETNX (``get_webhook_dedup``) — keeps the HOT duplicate path off
     Graph entirely, since ``get_lead`` is a real network call.
  2. ``meta_webhook_events.id`` PK — survives a restart and a Redis
     eviction; this is the correctness layer.
  3. ``meta_ads_leads.id`` upsert-on-conflict — the final backstop, and the
     reason the webhook and the daily cron can both run without duplicating.
Layer 1 is an optimization. Layers 2 and 3 are the guarantee.

ORG RESOLUTION
──────────────
There is no page→org mapping today: the System-User token is
workspace-global and ``META_ADS_ORG_ID`` names the single owning org. So we
resolve ``meta_ads_lead_forms.page_id → org_id`` FIRST — a real DB lookup
that returns the same org today, but starts returning different orgs at
roadmap Phase 4 with NO change here — then fall back to the configured org.
If neither resolves we park the row as ``unresolved`` rather than guessing:
a wrong guess writes one tenant's lead PII into another tenant's RLS scope,
which is exactly the leak the 2026-07-23 scheduler fix exists to prevent.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any
from uuid import UUID

from noctusai_lib.integrations.meta import MetaGraphError
from noctusai_lib.integrations.meta.leadgen_webhook import LeadgenEvent

logger = logging.getLogger(__name__)

_SCHEMA = "social_wiring"
_EVENTS = "meta_webhook_events"
_FORMS = "meta_ads_lead_forms"

#: Terminal + retryable statuses on ``meta_webhook_events``.
STATUS_RECEIVED = "received"
STATUS_PROCESSED = "processed"
STATUS_ERROR = "error"
STATUS_UNRESOLVED = "unresolved"
STATUS_IGNORED = "ignored"

#: Statuses the retry job re-drives.
PENDING_STATUSES = (STATUS_RECEIVED, STATUS_ERROR, STATUS_UNRESOLVED)

#: Give up re-driving after this many attempts. A row that fails five times
#: is a bug or a permanently-deleted lead (Meta purges after 90 days), not a
#: transient blip — it stays queryable as `error` rather than being retried
#: forever or silently dropped.
MAX_ATTEMPTS = 5


class LeadgenWebhookService:
    """Per-request collaborator for the Meta leadgen receiver.

    Every collaborator is a keyword seam (``KB § PATTERNS/backend/di-test-seam.md``)
    so tests exercise the REAL resolution rather than patching module globals.
    """

    def __init__(
        self,
        *,
        admin_supabase: Any,
        adapter_factory: Any = None,
        leads_sync_factory: Any = None,
        dedup: Any = None,
        org_resolver: Any = None,
    ) -> None:
        self._admin = admin_supabase
        self._adapter_factory = adapter_factory
        self._leads_sync_factory = leads_sync_factory
        self._dedup = dedup
        self._org_resolver = org_resolver

    # ─── inbox ─────────────────────────────────────────────────────────
    def record_event(self, event: LeadgenEvent) -> bool:
        """Persist the verified delivery. Returns True when this is a NEW
        row, False when the PK already existed (a Meta retry).

        Deliberately runs BEFORE dedup and BEFORE org resolution: the raw
        payload is captured even for a duplicate or an unmappable page, so
        "did Meta actually call us?" always has an answer. That question was
        unanswerable before this table existed — a stale `synced_at` looked
        identical whether zero leads arrived or every delivery was dropped.
        """
        row = {
            "id": event.leadgen_id,
            "page_id": event.page_id,
            "form_id": event.form_id,
            "ad_id": event.ad_id,
            "created_time": event.created_time.isoformat() if event.created_time else None,
            "payload": event.raw,
            "status": STATUS_RECEIVED,
            "received_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            (
                self._admin.schema(_SCHEMA).table(_EVENTS)
                .insert(row)
                .execute()
            )
            return True
        except Exception as exc:  # noqa: BLE001
            # A PK conflict is the expected duplicate path, not an error.
            # Anything else still must not raise — the caller owes Meta a
            # 200, and an un-inserted row is strictly better than a retry
            # storm that can cost us the subscription.
            if _is_duplicate_key(exc):
                logger.info(
                    "meta-leadgen: duplicate delivery for leadgen_id=%s", event.leadgen_id
                )
                return False
            logger.exception(
                "meta-leadgen: could not record inbox row for leadgen_id=%s",
                event.leadgen_id,
            )
            return False

    def _set_status(
        self, leadgen_id: str, *, status: str, error: str | None = None,
        org_id: UUID | None = None, bump_attempts: bool = False,
    ) -> None:
        patch: dict[str, Any] = {"status": status, "error": error}
        if org_id is not None:
            patch["org_id"] = str(org_id)
        if status == STATUS_PROCESSED:
            patch["processed_at"] = datetime.now(timezone.utc).isoformat()
        if bump_attempts:
            patch["attempts"] = self._current_attempts(leadgen_id) + 1
        try:
            (
                self._admin.schema(_SCHEMA).table(_EVENTS)
                .update(patch).eq("id", leadgen_id).execute()
            )
        except Exception:  # noqa: BLE001
            logger.exception("meta-leadgen: could not update inbox status for %s", leadgen_id)

    def _current_attempts(self, leadgen_id: str) -> int:
        try:
            resp = (
                self._admin.schema(_SCHEMA).table(_EVENTS)
                .select("attempts").eq("id", leadgen_id).limit(1).execute()
            )
            rows = resp.data or []
            return int(rows[0].get("attempts") or 0) if rows else 0
        except Exception:  # noqa: BLE001
            return 0

    # ─── org resolution ────────────────────────────────────────────────
    def resolve_org(self, event: LeadgenEvent) -> UUID | None:
        """page_id → org_id via the persisted forms table, else the single
        configured org. ``None`` ⇒ park as ``unresolved``, never guess."""
        if self._org_resolver is not None:
            return self._org_resolver(event)
        if event.page_id:
            try:
                resp = (
                    self._admin.schema(_SCHEMA).table(_FORMS)
                    .select("org_id").eq("page_id", event.page_id).limit(1).execute()
                )
                rows = resp.data or []
                if rows and rows[0].get("org_id"):
                    return UUID(str(rows[0]["org_id"]))
            except Exception:  # noqa: BLE001
                logger.exception("meta-leadgen: page→org lookup failed for %s", event.page_id)
        from app.services.app_config_store import resolve_meta_ads_config

        _token, _account, raw_org = resolve_meta_ads_config()
        if not raw_org:
            return None
        try:
            return UUID(str(raw_org))
        except ValueError:
            logger.warning("meta-leadgen: META_ADS_ORG_ID=%r is not a valid UUID", raw_org)
            return None

    # ─── form schema (with cold-form fallback) ─────────────────────────
    def resolve_form(self, form_id: str | None, *, page_id: str | None, adapter: Any):
        """Return ``(form, key_types)`` for :meth:`LeadsSyncService.upsert_lead`.

        Reads the persisted ``meta_ads_lead_forms`` row first — it already
        stores ``questions``, so the common path costs zero Graph calls.

        🔴 COLD-FORM FALLBACK. A brand-new form fires its first webhook
        before any sync has seen it. Without this branch ``key_types`` is
        empty, so NOTHING promotes to ``full_name``/``email``/``phone`` —
        the lead lands with null contact fields and the funnel card titles
        as the generic fallback. Silent, and worst on exactly the leads that
        matter most: the first ones from a newly-launched campaign. One
        extra Graph call on first sighting is the right trade.
        """
        if not form_id:
            return None, {}
        try:
            resp = (
                self._admin.schema(_SCHEMA).table(_FORMS)
                .select("id,org_id,page_id,name,questions")
                .eq("id", form_id).limit(1).execute()
            )
            rows = resp.data or []
        except Exception:  # noqa: BLE001
            logger.exception("meta-leadgen: form lookup failed for %s", form_id)
            rows = []

        if rows:
            row = rows[0]
            questions = row.get("questions") or []
            key_types = {q.get("key"): q.get("type") for q in questions if q.get("key")}
            form = SimpleNamespace(
                id=row["id"], name=row.get("name"), page_id=row.get("page_id") or page_id
            )
            return form, key_types

        form_obj = adapter.get_leadgen_form(form_id, page_id=page_id)
        key_types = {q.key: q.type for q in form_obj.questions if q.key}
        logger.info(
            "meta-leadgen: cold form %s — fetched schema on first sighting", form_id
        )
        return form_obj, key_types

    # ─── the pipeline ──────────────────────────────────────────────────
    def process_event(self, event: LeadgenEvent) -> str:
        """Enrich → upsert → normalize → notify. Returns the terminal status.

        NEVER raises: the caller owes Meta a 200 regardless, and every
        failure mode is recorded on the inbox row instead.
        """
        org_id = self.resolve_org(event)
        if org_id is None:
            logger.warning(
                "meta-leadgen: no org for page_id=%s — parked as unresolved "
                "(set META_ADS_ORG_ID, or sync the form so page→org resolves)",
                event.page_id,
            )
            self._set_status(event.leadgen_id, status=STATUS_UNRESOLVED)
            return STATUS_UNRESOLVED

        try:
            adapter = self._build_adapter(org_id)
            form, key_types = self.resolve_form(
                event.form_id, page_id=event.page_id, adapter=adapter
            )
            lead = adapter.get_lead(event.leadgen_id, page_id=event.page_id)
            if form is None:
                form = SimpleNamespace(
                    id=lead.form_id or event.form_id, name=None, page_id=event.page_id
                )
            svc = self._build_leads_sync()
            svc.upsert_lead(lead, org_id=org_id, form=form, key_types=key_types)
        except MetaGraphError as exc:
            detail = str(exc)
            if getattr(exc, "is_permission", False):
                detail = (
                    f"{detail} — the token is missing `leads_retrieval`; lead RECORDS "
                    "cannot be read until that scope is granted"
                )
            logger.warning("meta-leadgen: enrich/upsert failed for %s: %s",
                           event.leadgen_id, detail)
            self._set_status(event.leadgen_id, status=STATUS_ERROR,
                             error=detail, org_id=org_id, bump_attempts=True)
            return STATUS_ERROR
        except Exception as exc:  # noqa: BLE001
            logger.exception("meta-leadgen: unexpected failure for %s", event.leadgen_id)
            self._set_status(event.leadgen_id, status=STATUS_ERROR,
                             error=str(exc), org_id=org_id, bump_attempts=True)
            return STATUS_ERROR

        self._set_status(event.leadgen_id, status=STATUS_PROCESSED, org_id=org_id)
        return STATUS_PROCESSED

    # ─── collaborators ─────────────────────────────────────────────────
    def _build_adapter(self, org_id: UUID) -> Any:
        if self._adapter_factory is not None:
            return self._adapter_factory(org_id=str(org_id))
        from app.services.meta import get_meta_adapter

        return get_meta_adapter(org_id=str(org_id))

    def _build_leads_sync(self) -> Any:
        if self._leads_sync_factory is not None:
            return self._leads_sync_factory(admin_supabase=self._admin)
        from app.modules.meta_ads.services.leads_sync_service import LeadsSyncService

        return LeadsSyncService(admin_supabase=self._admin)

    def claim(self, leadgen_id: str) -> bool:
        """Redis SETNX pre-filter. True ⇒ we own this delivery.

        Fails SAFE: an unreachable Redis returns True (proceed) rather than
        False (silently drop a real lead) — layers 2 and 3 still guarantee
        idempotency, so the worst case is a redundant Graph call, not a
        duplicate or a loss.
        """
        if self._dedup is None:
            return True
        try:
            return bool(self._dedup.claim(leadgen_id))
        except Exception:  # noqa: BLE001
            logger.warning("meta-leadgen: dedup backend unavailable — proceeding")
            return True

    # ─── retry + retention ─────────────────────────────────────────────
    def drain_pending(self, *, limit: int = 100) -> dict[str, int]:
        """Re-drive inbox rows the receiver could not finish. The reason a
        transient Graph blip is not a lost lead."""
        try:
            resp = (
                self._admin.schema(_SCHEMA).table(_EVENTS)
                .select("id,page_id,form_id,ad_id,created_time,payload,attempts")
                .in_("status", list(PENDING_STATUSES))
                .lt("attempts", MAX_ATTEMPTS)
                .order("received_at")
                .limit(limit)
                .execute()
            )
            rows = resp.data or []
        except Exception:  # noqa: BLE001
            logger.exception("meta-leadgen: could not read pending inbox rows")
            return {"scanned": 0, "processed": 0, "failed": 0}

        processed = failed = 0
        for row in rows:
            event = _event_from_row(row)
            if self.process_event(event) == STATUS_PROCESSED:
                processed += 1
            else:
                failed += 1
        if rows:
            logger.info(
                "meta-leadgen retry: scanned=%d processed=%d failed=%d",
                len(rows), processed, failed,
            )
        return {"scanned": len(rows), "processed": processed, "failed": failed}

    def purge_processed(self, *, older_than_days: int = 90) -> int:
        """LGPD retention: drop processed inbox rows past the window.

        90 days deliberately mirrors Meta's OWN lead retention, so we never
        hold lead PII in the inbox longer than Meta does. The durable copy
        lives in ``meta_ads_leads``; this row is only ever delivery-debugging
        material.
        """
        cutoff = (datetime.now(timezone.utc) - timedelta(days=older_than_days)).isoformat()
        try:
            resp = (
                self._admin.schema(_SCHEMA).table(_EVENTS)
                .delete().eq("status", STATUS_PROCESSED).lt("processed_at", cutoff).execute()
            )
            return len(resp.data or [])
        except Exception:  # noqa: BLE001
            logger.exception("meta-leadgen: inbox purge failed")
            return 0


def _event_from_row(row: dict[str, Any]) -> LeadgenEvent:
    """Rebuild a `LeadgenEvent` from a stored inbox row (retry path)."""
    created = row.get("created_time")
    dt: datetime | None = None
    if created:
        try:
            dt = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
        except ValueError:
            dt = None
    return LeadgenEvent(
        leadgen_id=str(row["id"]),
        page_id=row.get("page_id"),
        form_id=row.get("form_id"),
        ad_id=row.get("ad_id"),
        adgroup_id=None,
        created_time=dt,
        raw=row.get("payload") or {},
    )


def _is_duplicate_key(exc: Exception) -> bool:
    """PostgREST surfaces a PK conflict as SQLSTATE 23505 / 'duplicate key'.

    Matched on the message because the Supabase client raises a generic
    APIError rather than a typed conflict — narrow enough to not swallow a
    real failure, since anything that is NOT a duplicate falls through to the
    exception branch and gets logged.
    """
    text = str(exc).lower()
    return "23505" in text or "duplicate key" in text


__all__ = [
    "LeadgenWebhookService",
    "MAX_ATTEMPTS",
    "PENDING_STATUSES",
    "STATUS_ERROR",
    "STATUS_IGNORED",
    "STATUS_PROCESSED",
    "STATUS_RECEIVED",
    "STATUS_UNRESOLVED",
]
