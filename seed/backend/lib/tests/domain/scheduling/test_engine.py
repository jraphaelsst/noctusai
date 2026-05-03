"""SchedulingEngine tests — 5 cases ported from sibling
(`whatsapp-google-scheduling/tests/test_scheduling_service.py`,
2026-05-03 absorption) with vocabulary translated, plus 4 seed-lib-only
cases for the explicit Scorer / TravelLookup Protocols.
"""

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from noctusai_lib.domain.scheduling import (
    BlockedInterval,
    DefaultScorer,
    SchedulingContext,
    SchedulingEngine,
    SchedulingRules,
    Slot,
    ZeroTravelLookup,
)


TZ = ZoneInfo("America/Sao_Paulo")


class _StubTravelLookup:
    """Minimal in-test travel lookup. Returns 0 for same-location, fixed
    minutes otherwise."""

    def __init__(self, default_minutes: int = 20):
        self.default_minutes = default_minutes

    def travel_minutes(
        self,
        origin_location_id,
        destination_location_id,
    ) -> int:
        if origin_location_id == destination_location_id:
            return 0
        return self.default_minutes


def at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 5, 12, hour, minute, tzinfo=TZ)


def engine(default_travel_minutes: int = 20) -> SchedulingEngine:
    rules = SchedulingRules(timezone=TZ, transition_buffer_minutes=10)
    return SchedulingEngine(
        rules=rules,
        travel_lookup=_StubTravelLookup(default_minutes=default_travel_minutes),
    )


# ---------------------------------------------------------------------------
# Ported sibling tests (5)
# ---------------------------------------------------------------------------


def test_generates_standard_morning_slots_without_existing_appointments() -> None:
    slots = engine().candidate_slots(
        date(2026, 5, 12),
        target_location_id=1,
        existing_intervals=[],
        window_name="morning",
    )

    assert [
        (slot.start_at.time().isoformat(), slot.end_at.time().isoformat())
        for slot in slots
    ] == [
        ("09:00:00", "10:30:00"),
        ("09:30:00", "11:00:00"),
        ("10:00:00", "11:30:00"),
        ("10:30:00", "12:00:00"),
    ]


def test_blocks_lunch_by_using_fixed_working_windows() -> None:
    slots = engine().candidate_slots(
        date(2026, 5, 12), target_location_id=1, existing_intervals=[]
    )

    assert all(
        not (slot.start_at.time().hour == 12 or slot.end_at.time().hour == 13)
        for slot in slots
    )


def test_same_location_back_to_back_can_use_one_hour() -> None:
    existing = [
        BlockedInterval(start=at(9), end=at(10), location_id=7),
    ]

    slots = engine().candidate_slots(
        date(2026, 5, 12),
        target_location_id=7,
        existing_intervals=existing,
        window_name="morning",
    )

    assert any(
        slot.start_at == at(10) and slot.end_at == at(11) and slot.duration_minutes == 60
        for slot in slots
    )


def test_custom_working_windows_override_defaults() -> None:
    from noctusai_lib.domain.scheduling import WorkingWindow

    custom_rules = SchedulingRules(
        timezone=TZ,
        transition_buffer_minutes=10,
        working_windows=[
            WorkingWindow(name="morning", start=time(8, 0), end=time(11, 0)),
            WorkingWindow(name="afternoon", start=time(14, 0), end=time(17, 0)),
        ],
    )
    custom_engine = SchedulingEngine(
        rules=custom_rules, travel_lookup=_StubTravelLookup()
    )

    morning_slots = custom_engine.candidate_slots(
        date(2026, 5, 12),
        target_location_id=1,
        existing_intervals=[],
        window_name="morning",
    )

    assert morning_slots[0].start_at.time() == time(8, 0)

    afternoon_slots = custom_engine.candidate_slots(
        date(2026, 5, 12),
        target_location_id=1,
        existing_intervals=[],
        window_name="afternoon",
    )
    assert any(slot.start_at.time() == time(14, 0) for slot in afternoon_slots)


def test_different_location_requires_transition_buffer_after_previous() -> None:
    existing = [BlockedInterval(start=at(9), end=at(10), location_id=1)]

    slots = engine(default_travel_minutes=20).candidate_slots(
        date(2026, 5, 12),
        target_location_id=2,
        existing_intervals=existing,
        window_name="morning",
    )

    # 10:00 must be rejected — previous ends at 10:00, target is different
    # location, travel=20min + buffer=10min → next valid start is 10:30.
    assert all(slot.start_at != at(10) for slot in slots)
    assert any(slot.start_at == at(10, 30) for slot in slots)


# ---------------------------------------------------------------------------
# Seed-lib-only tests (Scorer Protocol surface)
# ---------------------------------------------------------------------------


