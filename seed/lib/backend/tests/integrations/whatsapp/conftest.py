"""Autouse fixture: virtual clock for the shared `rate_limit` "whatsapp"
bucket across every test in this package.

`WahaClient._request`/`_request_sync` now pace every call via
`rate_limit.acquire_async("whatsapp")` / `rate_limit.acquire("whatsapp")`
(closing the prior `NOC-REMEDIATE[rate-limit]`). The bucket + its clock
are process-wide singletons (`noctusai_lib.integrations.rate_limit.limiter`
/ `_async_registry`), so without this fixture a busy test run could start
incurring small REAL sleeps once the burst allowance (10 tokens) is
exhausted. A `VirtualClock` makes the pacing math run for real (tokens
still refill, still gate) without ever wall-clock-waiting — the same
pattern `tests/integrations/meta/test_meta_integration.py` already
established for the `"meta"` bucket.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _virtual_rate_limit_clock():
    from noctusai_lib.integrations import rate_limit

    rate_limit.set_default_clock(rate_limit.VirtualClock())
    rate_limit._reset_all_buckets()
    yield
    rate_limit.reset_default_clock()
    rate_limit._reset_all_buckets()


@pytest.fixture(autouse=True)
def _legacy_enabled_line_policy():
    """These suites predate line policy v1 and exercise the send path of raw `WahaClient`s: declare the process-wide
    legacy policy (`send: enabled`, today's behaviour) through the PUBLIC registry. Fail-closed behaviour has its own
    suite (`test_line_policy.py`), which clears the registry first."""
    from noctusai_lib.integrations.whatsapp import (
        LinePolicy,
        clear_line_policies,
        register_line_policy,
    )

    clear_line_policies()
    register_line_policy("*", LinePolicy("enabled", True, True, True))
    yield
    clear_line_policies()
