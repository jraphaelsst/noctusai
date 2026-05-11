"""Scheduling-engine wiring for the Imobi Scheduling bot — Phase 7.

**Why this module exists** — Phase 7 of `projects/imobi-scheduling-bot-creation/`
wires the seed `noctusai_lib.domain.scheduling.SchedulingEngine` into the
product. The engine is platform-neutral (location / assignee / transition
vocabulary); this module supplies the real-estate vocabulary adapter
(condominium / media crew / travel buffer) AND the DB orchestration that
fetches existing intervals + lookups property → condominium mapping.

**What the seed owns vs. what this module owns.**

  Seed (`noctusai_lib.domain.scheduling`):

    - `SchedulingEngine.candidate_slots(...)` — pure slot generation.
    - `SchedulingRules` — config dataclass (windows + durations + buffer + grid).
    - `Conflict` / `Scorer` / `TravelLookup` — Protocols for extension.
    - `DefaultConflict` (overlap + transition-buffer gap on both sides).
    - `DefaultScorer` (sum travel from previous + to next).
    - `ZeroTravelLookup` (no-travel default).

  This module owns:

    - `build_rules(settings)` — settings → `SchedulingRules` mapping. The
      lunch block (12:00-13:30) is **implicit**: the engine only sees
      morning + afternoon `WorkingWindow`s; no slot can land in the gap.
    - `SchedulingService` — DB-fetch glue + tool-call orchestration.
    - `_PropertyConflict` — placeholder for per-property availability
      (no rule today beyond what `DefaultConflict` gives us; reserved
      for future per-property restrictions).
    - `_CrewAvailabilityConflict` — placeholder shape (not wired into
      the engine yet — crew_skills + per-crew BlockedInterval surface
      lives in Phase 9 cancellation/reschedule scope).

**Real-estate vocabulary mapping** (per PROJECT.md §5.1):

    locations  → condominium_id  (engine's `target_location_id`)
    assignees  → media-crew users (engine's optional `assignee_id` on BlockedInterval)
    transition → travel buffer    (engine's `transition_buffer_minutes`)

**Tool semantics.**

  - `propose_appointment(property_code, requested_date, time_window)` —
    looks up the property → condominium, fetches existing scheduled
    appointments overlapping the date, calls `engine.candidate_slots(...)`,
    returns top-3 sorted slots as a JSON-serializable payload.
  - `confirm_appointment(property_code, services, start_at, end_at, ...)` —
    re-validates the slot is still free + (Phase 8 wires) creates the
    Calendar event + persists the `appointments` row. Phase 7 ships the
    re-validation + DB insert; Calendar event creation lands at Phase 8.
  - `lookup_property(code)` — real DB lookup (was a stub in Phase 6).

**Travel adapter.** A `TravelLookup` Protocol implementation that bridges
to `noctusai_lib.integrations.google_maps`. Phase 7 wires it as
`ZeroTravelLookup` by default (Maps adapter lands at Phase 8); the
constructor accepts an injected `TravelLookup` so Phase 8 can swap in
a real `GoogleMapsTravelLookup` without touching this module.

See `KB § PATTERNS/scheduling-seed.md § Wiring recipe` for the canonical
consumer-side wiring template this module follows.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from typing import Any, Callable, Optional
from uuid import UUID
from zoneinfo import ZoneInfo

from noctusai_lib.domain.scheduling import (
    BlockedInterval,
    Conflict,
    DefaultConflict,
    DefaultScorer,
    SchedulingContext,
    SchedulingEngine,
    SchedulingRules,
    Scorer,
    Slot,
    TravelLookup,
    WorkingWindow,
    ZeroTravelLookup,
)


# CalendarEventFactory: receives the kwargs needed to build a calendar
# event (summary/description/attendees come from the consumer's domain
# knowledge — the service is data-only) and returns the event_id string.
# On failure it MUST raise; ``confirm_appointment`` translates that into
# ``ConfirmationResult(created=False, reason=...)`` BEFORE writing to DB.
# Phase 8 wires this from ``app.services.calendar.create_calendar_event``.
CalendarEventFactory = Callable[..., str]


# CalendarEventCanceler: deletes a previously-created Calendar event by id.
# Phase 9 wires this from ``app.services.calendar.cancel_calendar_event``.
# Failure to delete is LOGGED but does NOT abort the DB-side cancellation
# flip — the user-visible "cancelled" state must land even if the Calendar
# side is unreachable (double-flip on the next retry would corrupt the DB).
CalendarEventCanceler = Callable[..., None]


# CalendarEventUpdater: updates a previously-created Calendar event's
# start/end + summary metadata. Phase 9 wires this from
# ``app.services.calendar.update_calendar_event``. On failure the service
# LOGS + falls back to deleting + re-creating the event id (the consumer
# decides; this module just routes through the seam).
CalendarEventUpdater = Callable[..., Any]

logger = logging.getLogger(__name__)


SCHEMA = "imobi_scheduling"

# Time-window string → engine window name. The LLM's `propose_appointment`
# tool accepts ``morning`` / ``afternoon`` / ``any``; the engine filters
# by `WorkingWindow.name` (`None` = all).
_WINDOW_NAME_MAP: dict[str, Optional[str]] = {
    "morning": "morning",
    "afternoon": "afternoon",
    "any": None,
}


# ---------------------------------------------------------------------------
# Settings → SchedulingRules
# ---------------------------------------------------------------------------

def _parse_hhmm(raw: str) -> time:
    """Parse ``HH:MM`` → `time`. Raises `ValueError` on malformed input
    rather than silently degrading — the rules dataclass is constructed
    once at module init; surfacing the malformed config loud is the right
    failure mode.
    """
    hh, mm = raw.split(":", 1)
    return time(hour=int(hh), minute=int(mm))


def build_rules(settings: Any) -> SchedulingRules:
    """Build `SchedulingRules` from the imobi-scheduling settings object.

    The lunch interval (`12:00-13:30` by default) is encoded implicitly
    as the gap between `imobi_scheduling_morning_end` and
    `imobi_scheduling_afternoon_start` — the engine never proposes a
    slot in that gap because no `WorkingWindow` covers it. No explicit
    `BlockedInterval` is required.

    Args:
        settings: `ImobiSchedulingSettings` (or any object exposing the
            ``imobi_scheduling_*`` knobs by attribute).

    Returns:
        Frozen `SchedulingRules` ready for `SchedulingEngine(rules=...)`.
    """
    tz = ZoneInfo(settings.imobi_scheduling_timezone)
    morning = WorkingWindow(
        name="morning",
        start=_parse_hhmm(settings.imobi_scheduling_morning_start),
        end=_parse_hhmm(settings.imobi_scheduling_morning_end),
    )
    afternoon = WorkingWindow(
        name="afternoon",
        start=_parse_hhmm(settings.imobi_scheduling_afternoon_start),
        end=_parse_hhmm(settings.imobi_scheduling_afternoon_end),
    )
    return SchedulingRules(
        timezone=tz,
        transition_buffer_minutes=settings.imobi_scheduling_travel_buffer_minutes,
        default_duration_minutes=settings.imobi_scheduling_standard_duration_minutes,
        same_location_duration_minutes=settings.imobi_scheduling_same_condo_duration_minutes,
        slot_grid_minutes=settings.imobi_scheduling_slot_grid_minutes,
        working_windows=[morning, afternoon],
    )


def build_engine(
    rules: SchedulingRules,
    travel_lookup: TravelLookup | None = None,
    extra_conflicts: list[Conflict] | None = None,
    scorer: Scorer | None = None,
) -> SchedulingEngine:
    """Compose a `SchedulingEngine` with imobi defaults.

    Default conflict list is just `DefaultConflict` (overlap +
    transition buffer); `extra_conflicts` appends additional rules
    (e.g. a future `CrewAvailabilityConflict` wired in Phase 9).

    Default `travel_lookup` is `ZeroTravelLookup` (no Maps adapter yet).
    Phase 8 will inject a `GoogleMapsTravelLookup`.

    Default `scorer` is `DefaultScorer` (sum travel previous + next).
    """
    conflicts: list[Conflict] = [DefaultConflict()]
    if extra_conflicts:
        conflicts.extend(extra_conflicts)
    return SchedulingEngine(
        rules=rules,
        travel_lookup=travel_lookup if travel_lookup is not None else ZeroTravelLookup(),
        conflicts=conflicts,
        scorer=scorer if scorer is not None else DefaultScorer(),
    )


# ---------------------------------------------------------------------------
# Result value objects (handler-facing)
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class PropertyLookupResult:
    """Outcome of `lookup_property`. `found=False` → property code not
    registered for this org. `condominium_id` is the engine's
    `target_location_id`.
    """

    found: bool
    code: str
    property_id: Optional[str] = None
    condominium_id: Optional[str] = None
    condominium_name: Optional[str] = None


@dataclass(frozen=True, slots=True)
class ProposedSlot:
    """Single proposed-slot payload (JSON-serializable)."""

    start_at: str  # ISO 8601 with TZ
    end_at: str    # ISO 8601 with TZ
    duration_minutes: int
    score: float


@dataclass(frozen=True, slots=True)
class ConfirmationResult:
    """Outcome of `confirm_appointment`. `created=False` means the slot
    is no longer free (a concurrent confirmation took it) or the
    property/services lookup failed."""

    created: bool
    appointment_id: Optional[str] = None
    reason: Optional[str] = None


@dataclass(frozen=True, slots=True)
class CancellationResult:
    """Outcome of `cancel_appointment`. `cancelled=False` means the row
    was not in a cancellable state (already cancelled / completed / not
    found). ``calendar_deleted`` separates the DB-side flip from the
    Calendar-side deletion — a True DB flip with False Calendar deletion
    is reported, not raised (caller logs + user can clean stale event).
    """

    cancelled: bool
    appointment_id: Optional[str] = None
    calendar_deleted: bool = False
    reason: Optional[str] = None


@dataclass(frozen=True, slots=True)
class RescheduleResult:
    """Outcome of `reschedule_appointment`. ``rescheduled=False`` means
    the new slot conflicts, the row was not in a reschedulable state,
    or the property/lookup failed. ``calendar_updated`` separates the
    DB-side flip from the Calendar-side update.
    """

    rescheduled: bool
    appointment_id: Optional[str] = None
    calendar_updated: bool = False
    reason: Optional[str] = None


# ---------------------------------------------------------------------------
# SchedulingService — DB orchestration + tool-call handlers
# ---------------------------------------------------------------------------

class SchedulingService:
    """Per-request scheduling orchestrator.

    Per-request construction from a Supabase admin client + the
    single-agency `org_id` (Phase 0 Q4). The schema is
    `imobi_scheduling`; the service uses `client.schema(...)` to scope
    queries.

    The engine is `stateless` per the seed contract — safe to construct
    once and re-use. We construct on every service instance for now
    (cheap dataclass + engine init); future optimization can hoist the
    engine to module-scope if profiling demands.
    """

    SCHEMA = "imobi_scheduling"

    def __init__(
        self,
        admin_client: Any,
        *,
        org_id: UUID | str,
        rules: SchedulingRules,
        travel_lookup: TravelLookup | None = None,
        extra_conflicts: list[Conflict] | None = None,
        scorer: Scorer | None = None,
        calendar_event_factory: CalendarEventFactory | None = None,
        calendar_event_canceler: CalendarEventCanceler | None = None,
        calendar_event_updater: CalendarEventUpdater | None = None,
    ) -> None:
        self._client = admin_client
        self._org_id = str(org_id)
        self._scoped = admin_client.schema(self.SCHEMA)
        self.rules = rules
        self.engine = build_engine(
            rules=rules,
            travel_lookup=travel_lookup,
            extra_conflicts=extra_conflicts,
            scorer=scorer,
        )
        # Phase 8 seam — when provided, ``confirm_appointment`` calls this
        # AFTER conflict re-validation but BEFORE the DB insert. Failure
        # to create the Calendar event aborts the booking — the DB row
        # never lands. None preserves the Phase 7 DB-only path used by
        # the existing test suite + early-dev.
        self._calendar_event_factory = calendar_event_factory
        # Phase 9 seams — wired by lifespan from
        # ``app.services.calendar.cancel_calendar_event`` +
        # ``app.services.calendar.update_calendar_event``. When absent
        # (test paths / pre-Phase-9 wiring), cancellation/reschedule
        # operate on the DB row only.
        self._calendar_event_canceler = calendar_event_canceler
        self._calendar_event_updater = calendar_event_updater

    # ------------------------------------------------------------------
    # Tool: lookup_property
    # ------------------------------------------------------------------

    def lookup_property(self, code: str) -> PropertyLookupResult:
        """Resolve a property code → property + condominium.

        Returns `PropertyLookupResult(found=False, ...)` when the code
        does not match an active property for this org. Inactive
        properties are excluded.
        """
        response = (
            self._scoped
            .table("properties")
            .select("id, code, condominium_id, active, org_id")
            .eq("code", code)
            .eq("active", True)
            .eq("org_id", self._org_id)
            .execute()
        )
        rows = response.data or []
        if not rows:
            return PropertyLookupResult(found=False, code=code)

        row = rows[0]
        prop_id = str(row["id"])
        condo_id = str(row["condominium_id"])

        # Fetch condominium name (best-effort — missing → None).
        condo_name = None
        try:
            condo_resp = (
                self._scoped
                .table("condominiums")
                .select("id, name, org_id")
                .eq("id", condo_id)
                .eq("org_id", self._org_id)
                .execute()
            )
            condo_rows = condo_resp.data or []
            if condo_rows:
                condo_name = condo_rows[0].get("name")
        except Exception as exc:  # noqa: BLE001 — best-effort; loud-log only.
            logger.warning(
                "Condominium name lookup failed: condo_id=%s err=%s",
                condo_id, exc,
            )

        return PropertyLookupResult(
            found=True,
            code=code,
            property_id=prop_id,
            condominium_id=condo_id,
            condominium_name=condo_name,
        )

    # ------------------------------------------------------------------
    # Tool: propose_appointment
    # ------------------------------------------------------------------

    def propose_appointment(
        self,
        *,
        property_code: str,
        requested_date: date | str,
        time_window: str = "any",
        limit: int = 3,
    ) -> list[ProposedSlot]:
        """Generate candidate slots for the date + window.

        Returns up to `limit` slots sorted by `(score, start_at)` per
        the engine contract. Empty list means no valid slot was found
        (every grid position conflicted with existing appointments or
        fell outside the working windows).

        Raises:
            ValueError: If the property code is unknown OR the date /
                window inputs are malformed. Surface to the LLM as a
                tool-error payload — not a silent failure.
        """
        if isinstance(requested_date, str):
            try:
                requested_date = date.fromisoformat(requested_date)
            except ValueError as exc:
                raise ValueError(
                    f"requested_date is not ISO-formatted (YYYY-MM-DD): {requested_date!r}"
                ) from exc

        prop = self.lookup_property(property_code)
        if not prop.found:
            raise ValueError(f"Property code not found: {property_code!r}")

        window_name = _WINDOW_NAME_MAP.get(time_window, None)
        existing = self._fetch_existing_intervals(requested_date)

        slots = self.engine.candidate_slots(
            requested_date=requested_date,
            target_location_id=prop.condominium_id,
            existing_intervals=existing,
            window_name=window_name,
        )
        return [_slot_to_proposed(s) for s in slots[:limit]]

    # ------------------------------------------------------------------
    # Tool: confirm_appointment
    # ------------------------------------------------------------------

    def confirm_appointment(
        self,
        *,
        property_code: str,
        start_at: datetime | str,
        end_at: datetime | str,
        services: list[str] | None = None,
        appointment_request_id: str | None = None,
        media_crew_user_id: str | None = None,
        google_calendar_event_id: str | None = None,
    ) -> ConfirmationResult:
        """Persist a confirmed appointment row.

        Phase 7 ships the DB insert path + a final overlap re-check
        (engine `DefaultConflict.applies` against current `appointments`
        rows for the date).

        Phase 8 — when ``calendar_event_factory`` is wired into the
        service (via constructor injection), this method calls it AFTER
        conflict re-validation but BEFORE the DB insert. A failure in
        the calendar factory aborts the booking (no DB row written) so
        the user can't see "scheduled" status while the Calendar event
        is missing. The resulting Calendar event_id is persisted as
        ``google_calendar_event_id`` on the row.

        Callers may also pre-create the Calendar event themselves and
        pass ``google_calendar_event_id=...`` — in that case the
        factory is skipped (the caller has already handled idempotency).

        Returns `created=False` on:
          - property lookup miss,
          - calendar event creation failure (when factory is wired and
            no caller-provided ``google_calendar_event_id``),
          - DB insert failure,
          - re-validation conflict (slot taken between propose + confirm).
        """
        start = _coerce_aware_datetime(start_at, self.rules.timezone)
        end = _coerce_aware_datetime(end_at, self.rules.timezone)
        if end <= start:
            return ConfirmationResult(
                created=False,
                reason="end_at must be strictly after start_at",
            )

        prop = self.lookup_property(property_code)
        if not prop.found:
            return ConfirmationResult(
                created=False,
                reason=f"property code not found: {property_code!r}",
            )

        # Re-validate the slot against current bookings. Defends against
        # the propose→confirm race (another caller grabbed the slot).
        existing = self._fetch_existing_intervals(start.date())
        candidate = Slot(
            start_at=start,
            end_at=end,
            duration_minutes=int((end - start).total_seconds() // 60),
        )
        ctx = SchedulingContext(
            target_location_id=prop.condominium_id,
            existing_intervals_sorted=sorted(existing, key=lambda i: i.start),
            travel_lookup=self.engine.travel_lookup,
            rules=self.rules,
        )
        for rule in self.engine.conflicts:
            if rule.applies(candidate, ctx):
                return ConfirmationResult(
                    created=False,
                    reason="slot conflicts with an existing appointment",
                )

        # Phase 8 — create the Calendar event BEFORE the DB insert. If
        # the factory is configured and the create_event call fails, the
        # appointment row is NOT inserted (compensation is preferable to
        # double-booking: a failed Calendar create with a successful DB
        # row would mask the user-visible failure mode "I don't see it
        # on my Calendar"). The factory is consumer-injected (Phase 8
        # wires ``app.services.calendar.create_calendar_event``); when
        # absent (test path / pre-Phase-8 wiring), the path skips and
        # ``google_calendar_event_id`` is whatever the caller passed
        # (typically None).
        if self._calendar_event_factory is not None and not google_calendar_event_id:
            try:
                google_calendar_event_id = self._calendar_event_factory(
                    summary=_build_calendar_summary(prop, services),
                    start_at=start,
                    end_at=end,
                    timezone=str(self.rules.timezone),
                    appointment_request_id=appointment_request_id or _fallback_request_id(
                        prop.property_id, start
                    ),
                    description=_build_calendar_description(prop, services),
                    location=prop.condominium_name,
                )
            except Exception as exc:  # noqa: BLE001 — surface loud + abort booking.
                logger.warning(
                    "Calendar event creation failed; aborting confirm: "
                    "property=%s start=%s err=%s",
                    property_code, start.isoformat(), exc,
                )
                return ConfirmationResult(
                    created=False,
                    reason=f"calendar event creation failed: {exc}",
                )

        payload: dict[str, Any] = {
            "org_id": self._org_id,
            "property_id": prop.property_id,
            "condominium_id": prop.condominium_id,
            "start_at": start.isoformat(),
            "end_at": end.isoformat(),
            "status": "scheduled",
        }
        if appointment_request_id:
            payload["appointment_request_id"] = appointment_request_id
        if media_crew_user_id:
            payload["media_crew_user_id"] = media_crew_user_id
        if google_calendar_event_id:
            payload["google_calendar_event_id"] = google_calendar_event_id

        try:
            response = (
                self._scoped
                .table("appointments")
                .insert(payload)
                .execute()
            )
        except Exception as exc:  # noqa: BLE001 — DB failure surfaced loud.
            logger.warning(
                "Appointment insert failed: property=%s start=%s err=%s",
                property_code, start.isoformat(), exc,
            )
            return ConfirmationResult(
                created=False,
                reason=f"appointment insert failed: {exc}",
            )

        rows = response.data or []
        appt_id = str(rows[0]["id"]) if rows and "id" in rows[0] else None

        # Note: `services` arg is captured for future appointment_request_services
        # joining (Phase 9 cancellation/reschedule wires the full request lifecycle).
        # The dispatcher passes it through; we drop here with a debug log if unused.
        if services:
            logger.debug(
                "confirm_appointment received services=%s — full appointment_request "
                "lifecycle wired at Phase 9.",
                services,
            )

        return ConfirmationResult(
            created=True,
            appointment_id=appt_id,
        )

    # ------------------------------------------------------------------
    # Tool: cancel_appointment (Phase 9)
    # ------------------------------------------------------------------

    def cancel_appointment(
        self,
        *,
        appointment_id: str,
        reason: str | None = None,
        requester_user_id: str | None = None,
    ) -> CancellationResult:
        """Cancel a previously-confirmed appointment.

        Flow:

          1. Fetch the appointment row by id; validate it's in
             ``status='scheduled'`` (idempotent — already-cancelled rows
             return ``cancelled=False`` with reason so the LLM can read
             back a stable "already cancelled" payload).
          2. Flip status to ``cancelled``; write cancellation audit columns
             (``cancellation_reason``, ``cancelled_at``, ``cancelled_by``).
          3. If the row carries a ``google_calendar_event_id`` AND a
             ``calendar_event_canceler`` is wired, delete the Calendar
             event. Failure LOGS but does NOT roll back the DB flip — a
             stale Calendar event is recoverable; a desynced DB state
             would corrupt future propose/confirm conflict re-checks.

        Args:
            appointment_id: UUID of the row to cancel.
            reason: Free-text cancellation reason from the user.
            requester_user_id: Optional UUID for the audit trail
                (``cancelled_by``).

        Returns:
            `CancellationResult` — ``cancelled=True`` on success,
            ``cancelled=False`` when row is missing / not in a
            cancellable state. ``calendar_deleted`` reflects the Calendar
            side outcome independently.
        """
        # Fetch the row to validate state + capture event id.
        try:
            response = (
                self._scoped
                .table("appointments")
                .select("id, status, google_calendar_event_id, org_id")
                .eq("id", appointment_id)
                .eq("org_id", self._org_id)
                .execute()
            )
        except Exception as exc:  # noqa: BLE001 — DB fetch surfaced loud.
            logger.warning(
                "Cancel fetch failed: appointment_id=%s err=%s",
                appointment_id, exc,
            )
            return CancellationResult(
                cancelled=False,
                appointment_id=appointment_id,
                reason=f"appointment fetch failed: {exc}",
            )

        rows = response.data or []
        if not rows:
            return CancellationResult(
                cancelled=False,
                appointment_id=appointment_id,
                reason=f"appointment not found: {appointment_id!r}",
            )

        row = rows[0]
        status = row.get("status")
        if status != "scheduled":
            # Idempotent: already-cancelled returns a stable "not cancelled
            # again" signal; the LLM reads the reason and replies naturally.
            return CancellationResult(
                cancelled=False,
                appointment_id=appointment_id,
                reason=f"appointment status is {status!r}; only 'scheduled' may be cancelled",
            )

        google_event_id = row.get("google_calendar_event_id")

        # DB-side flip FIRST. Calendar delete follows + is best-effort.
        now_iso = _now_utc_iso()
        update_payload: dict[str, Any] = {
            "status": "cancelled",
            "cancellation_reason": reason,
            "cancelled_at": now_iso,
        }
        if requester_user_id:
            update_payload["cancelled_by"] = requester_user_id

        try:
            (
                self._scoped
                .table("appointments")
                .update(update_payload)
                .eq("id", appointment_id)
                .eq("org_id", self._org_id)
                .execute()
            )
        except Exception as exc:  # noqa: BLE001 — DB update surfaced loud.
            logger.warning(
                "Cancel DB update failed: appointment_id=%s err=%s",
                appointment_id, exc,
            )
            return CancellationResult(
                cancelled=False,
                appointment_id=appointment_id,
                reason=f"appointment update failed: {exc}",
            )

        # Calendar delete (best-effort). The DB is already flipped — a
        # failure here leaves a stale Calendar event but the booking is
        # gone from the user's perspective.
        calendar_deleted = False
        if google_event_id and self._calendar_event_canceler is not None:
            try:
                self._calendar_event_canceler(event_id=google_event_id)
                calendar_deleted = True
            except Exception as exc:  # noqa: BLE001 — best-effort delete.
                logger.warning(
                    "Calendar event deletion failed (DB cancellation already landed): "
                    "appointment_id=%s event_id=%s err=%s",
                    appointment_id, google_event_id, exc,
                )

        return CancellationResult(
            cancelled=True,
            appointment_id=appointment_id,
            calendar_deleted=calendar_deleted,
        )

    # ------------------------------------------------------------------
    # Tool: reschedule_appointment (Phase 9)
    # ------------------------------------------------------------------

    def reschedule_appointment(
        self,
        *,
        appointment_id: str,
        new_start_at: datetime | str,
        new_end_at: datetime | str,
        requester_user_id: str | None = None,
    ) -> RescheduleResult:
        """Move a confirmed appointment to a new slot.

        Flow:

          1. Fetch the row by id; validate ``status='scheduled'``.
          2. Re-validate the new slot against current bookings via the
             same `DefaultConflict` rule used by `confirm_appointment` —
             a conflict returns ``rescheduled=False`` with reason. The
             row's OWN appointment is excluded from the conflict-check
             interval list (otherwise it would conflict with itself).
          3. Capture ``previous_start_at`` / ``previous_end_at`` for the
             audit trail; update ``start_at`` / ``end_at`` + audit columns
             (``rescheduled_at``, ``rescheduled_by``).
          4. If the row carries a ``google_calendar_event_id`` AND a
             ``calendar_event_updater`` is wired, update the Calendar
             event. Same best-effort semantics as cancellation — failure
             LOGS but does not roll back the DB-side update.

        Args:
            appointment_id: UUID of the row to reschedule.
            new_start_at / new_end_at: New slot (tz-aware datetime or
                ISO-8601 string; naïve strings are localized to the
                rules timezone).
            requester_user_id: Optional UUID for the audit trail
                (``rescheduled_by``).

        Returns:
            `RescheduleResult` — ``rescheduled=True`` on success;
            ``rescheduled=False`` on conflict / not-found / wrong-status.
            ``calendar_updated`` reflects the Calendar side outcome.
        """
        new_start = _coerce_aware_datetime(new_start_at, self.rules.timezone)
        new_end = _coerce_aware_datetime(new_end_at, self.rules.timezone)
        if new_end <= new_start:
            return RescheduleResult(
                rescheduled=False,
                appointment_id=appointment_id,
                reason="new_end_at must be strictly after new_start_at",
            )

        # Fetch the row to validate state + capture event id + condo.
        try:
            response = (
                self._scoped
                .table("appointments")
                .select(
                    "id, status, google_calendar_event_id, condominium_id, "
                    "property_id, start_at, end_at, appointment_request_id, "
                    "media_crew_user_id, org_id"
                )
                .eq("id", appointment_id)
                .eq("org_id", self._org_id)
                .execute()
            )
        except Exception as exc:  # noqa: BLE001 — DB fetch surfaced loud.
            logger.warning(
                "Reschedule fetch failed: appointment_id=%s err=%s",
                appointment_id, exc,
            )
            return RescheduleResult(
                rescheduled=False,
                appointment_id=appointment_id,
                reason=f"appointment fetch failed: {exc}",
            )

        rows = response.data or []
        if not rows:
            return RescheduleResult(
                rescheduled=False,
                appointment_id=appointment_id,
                reason=f"appointment not found: {appointment_id!r}",
            )

        row = rows[0]
        status = row.get("status")
        if status != "scheduled":
            return RescheduleResult(
                rescheduled=False,
                appointment_id=appointment_id,
                reason=f"appointment status is {status!r}; only 'scheduled' may be rescheduled",
            )

        condo_id = str(row["condominium_id"])
        google_event_id = row.get("google_calendar_event_id")
        property_id = row.get("property_id")
        appointment_request_id = row.get("appointment_request_id")

        # Re-validate the new slot. Fetch existing intervals overlapping
        # the new date, EXCLUDE the row's own current interval (or it
        # collides with itself when the new slot overlaps the old one).
        existing = self._fetch_existing_intervals(new_start.date())
        # Filter out the row being moved — match by exact start/end + condo.
        try:
            current_start = _parse_aware_datetime(row["start_at"], self.rules.timezone)
            current_end = _parse_aware_datetime(row["end_at"], self.rules.timezone)
        except (KeyError, ValueError) as exc:
            logger.warning(
                "Reschedule could not parse current start/end: appointment_id=%s err=%s",
                appointment_id, exc,
            )
            current_start = current_end = None  # type: ignore[assignment]

        if current_start is not None and current_end is not None:
            existing = [
                interval for interval in existing
                if not (
                    interval.start == current_start
                    and interval.end == current_end
                    and interval.location_id == condo_id
                )
            ]

        candidate = Slot(
            start_at=new_start,
            end_at=new_end,
            duration_minutes=int((new_end - new_start).total_seconds() // 60),
        )
        ctx = SchedulingContext(
            target_location_id=condo_id,
            existing_intervals_sorted=sorted(existing, key=lambda i: i.start),
            travel_lookup=self.engine.travel_lookup,
            rules=self.rules,
        )
        for rule in self.engine.conflicts:
            if rule.applies(candidate, ctx):
                return RescheduleResult(
                    rescheduled=False,
                    appointment_id=appointment_id,
                    reason="new slot conflicts with an existing appointment",
                )

        # DB-side flip FIRST. Capture previous_* columns for the audit.
        now_iso = _now_utc_iso()
        update_payload: dict[str, Any] = {
            "start_at": new_start.isoformat(),
            "end_at": new_end.isoformat(),
            "rescheduled_at": now_iso,
            "previous_start_at": row["start_at"],
            "previous_end_at": row["end_at"],
        }
        if requester_user_id:
            update_payload["rescheduled_by"] = requester_user_id

        try:
            (
                self._scoped
                .table("appointments")
                .update(update_payload)
                .eq("id", appointment_id)
                .eq("org_id", self._org_id)
                .execute()
            )
        except Exception as exc:  # noqa: BLE001 — DB update surfaced loud.
            logger.warning(
                "Reschedule DB update failed: appointment_id=%s err=%s",
                appointment_id, exc,
            )
            return RescheduleResult(
                rescheduled=False,
                appointment_id=appointment_id,
                reason=f"appointment update failed: {exc}",
            )

        # Calendar update (best-effort). The DB is already flipped.
        calendar_updated = False
        if google_event_id and self._calendar_event_updater is not None:
            # Look up property + condo names for a refreshed event body.
            condo_name = self._lookup_condo_name(condo_id)
            try:
                self._calendar_event_updater(
                    event_id=google_event_id,
                    summary=_build_calendar_summary_from_strings(
                        property_code=self._lookup_property_code(property_id),
                        condo_name=condo_name,
                        services=None,
                    ),
                    start_at=new_start,
                    end_at=new_end,
                    timezone=str(self.rules.timezone),
                    appointment_request_id=appointment_request_id or _fallback_request_id(
                        property_id, new_start
                    ),
                    description=_build_calendar_description_from_strings(
                        property_code=self._lookup_property_code(property_id),
                        condo_name=condo_name,
                        services=None,
                    ),
                    location=condo_name,
                )
                calendar_updated = True
            except Exception as exc:  # noqa: BLE001 — best-effort update.
                logger.warning(
                    "Calendar event update failed (DB reschedule already landed): "
                    "appointment_id=%s event_id=%s err=%s",
                    appointment_id, google_event_id, exc,
                )

        return RescheduleResult(
            rescheduled=True,
            appointment_id=appointment_id,
            calendar_updated=calendar_updated,
        )

    # ------------------------------------------------------------------
    # Internal helpers for Phase 9 calendar refresh
    # ------------------------------------------------------------------

    def _lookup_condo_name(self, condo_id: str | None) -> Optional[str]:
        """Best-effort condominium-name lookup for Calendar summary refresh."""
        if not condo_id:
            return None
        try:
            resp = (
                self._scoped
                .table("condominiums")
                .select("id, name, org_id")
                .eq("id", condo_id)
                .eq("org_id", self._org_id)
                .execute()
            )
            rows = resp.data or []
            if rows:
                return rows[0].get("name")
        except Exception as exc:  # noqa: BLE001 — best-effort.
            logger.warning(
                "Condo name lookup failed during reschedule: condo_id=%s err=%s",
                condo_id, exc,
            )
        return None

    def _lookup_property_code(self, property_id: str | None) -> str:
        """Best-effort property-code lookup for Calendar summary refresh."""
        if not property_id:
            return "(imóvel)"
        try:
            resp = (
                self._scoped
                .table("properties")
                .select("id, code, org_id")
                .eq("id", property_id)
                .eq("org_id", self._org_id)
                .execute()
            )
            rows = resp.data or []
            if rows:
                return str(rows[0].get("code") or "(imóvel)")
        except Exception as exc:  # noqa: BLE001 — best-effort.
            logger.warning(
                "Property code lookup failed during reschedule: property_id=%s err=%s",
                property_id, exc,
            )
        return "(imóvel)"

    # ------------------------------------------------------------------
    # Internal: fetch existing intervals from the appointments table
    # ------------------------------------------------------------------

    def _fetch_existing_intervals(
        self,
        requested_date: date,
    ) -> list[BlockedInterval]:
        """Fetch confirmed (`scheduled`) appointments overlapping the date.

        The engine wants a list of `BlockedInterval`; we map each
        appointment row → `BlockedInterval(start, end, location_id=condominium_id,
        assignee_id=media_crew_user_id)`. Cancelled / completed rows are
        excluded — they no longer constrain new bookings.

        Date overlap: we fetch any row whose `[start_at, end_at)` intersects
        the day-bounded `[requested_date 00:00, next_day 00:00)` interval
        in the rules timezone.
        """
        tz = self.rules.timezone
        day_start = datetime.combine(requested_date, time(0, 0), tzinfo=tz)
        day_end = datetime.combine(
            date.fromordinal(requested_date.toordinal() + 1),
            time(0, 0),
            tzinfo=tz,
        )

        # `lt(start_at, day_end) AND gt(end_at, day_start)` — overlap predicate.
        response = (
            self._scoped
            .table("appointments")
            .select("id, start_at, end_at, condominium_id, media_crew_user_id, status, org_id")
            .eq("org_id", self._org_id)
            .eq("status", "scheduled")
            .lt("start_at", day_end.isoformat())
            .gt("end_at", day_start.isoformat())
            .execute()
        )
        rows = response.data or []

        intervals: list[BlockedInterval] = []
        for row in rows:
            try:
                start = _parse_aware_datetime(row["start_at"], tz)
                end = _parse_aware_datetime(row["end_at"], tz)
            except (KeyError, ValueError) as exc:
                logger.warning(
                    "Skipping malformed appointment row: id=%s err=%s",
                    row.get("id", "<unknown>"), exc,
                )
                continue
            intervals.append(
                BlockedInterval(
                    start=start,
                    end=end,
                    location_id=str(row["condominium_id"]),
                    assignee_id=(
                        str(row["media_crew_user_id"])
                        if row.get("media_crew_user_id")
                        else None
                    ),
                )
            )
        return intervals


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slot_to_proposed(slot: Slot) -> ProposedSlot:
    """Translate engine `Slot` → JSON-serializable `ProposedSlot`."""
    return ProposedSlot(
        start_at=slot.start_at.isoformat(),
        end_at=slot.end_at.isoformat(),
        duration_minutes=slot.duration_minutes,
        score=float(slot.score),
    )


def _coerce_aware_datetime(value: datetime | str, tz: ZoneInfo) -> datetime:
    """Coerce a datetime or ISO string → tz-aware datetime in `tz`.

    Naïve inputs are localized to `tz` (the bot is single-tenant Brazil).
    """
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(
                f"datetime is not ISO 8601: {value!r}"
            ) from exc
    else:
        parsed = value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=tz)
    return parsed


def _parse_aware_datetime(value: Any, tz: ZoneInfo) -> datetime:
    """Parse a Supabase TIMESTAMPTZ string (or datetime) → aware datetime."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=tz)
        return value
    return _coerce_aware_datetime(str(value), tz)


