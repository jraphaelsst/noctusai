"""ProfessionalAvailabilityConflict — therapist-availability gate for the
seed scheduling engine.

The seed engine (`noctusai_lib.domain.scheduling.engine.SchedulingEngine`)
reasons about a single `target_location_id` (clinic, or therapist when
solo) and a flat list of `BlockedInterval`s. It does NOT know about
therapist availability windows. This Conflict closes that gap.

**Shape:** the Conflict closes over a `Callable[[date], list[AvailabilityWindow]]`
supplied by the service layer. The lookup returns the therapist's
materialized windows for a single date — recurring-slot conversion,
one-off blocks, and DB queries all live in the service layer. The
Conflict body stays small and pure-functional, which makes it
straightforward to unit-test against fabricated windows.

**Reject rule** (`applies(slot, ...) -> True` means REJECT):

1. Any blocked window that *overlaps* the candidate slot rejects the
   slot. Blocks beat availability.
2. Otherwise, the slot is valid only when at least one available
   window *fully contains* the candidate slot's [start_at, end_at)
   interval. Half-open intervals — a slot ending exactly at a window's
   end_at is a fit; a slot starting exactly at a window's end_at is not.

See:
- `products/therapy-platform/projects/therapy-scheduling-pilot/PROJECT.md` § Phase 1.
- `seed/lib/backend/noctusai_lib/domain/scheduling/engine.py` (Protocol + Slot).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Callable

from noctusai_lib.domain.scheduling.engine import SchedulingContext, Slot


@dataclass(frozen=True)
class AvailabilityWindow:
    """A single resolved availability window for a therapist on one
    date. Half-open [start_at, end_at).

    `is_blocked=True` flips this from "available" to "unavailable" —
    used for one-off `availability_slots.is_blocked=true` rows that
    override an underlying recurring window.
    """

    start_at: datetime
    end_at: datetime
    is_blocked: bool = False


class ProfessionalAvailabilityConflict:
    """Reject candidate slots that fall outside a therapist's
    available windows OR inside a blocked window.

    Construction is per scheduling request: the service layer fetches
    the therapist's slots once, materializes a per-date lookup, then
    builds the engine with this Conflict in `conflicts=[...]`.
    """

    def __init__(
        self,
        availability_lookup: Callable[[date], list[AvailabilityWindow]],
    ) -> None:
        self._lookup = availability_lookup

    def applies(self, slot: Slot, context: SchedulingContext) -> bool:
        windows = self._lookup(slot.start_at.date())

        for window in windows:
            if window.is_blocked and self._overlaps(slot, window):
                return True

        for window in windows:
            if not window.is_blocked and self._contains(window, slot):
                return False

        return True

    @staticmethod
    def _overlaps(slot: Slot, window: AvailabilityWindow) -> bool:
        return slot.start_at < window.end_at and window.start_at < slot.end_at

    @staticmethod
    def _contains(window: AvailabilityWindow, slot: Slot) -> bool:
        return window.start_at <= slot.start_at and slot.end_at <= window.end_at
