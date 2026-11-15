from __future__ import annotations

import pytest

from noctusai_lib.integrations import rate_limit


@pytest.fixture(autouse=True)
def virtual_clock():
    """Pacing/backoff logic runs for real; nothing wall-waits."""
    clock = rate_limit.VirtualClock()
    rate_limit.set_default_clock(clock)
    rate_limit.limiter._reset()
    rate_limit._async_registry._reset()
    rate_limit._overrides.clear()
    yield clock
    rate_limit.reset_default_clock()
    rate_limit.limiter._reset()
    rate_limit._async_registry._reset()
    rate_limit._overrides.clear()
