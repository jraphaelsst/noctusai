"""Google Calendar adapter — Fake (shipped) + Google service-account /
OAuth (deferred to follow-up).

Lifted 2026-05-03 by `projects/whatsapp-seed-absorption/` Phase 7 from
`whatsapp-google-scheduling/app/services/calendar/`.

**What ships in this Phase 7:**
- `EventInput`, `EventAttendee`, `CreatedEvent` value objects.
- `CalendarAdapter` Protocol.
- `FakeCalendarAdapter` — deterministic in-memory implementation for
  dev + tests. Mirrors the Google Calendar v3 response shape so
  consumer code can swap real/fake transparently.
- Pure-function mappers (`event_to_google_body`,
  `google_body_to_created_event`, `parse_google_datetime`).
- `EventInput.request_id` field — Google's
  per-request idempotency key (sibling
  `idempotency-keys` idea folded into types per project §6 Phase 7).

**Deferred to follow-up project** (`google-calendar-real-adapters`
recommended slug):
- `GoogleCalendarAdapter` (service-account auth via
  `google-auth` + `googleapiclient`).
- `GoogleCalendarOAuthAdapter` (consenting-user auth, refresh-token
  exchange, persistent credential repo abstracted via consumer-supplied
  Callable).
- `_google_api` HTTP shims.

Why deferred: the real adapters require `google-auth` +
`googleapiclient` runtime deps, mockable tests, and a credential-repo
abstraction story. Bounded scope here ships the testable shape; the
real-adapter follow-up is a small, focused project once a consumer
needs live Google calls (the consumer's `imobi-scheduling-bot-creation`
Phase 6 wiring is the natural trigger).

**Default factory** (`get_calendar_adapter`): returns `FakeCalendarAdapter`
unconditionally for now. When the real adapters land, this factory
gains the OAuth → service-account → fake fallback ladder per the
`KB § PATTERNS/integrations-fake-fallback.md` pattern.
"""

from noctusai_lib.integrations.google_calendar.fake_adapter import FakeCalendarAdapter
from noctusai_lib.integrations.google_calendar.mappers import (
    event_to_google_body,
    google_body_to_created_event,
    parse_google_datetime,
)
from noctusai_lib.integrations.google_calendar.types import (
    CalendarAdapter,
    CreatedEvent,
    EventAttendee,
    EventInput,
)


def get_calendar_adapter() -> CalendarAdapter:
    """Default-factory placeholder — returns `FakeCalendarAdapter`.

    Until the Google service-account + OAuth adapters land in the
    follow-up project, consumers can wire `FakeCalendarAdapter` directly
    or override this factory. Kept here so the consumer wiring shape
    (per `KB § PATTERNS/scheduling-seed.md` pattern) is stable across
    the lift."""
    return FakeCalendarAdapter()


__all__ = [
    "CalendarAdapter",
    "CreatedEvent",
    "EventAttendee",
    "EventInput",
    "FakeCalendarAdapter",
    "event_to_google_body",
    "get_calendar_adapter",
    "google_body_to_created_event",
    "parse_google_datetime",
]
