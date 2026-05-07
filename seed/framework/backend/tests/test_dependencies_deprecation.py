"""Regression tests for the Phase-2 deprecation warning on
``ProductDependencies.get_org_id`` / ``get_user_role`` / ``get_user_client``.

The warning is intentionally narrow: it fires ONLY when FastAPI's
dependency-injection machinery (``fastapi.dependencies.utils``) is the
immediate caller. Imperative call sites (route bodies, services,
internal seed routers) MUST NOT trigger it — that would generate
noise without changing behavior.

See ``KB § PATTERNS/backend.md § Auth — canonical pattern`` for the
full rationale + the canonical migration path.
"""
from __future__ import annotations

import sys
import types
import warnings

import pytest

from noctusai_seed.dependencies import (
    ProductDependencies,
    _warn_if_fastapi_caller,
)


class _FakeUser:
    """Minimal stand-in for the Supabase user object."""

    def __init__(self, metadata: dict | None = None):
        self.user_metadata = metadata or {}


def test_imperative_call_emits_no_warning():
    """``deps.get_org_id(user)`` from a script-level call site must be
    silent. This is the dominant call shape in seed routers + product
    services and triggering on it would generate constant noise."""
    deps = ProductDependencies(db=object())
    user = _FakeUser({"org_id": "org-123"})

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        org_id = ProductDependencies.get_org_id(user)
        role = ProductDependencies.get_user_role(user)

    assert org_id == "org-123"
    assert role == "user"
    auth_warns = [w for w in caught if issubclass(w.category, DeprecationWarning)
                  and "ProductDependencies" in str(w.message)]
    assert auth_warns == [], (
        "Imperative call must not emit the auth-Depends deprecation "
        f"warning. Got: {[str(w.message) for w in auth_warns]}"
    )


def test_fastapi_dependency_call_emits_warning():
    """Simulate the call shape FastAPI's solver uses — i.e., invoking
    the deprecated method from a frame whose ``__name__`` is
    ``fastapi.dependencies.utils`` — and verify the warning fires.

    Build a synthetic module named after FastAPI's solver, have it
    invoke ``ProductDependencies.get_org_id`` exactly the way FastAPI's
    ``solve_dependencies`` would (``await call(**values)``-style direct
    call), and assert the warning surfaces.
    """
    fake_mod = types.ModuleType("fastapi.dependencies.utils")
    fake_mod.__file__ = "<synthetic-fastapi-solver>"
    code = compile(
        "from noctusai_seed.dependencies import ProductDependencies\n"
        "def call_get_org_id(user):\n"
        "    return ProductDependencies.get_org_id(user)\n",
        fake_mod.__file__,
        "exec",
    )
    exec(code, fake_mod.__dict__)
    sys.modules["fastapi.dependencies.utils.__synth__"] = fake_mod

    user = _FakeUser({"org_id": "org-from-fastapi"})
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = fake_mod.call_get_org_id(user)

    assert result == "org-from-fastapi"
    auth_warns = [w for w in caught if issubclass(w.category, DeprecationWarning)
                  and "get_org_id" in str(w.message)]
    assert len(auth_warns) == 1, (
        "Synthetic FastAPI-solver call must emit exactly one warning. "
        f"Got: {[str(w.message) for w in caught]}"
    )
    msg = str(auth_warns[0].message)
    # Migration recipe must be present so the warning is actionable.
    assert "make_get_current_user_org" in msg
    assert "KB § PATTERNS/backend.md" in msg


def test_non_fastapi_module_call_silent():
    """Direct call from any non-FastAPI frame is silent — confirms the
    detector does not over-fire on arbitrary callers (e.g. seed
    routers, product services, scripts)."""
    fake_mod = types.ModuleType("some.random.module")
    fake_mod.__file__ = "<synth-non-fastapi>"
    code = compile(
        "from noctusai_seed.dependencies import ProductDependencies\n"
        "def call_get_org_id(user):\n"
        "    return ProductDependencies.get_org_id(user)\n",
        fake_mod.__file__,
        "exec",
    )
    exec(code, fake_mod.__dict__)

    user = _FakeUser({"org_id": "org-from-non-fastapi"})
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = fake_mod.call_get_org_id(user)

    assert result == "org-from-non-fastapi"
    auth_warns = [w for w in caught if issubclass(w.category, DeprecationWarning)
                  and "ProductDependencies" in str(w.message)]
    assert auth_warns == []


def test_warning_helper_has_no_effect_when_called_at_module_top_level():
    """Defensive: a top-level call (no caller frame above the helper's
    own caller) must not raise — only conditionally warn."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _warn_if_fastapi_caller("ProductDependencies.get_org_id")

    auth_warns = [w for w in caught if issubclass(w.category, DeprecationWarning)
                  and "ProductDependencies" in str(w.message)]
    assert auth_warns == [], (
        "Top-level (test-frame) call must not emit the warning."
    )