def _build_calendar_summary(
    prop: "PropertyLookupResult",
    services: list[str] | None,
) -> str:
    """Compose a Calendar event summary string.

    Format: ``"Visita técnica — <condo_name> — <property_code>"`` with a
    services-suffix when present. Localized pt-BR per the bot's primary
    language; the prose isn't user-tunable today.
    """
    base = f"Visita técnica — {prop.condominium_name or '(condomínio)'} — {prop.code}"
    if services:
        base = f"{base} ({', '.join(services)})"
    return base


def _build_calendar_description(
    prop: "PropertyLookupResult",
    services: list[str] | None,
) -> str:
    """Compose a Calendar event description (multi-line)."""
    lines = [
        f"Imóvel: {prop.code}",
        f"Condomínio: {prop.condominium_name or '(não definido)'}",
    ]
    if services:
        lines.append(f"Serviços: {', '.join(services)}")
    lines.append("")
    lines.append("Agendado via Imobi Scheduling Bot (WhatsApp).")
    return "\n".join(lines)


def _build_calendar_summary_from_strings(
    *,
    property_code: str,
    condo_name: str | None,
    services: list[str] | None,
) -> str:
    """Reschedule-side summary builder.

    The reschedule path doesn't have a `PropertyLookupResult` handy (the
    property + condo are denormalized on the appointment row), so we accept
    the raw strings + reuse the same shape ``_build_calendar_summary``
    emits for `confirm_appointment`.
    """
    base = f"Visita técnica — {condo_name or '(condomínio)'} — {property_code}"
    if services:
        base = f"{base} ({', '.join(services)})"
    return base


