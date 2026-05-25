"""Tests for `build_standard_routers()` — the opt-in dispatcher introduced
by the `core-seed-wiring` project Phase 1.

Scope: registry contents, selection behavior, order preservation, error
handling on unknown names. The individual router factories
(`_create_health_router`, `_create_notificacoes_router`,
`_create_team_router`, `_build_llm_router`) are exercised by product
integration tests; we don't re-test their internals here.
"""
from __future__ import annotations

import pytest
from fastapi import APIRouter

from noctusai_seed.routers import (
    _STANDARD_ROUTERS,
    build_standard_routers,
)


_ALL_NAMES = ["health", "notificacoes", "team", "llm", "ai_outputs", "ai_feedback", "scheduler", "whatsapp_admin"]


def _paths(routers) -> set[str]:
    """Collect every registered route.path across the returned list."""
    return {route.path for r in routers for route in r.routes}


class TestBuildStandardRoutersSelection:
    def test_empty_names_returns_empty_list(self, fake_deps, fake_settings, product_name, version):
        result = build_standard_routers(
            fake_deps, fake_settings, product_name=product_name, version=version, names=[]
        )
        assert result == []

    def test_single_name_health(self, fake_deps, fake_settings, product_name, version):
        result = build_standard_routers(
            fake_deps, fake_settings, product_name=product_name, version=version, names=["health"]
        )
        assert len(result) == 1
        assert isinstance(result[0], APIRouter)
        assert "/api/health" in _paths(result)

    def test_single_name_notificacoes(self, fake_deps, fake_settings, product_name, version):
        result = build_standard_routers(
            fake_deps, fake_settings, product_name=product_name, version=version, names=["notificacoes"]
        )
        assert len(result) == 1
        assert isinstance(result[0], APIRouter)
        assert "/api/notificacoes" in _paths(result)

    def test_single_name_team(self, fake_deps, fake_settings, product_name, version):
        result = build_standard_routers(
            fake_deps, fake_settings, product_name=product_name, version=version, names=["team"]
        )
        assert len(result) == 1
        assert isinstance(result[0], APIRouter)
        assert "/api/team" in _paths(result)

    def test_single_name_llm(self, fake_deps, fake_settings, product_name, version):
        result = build_standard_routers(
            fake_deps, fake_settings, product_name=product_name, version=version, names=["llm"]
        )
        assert len(result) == 1
        assert isinstance(result[0], APIRouter)
        llm_paths = _paths(result)
        assert "/api/llm/providers" in llm_paths
        assert "/api/llm/models" in llm_paths
        assert "/api/llm/preferences" in llm_paths

    def test_all_names_returns_all_routers(self, fake_deps, fake_settings, product_name, version):
        result = build_standard_routers(
            fake_deps, fake_settings, product_name=product_name, version=version, names=_ALL_NAMES
        )
        assert len(result) == len(_ALL_NAMES)
        assert all(isinstance(r, APIRouter) for r in result)
        paths = _paths(result)
        assert "/api/health" in paths
        assert "/api/notificacoes" in paths
        assert "/api/team" in paths
        assert "/api/llm/providers" in paths
        assert "/api/ai/outputs" in paths

    def test_single_name_ai_outputs(self, fake_deps, fake_settings, product_name, version):
        result = build_standard_routers(
            fake_deps, fake_settings, product_name=product_name, version=version,
            names=["ai_outputs"],
        )
        assert len(result) == 1
        assert "/api/ai/outputs" in _paths(result)


class TestBuildStandardRoutersOrder:
    def test_order_preserved(self, fake_deps, fake_settings, product_name, version):
        """Passing names in a non-canonical order returns routers in that order.

        FastAPI's `include_router` is order-sensitive for overlapping routes
        (first match wins). Products that care enforce order via their opt-in
        list, so the builder must not re-sort."""
        a = build_standard_routers(
            fake_deps, fake_settings, product_name=product_name, version=version,
            names=["llm", "health"],
        )
        b = build_standard_routers(
            fake_deps, fake_settings, product_name=product_name, version=version,
            names=["health", "llm"],
        )
        # Path sets are identical; order is inverted.
        paths_a_first = next(iter(_paths([a[0]])))
        paths_b_first = next(iter(_paths([b[0]])))
        assert "llm" in paths_a_first or "health" == paths_a_first[-6:]  # first-of-list order
        # Stronger assertion: compare path-sets per index.
        assert _paths([a[0]]) != _paths([b[0]])


class TestBuildStandardRoutersValidation:
    def test_unknown_name_raises_valueerror(self, fake_deps, fake_settings, product_name, version):
        with pytest.raises(ValueError) as exc:
            build_standard_routers(
                fake_deps, fake_settings, product_name=product_name, version=version,
                names=["health", "bogus"],
            )
        msg = str(exc.value)
        assert "bogus" in msg
        # Must include the valid-name list so the caller can fix immediately.
        for name in _ALL_NAMES:
            assert name in msg

    def test_multiple_unknown_names_all_reported(self, fake_deps, fake_settings, product_name, version):
        with pytest.raises(ValueError) as exc:
            build_standard_routers(
                fake_deps, fake_settings, product_name=product_name, version=version,
                names=["nope", "also-nope"],
            )
        msg = str(exc.value)
        assert "nope" in msg
        assert "also-nope" in msg

    def test_registry_keys_match_documented_set(self):
        """Guard against accidental registry drift. If a new standard router
        is added or removed, this test must be updated deliberately."""
        assert set(_STANDARD_ROUTERS) == set(_ALL_NAMES)
