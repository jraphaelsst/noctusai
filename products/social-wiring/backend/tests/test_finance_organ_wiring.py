"""Seed finance organ mounted on social-wiring (backend): the rendered migration equals the generator's output, the
routes are mounted, and the unauthenticated surface is strictly 401 (never 404/422)."""
from __future__ import annotations

from pathlib import Path

import pytest

from noctusai_lib.testing.organs import assert_organ_migration_current

PRODUCT_DIR = Path(__file__).resolve().parents[2]


def test_rendered_finance_migration_is_the_generators_output():
    assert_organ_migration_current(PRODUCT_DIR, "finance", schema="social_wiring")


def test_finance_routes_are_mounted():
    from app.main import app

    paths = {getattr(r, "path", "") for r in app.routes}
    for expected in ("/api/finance/accounts", "/api/finance/entries", "/api/finance/categories"):
        assert expected in paths, expected


@pytest.mark.parametrize("method,path", [("GET", "/api/finance/entries"), ("POST", "/api/finance/entries"),
                                         ("GET", "/api/finance/accounts")])
def test_finance_routes_are_strictly_401_without_auth(method, path, anon_client):
    assert anon_client.request(method, path).status_code == 401