def _build_calendar_description_from_strings(
    *,
    property_code: str,
    condo_name: str | None,
    services: list[str] | None,
) -> str:
    """Reschedule-side description builder. Same shape as ``_build_calendar_description``."""
    lines = [
        f"Imóvel: {property_code}",
        f"Condomínio: {condo_name or '(não definido)'}",
    ]
    if services:
        lines.append(f"Serviços: {', '.join(services)}")
    lines.append("")
    lines.append("Reagendado via Imobi Scheduling Bot (WhatsApp).")
    return "\n".join(lines)


def _now_utc_iso() -> str:
    """Current wall-clock as ISO-8601 UTC. Centralized so tests can monkey-patch
    a single call site if needed (no test does today; kept tight for the future).
    """
    return datetime.now(tz=timezone.utc).isoformat()


def _fallback_request_id(property_id: str | None, start: datetime) -> str:
    """Synthesize a stable request-id when no ``appointment_request_id``
    is supplied (Phase 9 will surface it for the full request lifecycle).

    Combines property + start to remain stable across retries of the
    same logical confirmation.
    """
    return f"adhoc-{property_id or 'unknown'}-{start.isoformat()}"


__all__ = [
    "CalendarEventCanceler",
    "CalendarEventFactory",
    "CalendarEventUpdater",
    "CancellationResult",
    "ConfirmationResult",
    "ProposedSlot",
    "PropertyLookupResult",
    "RescheduleResult",
    "SchedulingService",
    "build_engine",
    "build_rules",
]
