"""
Tests for the AdConnect Products Router (Phase 2 — Supabase-backed).

Covers:
  • GET /products             — list with filter / search / sort / inStock.
  • GET /products/categories  — list with per-category counts.
  • GET /products/{id}        — single fetch with preferential pricing.

The conftest provides a `client` fixture wired to `MockSupabaseClient`.
This file augments it with role-specific clients (brand admin vs distributor
user) since AdConnect's routers consume their own JWT (not the seed Supabase
auth flow).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
import pytest
from fastapi.testclient import TestClient

from app.config import settings


ORG_ID = "00000000-0000-0000-0000-000000000001"
DIST_A_ID = "11111111-1111-1111-1111-111111111111"
DIST_B_ID = "22222222-2222-2222-2222-222222222222"


def _make_token(payload: dict[str, Any]) -> str:
    body = dict(payload)
    body["exp"] = datetime.now(timezone.utc) + timedelta(minutes=30)
    return jwt.encode(body, settings.jwt_secret, algorithm="HS256")


def _admin_headers() -> dict[str, str]:
    tok = _make_token({"sub": "user-admin", "email": "admin@a.com", "role": "admin", "org_id": ORG_ID})
    return {"Authorization": f"Bearer {tok}"}


def _distributor_headers(distributor_id: str = DIST_A_ID) -> dict[str, str]:
    tok = _make_token(
        {
            "sub": f"user-{distributor_id}",
            "email": "u@dist.com",
            "role": "customer",
            "distributorId": distributor_id,
            "org_id": ORG_ID,
        }
    )
    return {"Authorization": f"Bearer {tok}"}


def _seed_catalog(mock_sb, *, products: list[dict] | None = None, categorias: list[dict] | None = None, precos: list[dict] | None = None):
    """Seed the mock Supabase tables used by the products service."""
    products = products if products is not None else _default_products()
    categorias = categorias if categorias is not None else _default_categorias()
    precos = precos if precos is not None else []
    mock_sb.set_table_data("products", products)
    mock_sb.set_table_data("categorias", categorias)
    mock_sb.set_table_data("precos_distribuidor", precos)


def _default_products() -> list[dict]:
    return [
        {
            "id": "p-1",
            "org_id": ORG_ID,
            "sku": "SKU-A",
            "nome": "Cabo Cat6",
            "categoria_id": "cat-id-cat6",
            "base_price": 100,
            "in_stock": True,
            "ativo": True,
        },
        {
            "id": "p-2",
            "org_id": ORG_ID,
            "sku": "SKU-B",
            "nome": "Patch Panel 24",
            "categoria_id": "cat-id-pp",
            "base_price": 200,
            "in_stock": False,
            "ativo": True,
        },
        {
            "id": "p-3",
            "org_id": ORG_ID,
            "sku": "SKU-C",
            "nome": "Fibra LC",
            "categoria_id": "cat-id-fibra",
            "base_price": 50,
            "in_stock": True,
            "ativo": True,
        },
    ]


def _default_categorias() -> list[dict]:
    return [
        {"id": "cat-id-cat6", "org_id": ORG_ID, "nome": "Cat.6", "ordem": 0, "ativa": True},
        {"id": "cat-id-pp", "org_id": ORG_ID, "nome": "Patch Panel", "ordem": 1, "ativa": True},
        {"id": "cat-id-fibra", "org_id": ORG_ID, "nome": "Fibra", "ordem": 2, "ativa": True},
    ]


# ---------------------------------------------------------------------------
# GET /products
# ---------------------------------------------------------------------------


class TestListProducts:
    def test_list_returns_products(self, client):
        _seed_catalog(client.mock_supabase)
        r = client.raw().get("/products", headers=_admin_headers())
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert isinstance(data, list)
        assert len(data) == 3
        assert {p["sku"] for p in data} == {"SKU-A", "SKU-B", "SKU-C"}

    def test_list_filters_in_stock_only(self, client):
        _seed_catalog(client.mock_supabase)
        r = client.raw().get("/products/?inStockOnly=true", headers=_admin_headers())
        assert r.status_code == 200
        skus = {p["sku"] for p in r.json()["data"]}
        assert skus == {"SKU-A", "SKU-C"}  # SKU-B is out of stock

    def test_list_search_matches_name(self, client):
        _seed_catalog(client.mock_supabase)
        r = client.raw().get("/products/?q=patch", headers=_admin_headers())
        assert r.status_code == 200
        skus = [p["sku"] for p in r.json()["data"]]
        assert skus == ["SKU-B"]

    def test_list_search_matches_sku(self, client):
        _seed_catalog(client.mock_supabase)
        r = client.raw().get("/products/?q=SKU-A", headers=_admin_headers())
        assert r.status_code == 200
        skus = [p["sku"] for p in r.json()["data"]]
        assert skus == ["SKU-A"]

    def test_list_sort_by_price_ascending(self, client):
        _seed_catalog(client.mock_supabase)
        r = client.raw().get("/products/?sort=price", headers=_admin_headers())
        assert r.status_code == 200
        skus = [p["sku"] for p in r.json()["data"]]
        # base_prices: 50, 100, 200 → SKU-C, SKU-A, SKU-B
        assert skus == ["SKU-C", "SKU-A", "SKU-B"]

    def test_list_sort_cashback_is_rejected(self, client):
        # `cashback` sort was on the mock router; canonical schema moves
        # cashback to regras_recompensa (Phase 4). The router's pattern
        # validation should 422 the obsolete value.
        _seed_catalog(client.mock_supabase)
        r = client.raw().get("/products/?sort=cashback", headers=_admin_headers())
        assert r.status_code == 422

    def test_list_default_sort_is_name_alphabetical(self, client):
        _seed_catalog(client.mock_supabase)
        r = client.raw().get("/products", headers=_admin_headers())
        assert r.status_code == 200
        names = [p["nome"] for p in r.json()["data"]]
        assert names == sorted(names, key=str.lower)

    def test_list_unauthenticated_rejected(self, client):
        r = client.raw().get("/products")
        assert r.status_code == 401


# ---------------------------------------------------------------------------
# Preferential pricing
# ---------------------------------------------------------------------------


class TestPreferentialPricing:
    def test_brand_admin_sees_base_price(self, client):
        _seed_catalog(
            client.mock_supabase,
            precos=[
                {"product_id": "p-1", "preferential_price": 70, "distributor_id": DIST_A_ID},
            ],
        )
        r = client.raw().get("/products", headers=_admin_headers())
        assert r.status_code == 200
        by_sku = {p["sku"]: p for p in r.json()["data"]}
        # Admin always sees base_price as effective_price.
        assert float(by_sku["SKU-A"]["effective_price"]) == 100.0

    def test_distributor_user_sees_preferential_price(self, client):
        _seed_catalog(
            client.mock_supabase,
            precos=[
                {"product_id": "p-1", "preferential_price": 70, "distributor_id": DIST_A_ID},
            ],
        )
        r = client.raw().get("/products", headers=_distributor_headers(DIST_A_ID))
        assert r.status_code == 200
        by_sku = {p["sku"]: p for p in r.json()["data"]}
        # Distributor A has a preferential row → 70 instead of 100.
        assert float(by_sku["SKU-A"]["effective_price"]) == 70.0
        # Products without a preferential row fall back to base_price.
        assert float(by_sku["SKU-B"]["effective_price"]) == 200.0

    def test_distributor_without_preferential_row_falls_back_to_base(self, client):
        _seed_catalog(client.mock_supabase, precos=[])
        r = client.raw().get("/products", headers=_distributor_headers(DIST_A_ID))
        assert r.status_code == 200
        by_sku = {p["sku"]: p for p in r.json()["data"]}
        assert float(by_sku["SKU-A"]["effective_price"]) == 100.0


# ---------------------------------------------------------------------------
# GET /products/categories
# ---------------------------------------------------------------------------


class TestCategories:
    def test_categories_includes_product_counts(self, client):
        _seed_catalog(client.mock_supabase)
        r = client.raw().get("/products/categories", headers=_admin_headers())
        assert r.status_code == 200
        data = r.json()["data"]
        # Canonical schema keys categorias by `nome` (no `slug` column —
        # Phase 0 audit divergence from mock JSON shape).
        by_nome = {c["nome"]: c for c in data}
        assert by_nome["Cat.6"]["count"] == 1
        assert by_nome["Patch Panel"]["count"] == 1
        assert by_nome["Fibra"]["count"] == 1


# ---------------------------------------------------------------------------
# GET /products/{id}
# ---------------------------------------------------------------------------


class TestGetProduct:
    def test_get_product_returns_row(self, client):
        # Mock builders don't filter on .eq() — seed just the target row so
        # the router's "first match" semantics line up with what we want.
        _seed_catalog(
            client.mock_supabase,
            products=[{
                "id": "p-1", "org_id": ORG_ID, "sku": "SKU-A", "nome": "Cabo Cat6",
                "categoria_id": "cat-id-cat6", "base_price": 100, "in_stock": True,
                "ativo": True,
            }],
        )
        r = client.raw().get("/products/p-1", headers=_admin_headers())
        assert r.status_code == 200
        assert r.json()["sku"] == "SKU-A"

    def test_get_product_distributor_sees_preferential_price(self, client):
        _seed_catalog(
            client.mock_supabase,
            products=[{
                "id": "p-1", "org_id": ORG_ID, "sku": "SKU-A", "nome": "Cabo Cat6",
                "categoria_id": "cat-id-cat6", "base_price": 100, "in_stock": True,
                "ativo": True,
            }],
            precos=[
                {"product_id": "p-1", "preferential_price": 70, "distributor_id": DIST_A_ID},
            ],
        )
        r = client.raw().get("/products/p-1", headers=_distributor_headers(DIST_A_ID))
        assert r.status_code == 200
        assert float(r.json()["effective_price"]) == 70.0

    def test_get_product_admin_sees_base_price(self, client):
        _seed_catalog(
            client.mock_supabase,
            products=[{
                "id": "p-1", "org_id": ORG_ID, "sku": "SKU-A", "nome": "Cabo Cat6",
                "categoria_id": "cat-id-cat6", "base_price": 100, "in_stock": True,
                "ativo": True,
            }],
            precos=[
                {"product_id": "p-1", "preferential_price": 70, "distributor_id": DIST_A_ID},
            ],
        )
        r = client.raw().get("/products/p-1", headers=_admin_headers())
        assert r.status_code == 200
        assert float(r.json()["effective_price"]) == 100.0

    def test_get_product_not_found(self, client):
        _seed_catalog(client.mock_supabase, products=[])
        r = client.raw().get("/products/nonexistent", headers=_admin_headers())
        assert r.status_code == 404
