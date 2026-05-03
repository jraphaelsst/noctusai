"""Scheduling — therapy-platform pilot consumer of `noctusai_lib.domain.scheduling`.

See `products/therapy-platform/projects/therapy-scheduling-pilot/PROJECT.md`.
"""
from app.services.scheduling.conflicts import (
    AvailabilityWindow,
    ProfessionalAvailabilityConflict,
)
from app.services.scheduling.credentials import TherapyGcalCredentialResolver
from app.services.scheduling.service import (
    book_appointment,
    cancel_appointment,
    generate_candidate_slots,
    list_blocked_intervals,
    materialize_availability_lookup,
    reschedule_appointment,
    resolve_calendar_for_therapist,
)

__all__ = [
    "AvailabilityWindow",
    "ProfessionalAvailabilityConflict",
    "TherapyGcalCredentialResolver",
    "book_appointment",
    "cancel_appointment",
    "generate_candidate_slots",
    "list_blocked_intervals",
    "materialize_availability_lookup",
    "reschedule_appointment",
    "resolve_calendar_for_therapist",
]