def test_default_scorer_zero_when_no_neighbors() -> None:
    rules = SchedulingRules(timezone=TZ)
    slot = Slot(start_at=at(9), end_at=at(10, 30), duration_minutes=90)
    context = SchedulingContext(
        target_location_id=1,
        existing_intervals_sorted=[],
        travel_lookup=_StubTravelLookup(),
        rules=rules,
    )
    assert DefaultScorer().score(slot, context) == 0.0


def test_default_scorer_sums_travel_to_previous_and_next() -> None:
    rules = SchedulingRules(timezone=TZ)
    existing = sorted(
        [
            BlockedInterval(start=at(7), end=at(8, 30), location_id=99),
            BlockedInterval(start=at(11), end=at(12), location_id=88),
        ],
        key=lambda i: i.start,
    )
    slot = Slot(start_at=at(9), end_at=at(10, 30), duration_minutes=90)
    context = SchedulingContext(
        target_location_id=1,
        existing_intervals_sorted=existing,
        travel_lookup=_StubTravelLookup(default_minutes=20),
        rules=rules,
    )
    # Previous (loc 99 → target 1): 20 min. Next (target 1 → loc 88): 20 min.
    assert DefaultScorer().score(slot, context) == 40.0


def test_engine_sorts_by_score_then_start_at() -> None:
    # Same-location previous (score adds 0) ranks before different-location.
    existing = [
        BlockedInterval(start=at(8), end=at(9), location_id=1),
    ]
    slots = engine(default_travel_minutes=15).candidate_slots(
        date(2026, 5, 12),
        target_location_id=1,
        existing_intervals=existing,
        window_name="morning",
    )

    # All slots produced; the one starting right after the same-location
    # previous (at 9:00) should score 0 (no travel from previous, no next).
    same_loc_after = [s for s in slots if s.start_at == at(9)]
    assert same_loc_after, "expected a 9:00 slot following the same-location interval"
    assert same_loc_after[0].score == 0.0

    # Sort key invariant: list is ordered (score, start_at) ascending.
    for a, b in zip(slots, slots[1:]):
        assert (a.score, a.start_at) <= (b.score, b.start_at)


def test_reschedule_excludes_original_interval_from_conflicts() -> None:
    """Reschedule must free up the original slot so it can be re-proposed."""
    original = BlockedInterval(start=at(10), end=at(11, 30), location_id=5)
    other = BlockedInterval(start=at(9), end=at(10), location_id=5)
    all_intervals = [original, other]

    eng = engine()
    # Without reschedule: 10:00 is blocked (`original` runs 10:00-11:30).
    blocked_slots = eng.candidate_slots(
        date(2026, 5, 12),
        target_location_id=5,
        existing_intervals=all_intervals,
        window_name="morning",
    )
    assert all(slot.start_at != at(10) for slot in blocked_slots), \
        "original interval should block 10:00 when present"

    # With reschedule: 10:00 frees up because original is excluded.
    reschedule_slots = eng.reschedule(
        original=original,
        requested_date=date(2026, 5, 12),
        target_location_id=5,
        all_existing_intervals=all_intervals,
        window_name="morning",
    )
    assert any(slot.start_at == at(10) for slot in reschedule_slots), \
        "reschedule must surface 10:00 as a candidate (original excluded)"


def test_reschedule_preserves_same_location_duration_shortcut() -> None:
    """Same-location back-to-back behavior must survive reschedule."""
    original = BlockedInterval(start=at(11, 30), end=at(13), location_id=7)
    previous = BlockedInterval(start=at(9), end=at(10), location_id=7)
    all_intervals = [previous, original]

    slots = engine().reschedule(
        original=original,
        requested_date=date(2026, 5, 12),
        target_location_id=7,
        all_existing_intervals=all_intervals,
        window_name="morning",
    )

    # 10:00 follows the same-location previous → same_location_duration (60).
    same_loc_after = [s for s in slots if s.start_at == at(10)]
    assert same_loc_after
    assert same_loc_after[0].duration_minutes == 60


def test_zero_travel_lookup_produces_zero_buffers() -> None:
    """ZeroTravelLookup should make different-location transitions
    behave like same-location (no buffer)."""
    existing = [BlockedInterval(start=at(9), end=at(10), location_id=1)]
    rules = SchedulingRules(timezone=TZ)
    eng = SchedulingEngine(rules=rules, travel_lookup=ZeroTravelLookup())

    slots = eng.candidate_slots(
        date(2026, 5, 12),
        target_location_id=2,  # different location, but ZeroTravelLookup → 0
        existing_intervals=existing,
        window_name="morning",
    )

    # 10:00 SHOULD be valid — zero travel + zero gap rule.
    assert any(slot.start_at == at(10) for slot in slots)
