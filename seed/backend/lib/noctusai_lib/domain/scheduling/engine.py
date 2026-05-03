"""Slot-generation engine — value objects, Protocols, defaults, engine.

The math is preserved verbatim from the sibling
(`whatsapp-google-scheduling/app/services/scheduling_service.py`); only
the vocabulary changed.

Three Protocols (`TravelLookup`, `Conflict`, `Scorer`) are the consumer
extension points. The default conflict + default scorer both consume the
same `TravelLookup` seam, matching sibling semantics.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Protocol, runtime_checkable
from zoneinfo import ZoneInfo


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WorkingWindow:
    """Named time-of-day window. Names enable per-call filtering
    (`window_name="morning"`) without losing the named-window UX the
    sibling exposed via its `time_window` parameter.
    """

    name: str
    start: time
    end: time


@dataclass(frozen=True)
class BlockedInterval:
    """A pre-existing scheduled interval that constrains slot selection.

    `location_id` is the locality identifier (condo, room, address).
    `assignee_id` is optional — if present, conflict rules can be scoped
    per-assignee. Sibling did not have `assignee_id`; it's added here
    for future therapy / multi-professional use cases.
    """

    start: datetime
    end: datetime
    location_id: int | str
    assignee_id: int | str | None = None


@dataclass(frozen=True)
class Slot:
    """Candidate slot returned by the engine. `score` is filled by the
    Scorer; lower scores rank earlier in the result list."""

    start_at: datetime
    end_at: datetime
    duration_minutes: int
    score: float = 0.0


def _default_working_windows() -> list[WorkingWindow]:
    return [
        WorkingWindow(name="morning", start=time(9, 0), end=time(12, 0)),
        WorkingWindow(name="afternoon", start=time(13, 30), end=time(16, 30)),
    ]


@dataclass(frozen=True)
class SchedulingRules:
    """Engine configuration. All durations are minutes."""

    timezone: ZoneInfo
    transition_buffer_minutes: int = 10
    default_duration_minutes: int = 90
    same_location_duration_minutes: int = 60
    slot_grid_minutes: int = 30
    working_windows: list[WorkingWindow] = field(
        default_factory=_default_working_windows
    )


@dataclass(frozen=True)
class SchedulingContext:
    """Per-candidate evaluation context passed to Conflict + Scorer
    Protocol implementations. Carries the fields a sibling
    `_required_gap` / `_score` call needed beyond `(slot, blocked)`.
    """

    target_location_id: int | str
    existing_intervals_sorted: list[BlockedInterval]
    travel_lookup: TravelLookup
    rules: SchedulingRules


# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------


@runtime_checkable
class TravelLookup(Protocol):
    """Travel-minutes lookup between two locations. Same location → 0
    is the convention (the engine special-cases zero to mean "no
    transition needed" and skips the buffer)."""

    def travel_minutes(
        self,
        origin_location_id: int | str,
        destination_location_id: int | str,
    ) -> int: ...


@runtime_checkable
class Conflict(Protocol):
    """Pluggable rule that decides whether a candidate slot is valid.
    Return `True` if the slot conflicts (i.e., must be REJECTED)."""

    def applies(self, slot: Slot, context: SchedulingContext) -> bool: ...


@runtime_checkable
class Scorer(Protocol):
    """Pluggable scorer. Lower is better. Engine sorts by `(score, start_at)`."""

    def score(self, slot: Slot, context: SchedulingContext) -> float: ...


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------


class ZeroTravelLookup:
    """Travel-free lookup. Useful for scenarios where transition between
    locations is irrelevant (e.g., same-clinic therapy bookings)."""

    def travel_minutes(
        self,
        origin_location_id: int | str,
        destination_location_id: int | str,
    ) -> int:
        return 0


class DefaultConflict:
    """Mirrors sibling `_is_valid` logic, inverted to return True on conflict.

    Three checks:
    1. Direct overlap with any existing interval.
    2. Previous-interval transition buffer must not push into candidate start.
    3. Candidate end + transition buffer must not push into next interval start.
    """

    def applies(self, slot: Slot, context: SchedulingContext) -> bool:
        existing = context.existing_intervals_sorted

        # 1. Direct overlap
        for interval in existing:
            if _overlaps(slot.start_at, slot.end_at, interval.start, interval.end):
                return True

        # 2. Previous interval gap
        previous = _previous_interval(slot.start_at, existing)
        if previous is not None:
            required_gap = _required_gap(
                previous.location_id,
                context.target_location_id,
                context.travel_lookup,
                context.rules.transition_buffer_minutes,
            )
            if previous.end + required_gap > slot.start_at:
                return True

        # 3. Next interval gap
        next_interval = _next_interval(slot.end_at, existing)
        if next_interval is not None:
            required_gap = _required_gap(
                context.target_location_id,
                next_interval.location_id,
                context.travel_lookup,
                context.rules.transition_buffer_minutes,
            )
            if slot.end_at + required_gap > next_interval.start:
                return True

        return False


class DefaultScorer:
    """Sums travel minutes from previous-interval and to next-interval.
    Lower scores rank earlier (less travel = better)."""

    def score(self, slot: Slot, context: SchedulingContext) -> float:
        existing = context.existing_intervals_sorted
        total: float = 0.0

        previous = _previous_interval(slot.start_at, existing)
        if previous is not None:
            total += context.travel_lookup.travel_minutes(
                previous.location_id, context.target_location_id
            )

        next_interval = _next_interval(slot.end_at, existing)
        if next_interval is not None:
            total += context.travel_lookup.travel_minutes(
                context.target_location_id, next_interval.location_id
            )

        return total


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class SchedulingEngine:
    """Generate candidate slots for a date, filter by conflicts, score, sort.

    Defaults to `DefaultConflict` + `DefaultScorer`. Pass `conflicts=`
    to compose multiple conflict rules; first match rejects.

    Stateless — safe to share across requests.
    """

    def __init__(
        self,
        rules: SchedulingRules,
        travel_lookup: TravelLookup | None = None,
        conflicts: list[Conflict] | None = None,
        scorer: Scorer | None = None,
    ):
        self.rules = rules
        self.travel_lookup = travel_lookup if travel_lookup is not None else ZeroTravelLookup()
        self.conflicts = conflicts if conflicts is not None else [DefaultConflict()]
        self.scorer = scorer if scorer is not None else DefaultScorer()

    def candidate_slots(
        self,
        requested_date: date,
        target_location_id: int | str,
        existing_intervals: Iterable[BlockedInterval],
        window_name: str | None = None,
        duration_override_minutes: int | None = None,
    ) -> list[Slot]:
        """Return validated, scored, sorted candidate slots for the date.

        - `window_name` filters to working windows with that name (None = all).
        - `duration_override_minutes` skips the same-location-shortcut
          and forces every candidate to that duration.
        """
        existing = sorted(existing_intervals, key=lambda i: i.start)
        windows = self._windows_for(requested_date, window_name)
        candidates: list[Slot] = []

        for window_start, window_end in windows:
            cursor = window_start
            while cursor < window_end:
                duration = (
                    duration_override_minutes
                    if duration_override_minutes is not None
                    else self._duration_for(cursor, target_location_id, existing)
                )
                end_at = cursor + timedelta(minutes=duration)
                slot = Slot(
                    start_at=cursor, end_at=end_at, duration_minutes=duration
                )
                context = SchedulingContext(
                    target_location_id=target_location_id,
                    existing_intervals_sorted=existing,
                    travel_lookup=self.travel_lookup,
                    rules=self.rules,
                )
                if end_at <= window_end and not self._has_conflict(slot, context):
                    scored = Slot(
                        start_at=slot.start_at,
                        end_at=slot.end_at,
                        duration_minutes=slot.duration_minutes,
                        score=self.scorer.score(slot, context),
                    )
                    candidates.append(scored)
                cursor += timedelta(minutes=self.rules.slot_grid_minutes)

        return sorted(candidates, key=lambda s: (s.score, s.start_at))

    def _windows_for(
        self, requested_date: date, window_name: str | None
    ) -> list[tuple[datetime, datetime]]:
        selected = [
            w for w in self.rules.working_windows
            if window_name is None or w.name == window_name
        ]
        return [
            (
                datetime.combine(requested_date, w.start, tzinfo=self.rules.timezone),
                datetime.combine(requested_date, w.end, tzinfo=self.rules.timezone),
            )
            for w in selected
        ]

    def _duration_for(
        self,
        candidate_start: datetime,
        target_location_id: int | str,
        existing: list[BlockedInterval],
    ) -> int:
        previous = _previous_interval(candidate_start, existing)
        if previous is not None and previous.end == candidate_start:
            if previous.location_id == target_location_id:
                return self.rules.same_location_duration_minutes
        return self.rules.default_duration_minutes

    def _has_conflict(self, slot: Slot, context: SchedulingContext) -> bool:
        return any(rule.applies(slot, context) for rule in self.conflicts)

    def reschedule(
        self,
        original: BlockedInterval,
        requested_date: date,
        target_location_id: int | str,
        all_existing_intervals: Iterable[BlockedInterval],
        window_name: str | None = None,
        duration_override_minutes: int | None = None,
    ) -> list[Slot]:
        """Find candidate replacement slots for an interval being moved.

        `original` is excluded from `all_existing_intervals` before slot
        generation, so its timeslot becomes available again. Otherwise
        identical to `candidate_slots`.

        Cancel vs. reschedule: cancellation is consumer-side — the consumer
        deletes the row from its DB and the next `candidate_slots` call
        naturally honors the absence. `reschedule` exists for the case where
        the original isn't yet deleted but the consumer wants to evaluate
        replacement options first.
        """
        pruned = [i for i in all_existing_intervals if i != original]
        return self.candidate_slots(
            requested_date=requested_date,
            target_location_id=target_location_id,
            existing_intervals=pruned,
            window_name=window_name,
            duration_override_minutes=duration_override_minutes,
        )


# ---------------------------------------------------------------------------
# Helpers (module-private)
# ---------------------------------------------------------------------------


def _overlaps(
    start_a: datetime, end_a: datetime, start_b: datetime, end_b: datetime
) -> bool:
    return start_a < end_b and start_b < end_a


def _previous_interval(
    moment: datetime, existing: list[BlockedInterval]
) -> BlockedInterval | None:
    previous = [i for i in existing if i.end <= moment]
    return previous[-1] if previous else None


def _next_interval(
    moment: datetime, existing: list[BlockedInterval]
) -> BlockedInterval | None:
    upcoming = [i for i in existing if i.start >= moment]
    return upcoming[0] if upcoming else None


def _required_gap(
    origin_location_id: int | str,
    destination_location_id: int | str,
    travel_lookup: TravelLookup,
    transition_buffer_minutes: int,
) -> timedelta:
    travel = travel_lookup.travel_minutes(origin_location_id, destination_location_id)
    if travel == 0:
        return timedelta()
    return timedelta(minutes=travel + transition_buffer_minutes)
