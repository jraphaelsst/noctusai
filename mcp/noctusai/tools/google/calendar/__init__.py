"""``google.calendar.*`` — Google Calendar event tools.

Tools:
  - ``google.calendar.create_event``
  - ``google.calendar.delete_event``
  - ``google.calendar.get_event``
  - ``google.calendar.list_events``

All wrap ``noctusai_lib.integrations.google_calendar.CalendarAdapter``.
"""

from __future__ import annotations


def register_all(server) -> None:
    """Register every tool under ``google.calendar.*``."""
    from . import create_event, delete_event, get_event, list_events

    create_event.register(server)
    delete_event.register(server)
    get_event.register(server)
    list_events.register(server)


__all__ = ["register_all"]
