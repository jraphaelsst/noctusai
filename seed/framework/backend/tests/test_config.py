"""Tests for ``noctusai_seed.config.make_get_settings``.

The factory is the production-DI seam that replaces direct
``monkeypatch.setattr(settings, "X", "Y")`` / a ``settings_override`` conftest
fixture (both trip ``check_no_self_monkeypatch`` — the keeper can't tell a
config-value patch from a logic-guard patch). Routing settings through
``Depends(get_settings)`` lets tests override via FastAPI's own
``app.dependency_overrides`` instead of mutating a module global.

Born with ``social-wiring-settings-di-rewrite`` (the N>=3 recurrence
formalization). Network-free.
"""
from __future__ import annotations

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from noctusai_seed import make_get_settings
from noctusai_seed.config import ProductSettings


class _DemoSettings(ProductSettings):
    """A minimal product-settings subclass for the seam tests."""

    demo_flag: str = ""


def test_dep_returns_the_bound_instance():
    s = _DemoSettings(demo_flag="prod")
    get_settings = make_get_settings(s)
    assert get_settings() is s


def test_each_factory_call_binds_its_own_instance():
    a = _DemoSettings(demo_flag="a")
    b = _DemoSettings(demo_flag="b")
    assert make_get_settings(a)() is a
    assert make_get_settings(b)() is b


def test_dependency_override_replaces_the_value_without_patching():
    """End-to-end through FastAPI: the production path returns the bound
    singleton; ``app.dependency_overrides`` swaps it in tests — the honest
    replacement for ``monkeypatch.setattr(settings, ...)``."""
    prod = _DemoSettings(demo_flag="prod-value")
    get_settings = make_get_settings(prod)

    app = FastAPI()

    @app.get("/flag")
    def read_flag(settings: _DemoSettings = Depends(get_settings)):
        return {"flag": settings.demo_flag}

    client = TestClient(app)
    # Production path: the bound instance.
    assert client.get("/flag").json() == {"flag": "prod-value"}

    # Test override path: FastAPI's own mechanism, no global mutation.
    app.dependency_overrides[get_settings] = lambda: _DemoSettings(demo_flag="overridden")
    assert client.get("/flag").json() == {"flag": "overridden"}

    # Cleanup restores production behavior (mirrors per-test teardown).
    app.dependency_overrides.clear()
    assert client.get("/flag").json() == {"flag": "prod-value"}
