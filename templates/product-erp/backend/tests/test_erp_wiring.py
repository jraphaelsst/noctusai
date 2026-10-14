"""ERP organs mounted on this host (`app/erp_organs.py`).

Pins: (a) each rendered organ migration equals its generator's output (`assert_organ_migration_current`; re-render with
`noctus.dev.render_organ_migration`, never hand-edit); (b) every organ's `requires` carry a LOWER file number; (c) the
routers are mounted; (d) they are strictly 401 without auth; (e) the scheduler registers the finance + contracts jobs.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from noctusai_lib.testing.organs import assert_organ_migration_current, find_organ_migration

PRODUCT_DIR = Path(__file__).resolve().parents[1]
SCHEMA = "{{SCHEMA_NAME}}"
ORGANS = ["finance", "parties", "items", "inventory", "purchasing", "contracts", "quotes"]


@pytest.mark.parametrize("organ", ORGANS)
def test_organ_migration_is_the_generators_output(organ):
    assert_organ_migration_current(PRODUCT_DIR, organ, schema=SCHEMA)


def test_migration_order_respects_requires():
    from noctusai_seed.organs import ORGAN_REGISTRY

    numbers = {}
    for organ in ORGANS:
        found = find_organ_migration(PRODUCT_DIR, ORGAN_REGISTRY[organ].migration_header)
        assert found, f"{organ}: no rendered migration"
        numbers[organ] = int(re.match(r"(\d+)_", found[0].name).group(1))
    for organ in ORGANS:
        for dep in ORGAN_REGISTRY[organ].requires:
            assert numbers[dep] < numbers[organ], f"{organ} ({numbers[organ]}) must come after {dep} ({numbers[dep]})"


@pytest.mark.parametrize(
    "path",
    ["/api/finance/entries", "/api/parties", "/api/items", "/api/inventory/balances",
     "/api/purchasing/orders", "/api/contracts", "/api/quotes"],
)
def test_routes_are_mounted_and_strictly_401_without_auth(client, path):
    from app.main import app

    # The OpenAPI paths, not `app.routes`: FastAPI >= 0.143 keeps an included router as one `_IncludedRouter`
    # entry with no `.path`, so walking `app.routes` misses every organ route.
    mounted = set(app.openapi()["paths"])
    assert any(m == path or m.startswith(path + "/") or m == path.rstrip("/") for m in mounted), path
    assert client.raw().get(path).status_code == 401


def test_scheduler_registers_finance_and_contracts_jobs():
    from app import erp_scheduler

    names = erp_scheduler.configure()
    assert erp_scheduler.RECURRENCES_JOB in names
    assert "contracts_generate_billing" in names
