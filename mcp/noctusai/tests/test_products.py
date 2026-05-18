"""Tests for product introspection tools.

The `domain_product` fixture (tests/conftest.py) is the registry-derived
replacement for the hardcoded `mailing` slug these tests used as their domain
anchor — `mailing` was absorbed into `social-wiring/email_marketing` and
deleted in social-wiring-absorption Wave-4. See conftest for rationale.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.products import list_products, get_product_summary, get_product_structure


class TestListProducts:
    def test_returns_all_products(self, domain_product):
        products = list_products()
        slugs = [p["name"] for p in products]
        assert "seed" in slugs
        assert "erp-imobiliario" in slugs
        # Registry-derived rather than a frozen slug literal — survives
        # product deletion (a `"mailing" in slugs` assertion lived here
        # until Wave-4 teardown made it permanently red).
        assert domain_product in slugs
        assert len(products) >= 6

    def test_each_product_has_structure(self):
        for product in list_products():
            assert "routers" in product
            assert "services" in product
            assert "pages" in product
            assert "hooks" in product
            assert "has_backend" in product
            assert "has_frontend" in product


class TestGetProductSummary:
    def test_seed_has_only_demo_routers(self):
        """Seed ships exactly two demo routers — `example_router` (route
        conventions reference) and `webhook_router` (webhook 5-pin compliance
        reference, added in commit 22750fd `feat(seed): inherit start.sh +
        stop.sh + day-one routes + webhook 5-pin compliance`). NO domain
        routers — products inherit shared routers from the framework, never
        copy from seed.
        """
        summary = get_product_summary("seed")
        DEMO_ROUTERS = {"example_router", "webhook_router"}
        actual = set(summary["routers"])
        assert actual == DEMO_ROUTERS, (
            f"seed routers should be exactly {DEMO_ROUTERS} (demos only); "
            f"got {actual}"
        )
        assert summary["has_backend"] is True
        assert summary["has_readme"] is True

    def test_domain_product_has_routers(self, domain_product):
        """A domain product exposes ≥1 backend router. Probe is registry-derived
        (was a hardcoded `mailing` 3-router assertion pre-Wave-4)."""
        summary = get_product_summary(domain_product)
        assert summary["has_backend"] is True
        assert isinstance(summary["routers"], list)
        assert len(summary["routers"]) >= 1

    def test_nonexistent_product(self):
        summary = get_product_summary("nonexistent")
        assert "error" in summary


class TestGetProductStructure:
    def test_includes_endpoints(self, domain_product):
        structure = get_product_structure(domain_product)
        assert "router_endpoints" in structure
        assert len(structure["router_endpoints"]) >= 1

    def test_includes_tests(self, domain_product):
        structure = get_product_structure(domain_product)
        assert "test_files" in structure
        assert len(structure["test_files"]) > 0

    def test_includes_migrations(self, domain_product):
        structure = get_product_structure(domain_product)
        assert "migrations" in structure
        # Every product's schema is built by a single `001_<slug>.sql`
        # (feedback_single_001_migration) — assert that shape generically
        # rather than freezing the prior `001_mailing.sql` literal.
        assert any(m.startswith("001_") and m.endswith(".sql")
                   for m in structure["migrations"])
