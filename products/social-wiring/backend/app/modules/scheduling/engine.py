"""Scheduling-engine wiring for the social-wiring ``scheduling`` module.

Absorbed from the ``imobi-scheduling`` product (project
``social-wiring-absorption`` Wave 2.3). The real-estate scheduling
domain — condominium / media-crew / travel-buffer vocabulary + the
appointment propose→confirm→cancel→reschedule lifecycle — is UNIQUE
production logic; it moves *into* social-wiring as a module.

**What the seed owns vs. what this module owns.**

  Seed (``noctusai_lib.domain.scheduling``):

    - ``SchedulingEngine.candidate_slots(...)`` — pure slot generation.
    - ``SchedulingRules`` — config dataclass (windows + durations + buffer + grid).
    - ``Conflict`` / ``Scorer`` / ``TravelLookup`` — Protocols for extension.
    - ``DefaultConflict`` (overlap + transition-buffer gap on both sides).
    - ``DefaultScorer`` (sum travel from previous + to next).
    - ``ZeroTravelLookup`` (no-travel default).

  This module owns:

    - ``SchedulingRuleDefaults`` + ``build_rules(...)`` — the working-window
      / duration / buffer / grid configuration. The lunch block
      (``12:00-13:30`` by default) is **implicit**: the engine only sees
      morning + afternoon ``WorkingWindow``s; no slot can land in the gap.
    - ``SchedulingService`` — DB-fetch glue + tool-call orchestration
      against the ``social_wiring`` schema.

**Real-estate vocabulary mapping**:

    locations  → condominium_id  (engine's ``target_location_id``)
    assignees  → media-crew users (engine's optional ``assignee_id``)
    transition → travel buffer    (engine's ``transition_buffer_minutes``)

The cross-product scheduling primitive is consumed from seed — this
module vendors NONE of the engine math, only the real-estate adapter +
DB orchestration. See ``KB § PATTERNS/scheduling-seed.md``.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from typing import Any, Callable, Optional
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

logger = logging.getLogger(__name__)

# The scheduling module owns its own schema-scoped table namespace. The
# product schema is ``social_wiring`` (single canonical 001 migration);
# the scheduling-domain tables are prefixed ``sched_`` to avoid colliding
# with the W2.1 media-wiring tables / W2.2 email_marketing tables in the
# shared schema.
SCHEMA = "social_wiring"


# Calendar seams — the consumer (W2.1 chat/conversation layer or the
# module router) injects these. On failure the factory MUST raise;
# ``confirm_appointment`` translates that into a non-created result
# BEFORE writing to DB.
CalendarEventFactory = Callable[..., str]
CalendarEventCanceler = Callable[..., None]
CalendarEventUpdater = Callable[..., Any]


# Time-window string → engine window name.
_WINDOW_NAME_MAP: dict[str, Optional[str]] = {
    "morning": "morning",
    "afternoon": "afternoon",
    "any": None,
}


# ---------------------------------------------------------------------------
# Rule configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SchedulingRuleDefaults:
    """Working-window / duration / buffer / grid configuration.

    Defaults match the absorbed imobi-scheduling production profile
    (single-tenant Brazil real-estate agency). A consumer may build a
    different instance from product settings + pass it to ``build_rules``.
    The lunch block is the implicit gap between ``morning_end`` and
    ``afternoon_start`` — no explicit ``BlockedInterval`` required.
    """

    timezone: str = "America/Sao_Paulo"
    morning_start: str = "09:00"
    morning_end: str = "12:00"
    afternoon_start: str = "13:30"
    afternoon_end: str = "16:30"
    travel_buffer_minutes: int = 10
    standard_duration_minutes: int = 90
    same_location_duration_minutes: int = 60
    slot_grid_minutes: int = 30


DEFAULT_RULE_CONFIG = SchedulingRuleDefaults()


def _parse_hhmm(raw: str) -> time:
    """Parse ``HH:MM`` → ``time``. Raises ``ValueError`` on malformed
    input rather than silently degrading — the rules dataclass is
    constructed once; surfacing malformed config loud is correct."""
    hh, mm = raw.split(":", 1)
    return time(hour=int(hh), minute=int(mm))


def build_rules(
    config: SchedulingRuleDefaults | None = None,
) -> SchedulingRules:
    """Build the seed ``SchedulingRules`` from module config."""
    cfg = config or DEFAULT_RULE_CONFIG
    tz = ZoneInfo(cfg.timezone)
    morning = WorkingWindow(
        name="morning",
        start=_parse_hhmm(cfg.morning_start),
        end=_parse_hhmm(cfg.morning_end),
    )
    afternoon = WorkingWindow(
        name="afternoon",
        start=_parse_hhmm(cfg.afternoon_start),
        end=_parse_hhmm(cfg.afternoon_end),
    )
    return SchedulingRules(
        timezone=tz,
        transition_buffer_minutes=cfg.travel_buffer_minutes,
        default_duration_minutes=cfg.standard_duration_minutes,
        same_location_duration_minutes=cfg.same_location_duration_minutes,
        slot_grid_minutes=cfg.slot_grid_minutes,
        working_windows=[morning, afternoon],
    )


def build_engine(
    rules: SchedulingRules,
    travel_lookup: TravelLookup | None = None,
    extra_conflicts: list[Conflict] | None = None,
    scorer: Scorer | None = None,
) -> SchedulingEngine:
    """Compose a ``SchedulingEngine`` with the real-estate defaults."""
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
    found: bool
    code: str
    property_id: Optional[str] = None
    condominium_id: Optional[str] = None
    condominium_name: Optional[str] = None


@dataclass(frozen=True, slots=True)
class ProposedSlot:
    start_at: str
    end_at: str
    duration_minutes: int
    score: float


@dataclass(frozen=True, slots=True)
class ConfirmationResult:
    created: bool
    appointment_id: Optional[str] = None
    reason: Optional[str] = None


@dataclass(frozen=True, slots=True)
class CancellationResult:
    cancelled: bool
    appointment_id: Optional[str] = None
    calendar_deleted: bool = False
    reason: Optional[str] = None


@dataclass(frozen=True, slots=True)
class RescheduleResult:
    rescheduled: bool
    appointment_id: Optional[str] = None
    calendar_updated: bool = False
    reason: Optional[str] = None


# ---------------------------------------------------------------------------
# SchedulingService — DB orchestration + tool-call handlers
# ---------------------------------------------------------------------------


class SchedulingService:
    """Per-request scheduling orchestrator against the ``social_wiring``
    schema. The seed engine is stateless per its contract; we construct
    one per service instance (cheap dataclass + engine init)."""

    SCHEMA = SCHEMA

    def __init__(
        self,
        admin_client: Any,
        *,
        org_id: Any,
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
        self._calendar_event_factory = calendar_event_factory
        self._calendar_event_canceler = calendar_event_canceler
        self._calendar_event_updater = calendar_event_updater

    # ------------------------------------------------------------------
    # Tool: lookup_property
    # ------------------------------------------------------------------

    def lookup_property(self, code: str) -> PropertyLookupResult:
        response = (
            self._scoped
            .table("sched_properties")
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

        condo_name = None
        try:
            condo_resp = (
                self._scoped
                .table("sched_condominiums")
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
                .table("sched_appointments")
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

        if services:
            logger.debug(
                "confirm_appointment received services=%s — full appointment_request "
                "lifecycle joins are a follow-up.",
                services,
            )

        return ConfirmationResult(created=True, appointment_id=appt_id)

    # ------------------------------------------------------------------
    # Tool: cancel_appointment
    # ------------------------------------------------------------------

    def cancel_appointment(
        self,
        *,
        appointment_id: str,
        reason: str | None = None,
        requester_user_id: str | None = None,
    ) -> CancellationResult:
        try:
            response = (
                self._scoped
                .table("sched_appointments")
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
            return CancellationResult(
                cancelled=False,
                appointment_id=appointment_id,
                reason=f"appointment status is {status!r}; only 'scheduled' may be cancelled",
            )

        google_event_id = row.get("google_calendar_event_id")

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
                .table("sched_appointments")
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
    # Tool: reschedule_appointment
    # ------------------------------------------------------------------

    def reschedule_appointment(
        self,
        *,
        appointment_id: str,
        new_start_at: datetime | str,
        new_end_at: datetime | str,
        requester_user_id: str | None = None,
    ) -> RescheduleResult:
        new_start = _coerce_aware_datetime(new_start_at, self.rules.timezone)
        new_end = _coerce_aware_datetime(new_end_at, self.rules.timezone)
        if new_end <= new_start:
            return RescheduleResult(
                rescheduled=False,
                appointment_id=appointment_id,
                reason="new_end_at must be strictly after new_start_at",
            )

        try:
            response = (
                self._scoped
                .table("sched_appointments")
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

        existing = self._fetch_existing_intervals(new_start.date())
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
                .table("sched_appointments")
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

        calendar_updated = False
        if google_event_id and self._calendar_event_updater is not None:
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
    # Internal helpers
    # ------------------------------------------------------------------

    def _lookup_condo_name(self, condo_id: str | None) -> Optional[str]:
        if not condo_id:
            return None
        try:
            resp = (
                self._scoped
                .table("sched_condominiums")
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
        if not property_id:
            return "(imóvel)"
        try:
            resp = (
                self._scoped
                .table("sched_properties")
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

    def _fetch_existing_intervals(
        self,
        requested_date: date,
    ) -> list[BlockedInterval]:
        tz = self.rules.timezone
        day_start = datetime.combine(requested_date, time(0, 0), tzinfo=tz)
        day_end = datetime.combine(
            date.fromordinal(requested_date.toordinal() + 1),
            time(0, 0),
            tzinfo=tz,
        )

        response = (
            self._scoped
            .table("sched_appointments")
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
    return ProposedSlot(
        start_at=slot.start_at.isoformat(),
        end_at=slot.end_at.isoformat(),
        duration_minutes=slot.duration_minutes,
        score=float(slot.score),
    )


def _coerce_aware_datetime(value: datetime | str, tz: ZoneInfo) -> datetime:
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"datetime is not ISO 8601: {value!r}") from exc
    else:
        parsed = value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=tz)
    return parsed


def _parse_aware_datetime(value: Any, tz: ZoneInfo) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=tz)
        return value
    return _coerce_aware_datetime(str(value), tz)


def _build_calendar_summary(
    prop: "PropertyLookupResult",
    services: list[str] | None,
) -> str:
    base = f"Visita técnica — {prop.condominium_name or '(condomínio)'} — {prop.code}"
    if services:
        base = f"{base} ({', '.join(services)})"
    return base


def _build_calendar_description(
    prop: "PropertyLookupResult",
    services: list[str] | None,
) -> str:
    lines = [
        f"Imóvel: {prop.code}",
        f"Condomínio: {prop.condominium_name or '(não definido)'}",
    ]
    if services:
        lines.append(f"Serviços: {', '.join(services)}")
    lines.append("")
    lines.append("Agendado via Social Wiring (WhatsApp).")
    return "\n".join(lines)


def _build_calendar_summary_from_strings(
    *,
    property_code: str,
    condo_name: str | None,
    services: list[str] | None,
) -> str:
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
    lines = [
        f"Imóvel: {property_code}",
        f"Condomínio: {condo_name or '(não definido)'}",
    ]
    if services:
        lines.append(f"Serviços: {', '.join(services)}")
    lines.append("")
    lines.append("Reagendado via Social Wiring (WhatsApp).")
    return "\n".join(lines)


def _now_utc_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _fallback_request_id(property_id: str | None, start: datetime) -> str:
    return f"adhoc-{property_id or 'unknown'}-{start.isoformat()}"


__all__ = [
    "CalendarEventCanceler",
    "CalendarEventFactory",
    "CalendarEventUpdater",
    "CancellationResult",
    "ConfirmationResult",
    "DEFAULT_RULE_CONFIG",
    "ProposedSlot",
    "PropertyLookupResult",
    "RescheduleResult",
    "SchedulingRuleDefaults",
    "SchedulingService",
    "build_engine",
    "build_rules",
]
