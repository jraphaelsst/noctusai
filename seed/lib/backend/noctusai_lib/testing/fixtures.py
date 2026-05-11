"""Shared pytest fixtures for product test suites.

Lift history (`projects/seed-rate-limit-fixture-absorption/PROJECT.md`):
    * N=5 byte-identical `_reset_rate_limiter` autouse fixtures pre-existed
      (core, daily-life, mailing, media-scheduling, therapy-platform);
    * each cleared the slowapi module-level limiter between tests to avoid
      cross-test pollution from rate-limit decorators;
    * unified canonical lives here. Each product conftest re-imports the
      fixture for autouse discovery::

          from noctusai_lib.testing.fixtures import reset_rate_limiter  # noqa: F401

Usage notes:
    * The fixture imports ``app.rate_limit.limiter`` lazily at fixture
      invocation time. Products MUST expose this module (the seed factory
      `create_product_app` wires it via `standard_routers=[...]`).
    * Autouse via re-export: pytest discovers autouse fixtures in the
      conftest's namespace; the bare ``from … import reset_rate_limiter``
      line is sufficient to activate it — the ``# noqa: F401`` suppresses
      the unused-import lint.
    * Pure-logic shape: no IO, no Fake/Real split needed — this fixture
      orchestrates a side-effect (limiter reset) only against the
      product's own ``app.rate_limit`` module.
"""
from __future__ import annotations

import pytest

__all__ = ["reset_rate_limiter"]


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Reset the slowapi limiter between tests.

    slowapi keeps in-memory counters at module scope; without this fixture,
    decorated endpoints that get hit N+ times across the suite would
    surface 429s in unrelated tests. Lifted to seed-lib 2026-05-11 after
    the rate-limit fixture appeared in 5 product conftests (N=3 MUST-
    formalize threshold cleared by N=5).

    The lazy import of ``app.rate_limit`` keeps this module importable
    from non-product contexts (seed-lib own tests, mcp tests) — the
    fixture only executes when actually triggered by a test session that
    has the product app on its import path.
    """
    from app.rate_limit import limiter
    limiter.reset()
    yield
    limiter.reset()
