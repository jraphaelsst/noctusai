"""Per-call dependency container for MCP business / vendor tools.

A `NoctusContext` lazily exposes the adapters a vendor-leaf tool might
need: the Google Calendar adapter, the Google Maps routing adapter.
Each property builds its dependency on first access and caches it for
the lifetime of the context.

LLM tools (`llm.audio.*`, `llm.vision.*`) DO NOT pass through this
context — `noctusai_lib.integrations.llm.*` resolves its own provider
and API key per call, so the MCP tool wraps the lib function directly.

Each MCP tool gets a fresh context per call. Tools NEVER touch globals.
That keeps them callable in three modes:

1. From the MCP server — FastMCP calls `tool(payload)` which builds a
   default context internally.
2. In-process from a product — caller constructs a context with their
   own adapter handles.
3. From tests — tests construct a context with `Fake*Adapter` /
   `Static*Adapter` injected.

Pattern: `KB § PATTERNS/mcp-tool-conventions.md § 4. Lazy NoctusContext`.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from noctusai_lib.integrations.google_calendar import CalendarAdapter
    from noctusai_lib.integrations.google_maps import RoutingAdapter


class NoctusContext:
    """Lazy dependency container.

    Pass adapter instances to override defaults — useful for tests and
    for callers that already hold configured adapters.
    """

    def __init__(
        self,
        calendar: "CalendarAdapter | None" = None,
        routing: "RoutingAdapter | None" = None,
    ):
        self._calendar = calendar
        self._routing = routing

    @property
    def calendar(self) -> "CalendarAdapter":
        if self._calendar is None:
            from noctusai_lib.integrations.google_calendar import get_calendar_adapter

            self._calendar = get_calendar_adapter()
        return self._calendar

    @property
    def routing(self) -> "RoutingAdapter":
        if self._routing is None:
            from noctusai_lib.integrations.google_maps import get_routing_adapter

            api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
            self._routing = get_routing_adapter(api_key)
        return self._routing


@contextmanager
def noctus_context(
    calendar: "CalendarAdapter | None" = None,
    routing: "RoutingAdapter | None" = None,
) -> Iterator[NoctusContext]:
    yield NoctusContext(calendar=calendar, routing=routing)
