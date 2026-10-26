"""Finance organ mounted on this host (`mount_finance` in `app/main.py`).

Pins: (a) the rendered finance migration equals the generator's output
(`assert_organ_migration_current`; re-render with `noctus.dev.render_organ_migration`, never hand-edit);
(b) the finance routes are mounted; (c) they are strictly 401 without auth.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from noctusai_lib.testing.organs import assert_organ_migration_current

PRODUCT_DIR = Path(__file__).resolve().parents[1]
SCHEMA = "monica"


def test_finance_migration_is_the_generators_output():
    assert_organ_migration_current(PRODUCT_DIR, "finance", schema=SCHEMA)


def test_finance_routes_are_mounted(client):
    from app.main import app

    paths = {getattr(r, "path", "") for r in app.routes}
    assert "/api/finance/entries" in paths
    assert "/api/finance/accounts" in paths


@pytest.mark.parametrize(
    "method,path",
    [("GET", "/api/finance/entries"), ("POST", "/api/finance/entries"), ("GET", "/api/finance/accounts")],
)
def test_finance_routes_are_strictly_401_without_auth(client, method, path):
    assert client.raw().request(method, path).status_code == 401
