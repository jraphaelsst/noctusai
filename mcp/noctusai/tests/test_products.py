"""Tests for product introspection tools."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.products import list_products, get_product_summary, get_product_structure


class TestListProducts:
    def test_returns_all_products(self):
        products = list_products()
        slugs = [p["name"] for p in products]
        assert "seed" in slugs
        assert "mailing" in slugs
        assert "erp-imobiliario" in slugs
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
    def test_seed_has_zero_routers(self):
        summary = get_product_summary("seed")
        assert summary["routers"] == []
        assert summary["has_backend"] is True
        assert summary["has_readme"] is True

    def test_mailing_has_domain_routers(self):
        summary = get_product_summary("mailing")
        assert "contacts" in summary["routers"]
        assert "campaigns" in summary["routers"]
        assert "automations" in summary["routers"]

    def test_nonexistent_product(self):
        summary = get_product_summary("nonexistent")
        assert "error" in summary


class TestGetProductStructure:
    def test_includes_endpoints(self):
        structure = get_product_structure("mailing")
        assert "router_endpoints" in structure
        assert "contacts" in structure["router_endpoints"]

    def test_includes_tests(self):
        structure = get_product_structure("mailing")
        assert "test_files" in structure
        assert len(structure["test_files"]) > 0

    def test_includes_migrations(self):
        structure = get_product_structure("mailing")
        assert "migrations" in structure
        assert "001_mailing.sql" in structure["migrations"]
