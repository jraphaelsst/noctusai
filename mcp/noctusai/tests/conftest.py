"""Shared fixtures for the mcp/noctusai suite.

The `domain_product` fixture is the registry-derived replacement for the
hardcoded `mailing` slug that several tests used as their "a real domain
product" anchor. `mailing` was absorbed into `social-wiring/email_marketing`
and deleted in the social-wiring-absorption Wave-4 teardown; the mcp test
matrix is a derived surface the teardown grep missed. Resolving from the live
registry instead of freezing a slug literal is the hardcoded-product-slug-set
rule applied (feedback_hardcoded_product_slug_set_keeper) and closes the
dangling-deleted-product gap (feedback_dangling_deleted_product_path) for this
surface permanently — no future product deletion can re-redden these tests.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.products import list_products


def resolve_domain_product() -> str:
    """The alphabetically-first non-seed product that has a backend and ≥1
    domain router, resolved from the live product registry."""
    for p in sorted(list_products(), key=lambda d: d["name"]):
        if p["name"] != "seed" and p.get("has_backend") and p.get("routers"):
            return p["name"]
    raise AssertionError("no domain product with backend routers in registry")


@pytest.fixture(scope="session")
def domain_product() -> str:
    return resolve_domain_product()
