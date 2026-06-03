"""
Agenda service — agenda_events CRUD + Google Calendar sync seam.

GCal sync seam (NOC-REMEDIATE[orbity-agenda-gcal]):
  The agenda service holds a clean named seam for Google Calendar sync.
  A `CalendarAdapter` (from noctusai_lib.integrations.google_calendar)
  is injected at construction time; the default is `FakeCalendarAdapter`
  (no-op in-memory, fully testable).

  When a real CalendarAdapter is wired (e.g. via `get_calendar_adapter`
  with an OAuth or service-account credential resolver), `sync_to_gcal`
  creates the event in Google Calendar and stores the returned event ID
  in `agenda_events.gcal_event_id`.

  The service NEVER silently stubs — the seam is named, tested with
  the Fake, and ready for the Real when credentials are wired.

  NOC-REMEDIATE[orbity-agenda-gcal]: Wire a real CalendarAdapter by
  passing `calendar_adapter=get_calendar_adapter(resolver, tenant_id=…)`
  to AgendaService. Requires: (1) Google OAuth consent + token store
  integration in orbity.settings; (2) per-org credential resolver;
  (3) calendar_id storage (per-org config table or org settings JSON).
  See KB § INTEGRATIONS/google.md for the token store + resolver pattern.

No silent errors: every except logs at the right level and re-raises.
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID, uuid4

logger = logging.getLogger(__name__)

# Lazy import — keep the fake path importable even if google SDK absent
_GCAL_UNSET = object()


class AgendaService:
    def __init__(
        self,
        db: Any,
        org_id: UUID,
        *,
        calendar_adapter: Any = _GCAL_UNSET,
    ) -> None:
        self._db = db
        self._org_id = str(org_id)
        # Resolve the adapter — default to FakeCalendarAdapter so the service
        # is always functional even without GCal credentials configured.
        if calendar_adapter is _GCAL_UNSET:
            from noctusai_lib.integrations.google_calendar import FakeCalendarAdapter
            calendar_adapter = FakeCalendarAdapter()
        self._gcal = calendar_adapter

    def _t(self, table: str):
        # The Supabase client is already schema-scoped to "orbity" by
        # create_database_module(settings, schema="orbity").
        return self._db.table(table)

    # ------------------------------------------------------------------
    # Agenda events CRUD
    # ------------------------------------------------------------------

    def list_events(
        self,
        *,
        from_dt: str | None = None,
        to_dt: str | None = None,
        event_type: str | None = None,
        client_id: str | None = None,
        assignee_user_id: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        try:
            query = (
                self._t("agenda_events")
                .select("*")
                .eq("org_id", self._org_id)
                .order("starts_at", desc=False)
            )
            if from_dt:
                query = query.gte("starts_at", from_dt)
            if to_dt:
                query = query.lte("starts_at", to_dt)
            if event_type:
                query = query.eq("event_type", event_type)
            if client_id:
                query = query.eq("client_id", client_id)
            if assignee_user_id:
                query = query.eq("assignee_user_id", assignee_user_id)
            offset = (page - 1) * page_size
            query = query.range(offset, offset + page_size - 1)
            result = query.execute()
        except Exception:
            logger.exception("agenda.list_events failed org=%s", self._org_id)
            raise
        rows = result.data or []
        return {"items": rows, "page": page, "page_size": page_size, "count": len(rows)}

    def create_event(self, data: dict[str, Any]) -> dict[str, Any]:
        """Insert an agenda_events row, stamping org_id. Returns the inserted row."""
        payload = {**data, "org_id": self._org_id}
        payload.setdefault("id", str(uuid4()))
        try:
            result = self._t("agenda_events").insert(payload).execute()
        except Exception:
            logger.exception("agenda.create_event failed org=%s", self._org_id)
            raise
        rows = result.data or []
        if not rows:
            raise RuntimeError(f"agenda.create_event: insert returned no data org={self._org_id}")
        return rows[0]

    def get_event(self, event_id: str) -> dict[str, Any] | None:
        try:
            result = (
                self._t("agenda_events")
                .select("*")
                .eq("org_id", self._org_id)
                .eq("id", event_id)
                .execute()
            )
        except Exception:
            logger.exception("agenda.get_event failed org=%s id=%s", self._org_id, event_id)
            raise
        rows = result.data or []
        return rows[0] if rows else None

    def update_event(self, event_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
        safe = {k: v for k, v in data.items() if k not in ("id", "org_id", "created_at")}
        try:
            result = (
                self._t("agenda_events")
                .update(safe)
                .eq("org_id", self._org_id)
                .eq("id", event_id)
                .execute()
            )
        except Exception:
            logger.exception("agenda.update_event failed org=%s id=%s", self._org_id, event_id)
            raise
        rows = result.data or []
        return rows[0] if rows else None

    def delete_event(self, event_id: str) -> bool:
        try:
            result = (
                self._t("agenda_events")
                .delete()
                .eq("org_id", self._org_id)
                .eq("id", event_id)
                .execute()
            )
        except Exception:
            logger.exception("agenda.delete_event failed org=%s id=%s", self._org_id, event_id)
            raise
        return bool(result.data)

    # ------------------------------------------------------------------
    # GCal sync seam
    # ------------------------------------------------------------------

    def sync_to_gcal(
        self,
        event_id: str,
        *,
        calendar_id: str = "primary",
        timezone: str = "America/Sao_Paulo",
    ) -> dict[str, Any] | None:
        """Sync an agenda_event to Google Calendar via the injected adapter.

        With FakeCalendarAdapter (the default), this is a no-op that returns
        the event row without modifying gcal_event_id. With a real adapter,
        it creates the GCal event and persists the returned event_id.

        Returns the (possibly updated) agenda_event row, or None if not found.
        """
        row = self.get_event(event_id)
        if not row:
            logger.warning("agenda.sync_to_gcal: event not found id=%s org=%s", event_id, self._org_id)
            return None

        # FakeCalendarAdapter.create_event() returns a CreatedEvent with a
        # deterministic fake event_id — safe in tests, no network call.
        from noctusai_lib.integrations.google_calendar import EventInput
        from datetime import datetime, timezone as _tz

        def _parse_dt(s: str) -> datetime:
            """Parse an ISO 8601 datetime string to an aware datetime."""
            try:
                # Python 3.11+: datetime.fromisoformat handles Z suffix
                return datetime.fromisoformat(s.replace("Z", "+00:00"))
            except Exception:
                logger.warning(
                    "agenda.sync_to_gcal: could not parse datetime %r; using now()", s
                )
                return datetime.now(_tz.utc)

        event_input = EventInput(
            summary=row["title"],
            start_at=_parse_dt(row["starts_at"]),
            end_at=_parse_dt(row["ends_at"]),
            timezone=timezone,
            description=row.get("description"),
            location=row.get("location"),
            request_id=event_id,
        )

        try:
            created = self._gcal.create_event(calendar_id, event_input)
        except Exception:
            logger.exception(
                "agenda.sync_to_gcal: gcal create_event failed id=%s org=%s",
                event_id,
                self._org_id,
            )
            raise

        # Persist the GCal event ID so subsequent syncs can detect duplicates
        updated = self.update_event(event_id, {"gcal_event_id": created.event_id})
        return updated if updated else row
