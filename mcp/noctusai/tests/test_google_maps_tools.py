"""Tests for ``google.maps.travel_estimate`` MCP tool.

Uses ``StaticRoutingAdapter`` (the deterministic dev/test fallback) via
``NoctusContext`` so tests run without a Google Maps API key.
"""

from __future__ import annotations

import sys
from pathlib import Path

MCP_ROOT = Path(__file__).resolve().parents[1]
if str(MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(MCP_ROOT))

from context import NoctusContext  # noqa: E402
from noctusai_lib.integrations.google_maps import StaticRoutingAdapter  # noqa: E402
from tools.google.maps.travel_estimate import (  # noqa: E402
    CoordinatesInput,
    TravelEstimateInput,
    travel_estimate,
)


def test_travel_estimate_returns_minutes():
    ctx = NoctusContext(routing=StaticRoutingAdapter())
    out = travel_estimate(
        TravelEstimateInput(
            origin=CoordinatesInput(latitude=-23.5505, longitude=-46.6333),
            destination=CoordinatesInput(latitude=-23.5475, longitude=-46.6361),
        ),
        ctx=ctx,
    )
    assert isinstance(out.minutes, int)
    assert out.minutes >= 0
