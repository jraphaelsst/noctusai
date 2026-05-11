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
from datetime import date, datetime, time
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


def _fallback_request_id(property_id: str | None, start: datetime) -> str:
    """Synthesize a stable request-id when no ``appointment_request_id``
    is supplied (Phase 9 will surface it for the full request lifecycle).

    Combines property + start to remain stable across retries of the
    same logical confirmation.
    """
    return f"adhoc-{property_id or 'unknown'}-{start.isoformat()}"


__all__ = [
    "CalendarEventFactory",
    "ConfirmationResult",
    "ProposedSlot",
    "PropertyLookupResult",
    "SchedulingService",
    "build_engine",
    "build_rules",
]
