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
