"""Tests for `noctusai_lib.testing.fixtures.reset_rate_limiter`.

Coverage:

(a) The exported callable IS a pytest fixture marked ``autouse=True`` —
    re-importing it into a product conftest is sufficient to activate it
    without per-product ``@pytest.fixture(autouse=True)`` boilerplate.

(b) Body behavior: the fixture's underlying generator function, driven
    against a stub ``app.rate_limit`` module, invokes ``limiter.reset()``
    both pre-yield AND post-yield — defending against cross-test pollution
    from rate-limit decorators.

Important: we **don't** ``from … import reset_rate_limiter`` at module
scope. The fixture is ``autouse=True``, and a top-level import would
make pytest activate it for the tests in *this* file — which would fail
because the seed-lib session has no real ``app.rate_limit`` to import.
Instead, every test imports the fixture lazily through ``importlib``,
keeping autouse activation scoped to product conftests (the intended
consumers).
"""
from __future__ import annotations

import importlib
import sys
import types
from unittest.mock import MagicMock

import pytest


def _load_reset_rate_limiter():
    """Lazy-load the fixture symbol; never expose it at module scope.

    Autouse fixtures activate in any namespace they're visible at
    collection time. Keeping the import inside the test bodies stops
    pytest from auto-applying ``reset_rate_limiter`` to *these* tests
    (which lack a real ``app.rate_limit`` module).
    """
    fixtures_mod = importlib.import_module("noctusai_lib.testing.fixtures")
    return fixtures_mod.reset_rate_limiter


# ─── Fixture metadata ───────────────────────────────────────────────────────


def test_reset_rate_limiter_is_pytest_fixture_marked_autouse() -> None:
    """The exported callable IS a pytest fixture with ``autouse=True``.

    Pytest's modern ``@pytest.fixture`` (pytest 8+) wraps the function in
    a ``FixtureFunctionDefinition`` carrying a ``_fixture_function_marker``
    of type ``FixtureFunctionMarker(autouse=...)``. Older pytest exposed
    the same data as ``_pytestfixturefunction``. We probe both shapes so
    the test survives pytest minor-version drift; the assertion is the
    public contract — products re-import the fixture and rely on the
    autouse activation.
    """
    fixture = _load_reset_rate_limiter()
    # Modern shape (pytest 8+):
    modern_marker = getattr(fixture, "_fixture_function_marker", None)
    # Legacy shape (pytest <8):
    legacy_marker = getattr(fixture, "_pytestfixturefunction", None)
    marker = modern_marker or legacy_marker
    assert marker is not None, (
        "reset_rate_limiter is not a pytest fixture; products re-importing "
        "it via `from … import reset_rate_limiter  # noqa: F401` would "
        "not get autouse activation"
    )
    assert getattr(marker, "autouse", False) is True, (
        "reset_rate_limiter must be autouse — product conftests rely on "
        "bare import sufficient for cross-test limiter cleanup"
    )


# ─── Body behavior ──────────────────────────────────────────────────────────


def _get_underlying_generator_fn(fixture):
    """Return the unwrapped generator function from the fixture wrapper.

    Pytest 8+ exposes ``_get_wrapped_function``; legacy pytest exposed
    ``__wrapped__``. Either way, the result is the raw generator function
    we authored in ``fixtures.py``.
    """
    if hasattr(fixture, "_get_wrapped_function"):
        return fixture._get_wrapped_function()
    return fixture.__wrapped__


@pytest.fixture
def stub_app_rate_limit():
    """Inject a stub ``app.rate_limit`` module with a mock ``limiter`` for the test.

    Seed-lib tests don't have a product ``app`` package on the import
    path; the fixture body's ``from app.rate_limit import limiter`` would
    raise ``ModuleNotFoundError`` without this stub. Snapshot/restore
    keeps the stub scoped to a single test.
    """
    saved_app = sys.modules.get("app")
    saved_rate_limit = sys.modules.get("app.rate_limit")

    app_mod = types.ModuleType("app")
    rate_limit_mod = types.ModuleType("app.rate_limit")
    rate_limit_mod.limiter = MagicMock(name="slowapi_limiter")
    app_mod.rate_limit = rate_limit_mod  # type: ignore[attr-defined]
    sys.modules["app"] = app_mod
    sys.modules["app.rate_limit"] = rate_limit_mod

    yield rate_limit_mod.limiter

    # Restore exactly — drop stubs if they weren't there before, restore originals.
    if saved_app is None:
        sys.modules.pop("app", None)
    else:
        sys.modules["app"] = saved_app
    if saved_rate_limit is None:
        sys.modules.pop("app.rate_limit", None)
    else:
        sys.modules["app.rate_limit"] = saved_rate_limit


def test_reset_rate_limiter_resets_pre_and_post_yield(stub_app_rate_limit) -> None:
    """The fixture body calls ``limiter.reset()`` both before AND after yield.

    Calling reset both sides defends against (a) state leaked into the
    test by an earlier test in the session and (b) state left behind by
    the current test. Drives the underlying generator manually to verify
    both calls happen.
    """
    limiter = stub_app_rate_limit
    fixture = _load_reset_rate_limiter()
    fn = _get_underlying_generator_fn(fixture)
    gen = fn()

    # Step 1: enter the fixture (pre-yield reset)
    next(gen)
    assert limiter.reset.call_count == 1, (
        "fixture body must reset limiter before yielding"
    )

    # Step 2: exit the fixture (post-yield reset)
    with pytest.raises(StopIteration):
        next(gen)
    assert limiter.reset.call_count == 2, (
        "fixture body must reset limiter after yielding"
    )
