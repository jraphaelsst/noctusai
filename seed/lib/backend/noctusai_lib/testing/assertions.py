"""Assertion helpers for product test suites.

Single source of truth for assertions that recur across products' test files.
Keep these helpers small and shape-agnostic — they should not assume more
about the response than what the platform contract guarantees.
"""
from __future__ import annotations

from typing import Any


def assert_error_contains(response: Any, expected_substring: str) -> None:
    """Assert the response body's error message contains `expected_substring`.

    The platform's exception-handler shape is `{"error": {"code": ..., "message": ...}}`
    (added by `noctusai_seed.app.create_product_app`). This helper falls back
    to FastAPI's default `{"detail": ...}` shape when the wrapper isn't
    installed (e.g. specific test fixtures without the full app).

    Trip history (recurrence rule N≥4 → MUST formalize, 2026-04-29):
    - 4 sites in `products/therapy-platform/backend/tests/routers/test_messaging_router.py`
      (TestStartConversation, TestSendMessage block-paths, etc.) all wanted
      the same "extract message from platform-or-FastAPI error shape, assert
      substring" assertion.

    Args:
        response: TestClient response (anything with `.json()` returning a dict).
        expected_substring: substring expected in the error message.

    Raises:
        AssertionError: if neither the platform nor FastAPI error shape
            contains the substring; the message includes the actual body
            for debugging.
    """
    body = response.json()
    msg = body.get("error", {}).get("message", "") or body.get("detail", "")
    assert expected_substring in msg, (
        f"Expected {expected_substring!r} in error message; got: {body!r}"
    )


def handler_status(response: Any) -> int:
    """The status the HANDLER chose, read through `EdgeSafeStatusMiddleware`.

    A seed-built app (`create_product_app`) never puts 502/504 on the wire —
    CloudFlare would replace the body — it sends 503 and keeps the handler's
    choice in `X-Upstream-Status`. Tests that pin "this upstream failure is a
    502" assert `handler_status(resp) == 502`: that still checks the handler's
    intent AND that the wire status is the edge-safe one.

    Trip history (2026-10-26): 46 full-app assertions across agents, core,
    igig, orbity and social-wiring pinned the raw wire 502.

    Raises:
        AssertionError: a raw 502/504 reached the wire (an app not built
            through the seed factory), or the header is present on a status
            other than the edge-safe one.
    """
    from noctusai_lib.api.middleware import (
        EDGE_MASKED_STATUSES,
        EDGE_SAFE_STATUS,
        UPSTREAM_STATUS_HEADER,
    )

    status = response.status_code
    assert status not in EDGE_MASKED_STATUSES, (
        f"a raw {status} left the app — CloudFlare would discard its body; "
        "build the app through create_product_app (EdgeSafeStatusMiddleware)"
    )
    original = response.headers.get(UPSTREAM_STATUS_HEADER)
    if original is None:
        return status
    assert status == EDGE_SAFE_STATUS, (
        f"{UPSTREAM_STATUS_HEADER}={original} on a {status} response"
    )
    return int(original)
