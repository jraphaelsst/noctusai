"""
Router tests for the AdConnect cart (Phase 3 — Supabase-backed).

Covers:
  • GET    /cart                — get-or-create active cart
  • POST   /cart/items          — add line (or upsert qty)
  • PATCH  /cart/items/{id}     — update line qty
  • DELETE /cart/items/{id}     — remove line
  • POST   /cart/checkout       — convert active cart to pedido

Conftest provides the `client` fixture wired to `MockSupabaseClient(schema="adconnect")`.
The `distributor_client` / `admin_client` fixtures here re-bind the mock's
auth.get_user with a user_metadata dict carrying `distributor_id` (the
default conftest user has org_id but no distributor_id).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
import pytest

from app.config import settings

# `_bind_user_metadata` was lifted into the AdConnect conftest as
# `bind_adconnect_user` (Phase 1 of `adconnect-test-conftest-distributor-binding`).
# `ORG_ID` / `DIST_A_ID` constants likewise live in the conftest now —
# imported here for backwards compat with the inline test bodies that
# already reference them.
from tests.conftest import (
    ORG_ID_BRAND as ORG_ID,
    DIST_A_ID,
    bind_adconnect_user,
)


def _make_token(payload: dict[str, Any]) -> str:
    body = dict(payload)
    body["exp"] = datetime.now(timezone.utc) + timedelta(minutes=30)
    return jwt.encode(body, settings.jwt_secret, algorithm="HS256")


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


def _admin_headers() -> dict[str, str]:
    tok = _make_token(
        {"sub": "user-admin", "email": "admin@a.com", "role": "admin", "org_id": ORG_ID}
    )
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture
def distributor_client(client):
    """client + auto-bound distributor user_metadata."""
    bind_adconnect_user(client, role="customer", distributor_id=DIST_A_ID)
    return client


@pytest.fixture
def admin_client(client):
    """client + auto-bound admin user_metadata (no distributor)."""
    bind_adconnect_user(client, role="admin", distributor_id=None)
    return client


def _seed_catalog(mock_sb):
    """Seed a single catalog product for cart-add tests."""
    mock_sb.set_table_data(
        "products",
        [
            {
                "id": "p-1",
                "org_id": ORG_ID,
                "sku": "SKU-A",
                "nome": "Cabo Cat6",
                "categoria_id": "cat-1",
                "base_price": 100,
                "in_stock": True,
                "ativo": True,
            },
        ],
    )
    mock_sb.set_table_data("precos_distribuidor", [])


def _seed_active_cart(mock_sb, *, cart_id: str = "cart-1", distributor_id: str = DIST_A_ID):
    mock_sb.set_table_data(
        "carts",
        [
            {
                "id": cart_id,
                "distributor_id": distributor_id,
                "created_by": f"user-{distributor_id}",
                "status": "ativo",
                "total": 0,
                "created_at": "2026-05-10T00:00:00Z",
            },
        ],
    )


def _seed_cart_items(mock_sb, items: list[dict]):
    mock_sb.set_table_data("itens_carrinho", items)


# ---------------------------------------------------------------------------
# GET /cart
# ---------------------------------------------------------------------------


class TestGetCart:
    def test_get_creates_cart_when_absent(self, distributor_client):
        _seed_catalog(distributor_client.mock_supabase)
        distributor_client.mock_supabase.set_table_data("carts", [])
        distributor_client.mock_supabase.set_table_data("itens_carrinho", [])
        r = distributor_client.raw().get("/cart", headers=_distributor_headers())
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "ativo"
        assert body["items"] == []

    def test_get_returns_existing_cart_with_items(self, distributor_client):
        _seed_catalog(distributor_client.mock_supabase)
        _seed_active_cart(distributor_client.mock_supabase)
        _seed_cart_items(
            distributor_client.mock_supabase,
            [
                {
                    "id": "ic-1",
                    "cart_id": "cart-1",
                    "product_id": "p-1",
                    "quantidade": 2,
                    "price_at_add": 100.0,
                },
            ],
        )
        r = distributor_client.raw().get("/cart", headers=_distributor_headers())
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["id"] == "cart-1"
        assert len(body["items"]) == 1
        assert body["items"][0]["quantidade"] == 2
        assert body["items"][0]["line_total"] == 200.0
        assert body["total"] == 200.0

    def test_get_unauth_rejected(self, client):
        r = client.raw().get("/cart")
        assert r.status_code == 401

    def test_get_admin_without_distributor_rejected(self, admin_client):
        r = admin_client.raw().get("/cart", headers=_admin_headers())
        # Admin has no distributorId → 401 (no cart of their own).
        assert r.status_code == 401


# ---------------------------------------------------------------------------
# POST /cart/items
# ---------------------------------------------------------------------------


class TestAddCartItem:
    def test_add_line_on_empty_cart(self, distributor_client):
        _seed_catalog(distributor_client.mock_supabase)
        distributor_client.mock_supabase.set_table_data("carts", [])
        distributor_client.mock_supabase.set_table_data("itens_carrinho", [])
        r = distributor_client.raw().post(
            "/cart/items",
            json={"product_id": "p-1", "quantidade": 3},
            headers=_distributor_headers(),
        )
        assert r.status_code == 201, r.text
        inserts = distributor_client.mock_supabase.table(
            "itens_carrinho"
        ).inserted_payloads
        assert len(inserts) >= 1
        assert inserts[-1]["product_id"] == "p-1"
        assert inserts[-1]["quantidade"] == 3
        assert float(inserts[-1]["price_at_add"]) == 100.0

    def test_add_unknown_product_returns_400(self, distributor_client):
        _seed_catalog(distributor_client.mock_supabase)
        distributor_client.mock_supabase.set_table_data("carts", [])
        # Wipe products so the catalog returns no rows for our request.
        distributor_client.mock_supabase.set_table_data("products", [])
        r = distributor_client.raw().post(
            "/cart/items",
            json={"product_id": "p-99", "quantidade": 1},
            headers=_distributor_headers(),
        )
        assert r.status_code == 400

    def test_add_zero_quantity_rejected_by_pydantic(self, distributor_client):
        r = distributor_client.raw().post(
            "/cart/items",
            json={"product_id": "p-1", "quantidade": 0},
            headers=_distributor_headers(),
        )
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# PATCH /cart/items/{id}
# ---------------------------------------------------------------------------


class TestUpdateCartItem:
    def test_update_line_quantity(self, distributor_client):
        _seed_catalog(distributor_client.mock_supabase)
        _seed_active_cart(distributor_client.mock_supabase)
        _seed_cart_items(
            distributor_client.mock_supabase,
            [
                {
                    "id": "ic-1",
                    "cart_id": "cart-1",
                    "product_id": "p-1",
                    "quantidade": 1,
                    "price_at_add": 100.0,
                },
            ],
        )
        r = distributor_client.raw().patch(
            "/cart/items/ic-1",
            json={"quantidade": 5},
            headers=_distributor_headers(),
        )
        assert r.status_code == 200, r.text
        updates = distributor_client.mock_supabase.table(
            "itens_carrinho"
        ).updated_payloads
        assert any(u.get("quantidade") == 5 for u in updates)

    def test_update_unknown_line_returns_404(self, distributor_client):
        _seed_catalog(distributor_client.mock_supabase)
        _seed_active_cart(distributor_client.mock_supabase)
        _seed_cart_items(distributor_client.mock_supabase, [])
        r = distributor_client.raw().patch(
            "/cart/items/nonexistent",
            json={"quantidade": 2},
            headers=_distributor_headers(),
        )
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /cart/items/{id}
# ---------------------------------------------------------------------------


class TestRemoveCartItem:
    def test_remove_line(self, distributor_client):
        _seed_catalog(distributor_client.mock_supabase)
        _seed_active_cart(distributor_client.mock_supabase)
        _seed_cart_items(
            distributor_client.mock_supabase,
            [
                {
                    "id": "ic-1",
                    "cart_id": "cart-1",
                    "product_id": "p-1",
                    "quantidade": 1,
                    "price_at_add": 100.0,
                },
            ],
        )
        r = distributor_client.raw().delete(
            "/cart/items/ic-1", headers=_distributor_headers()
        )
        assert r.status_code == 200, r.text

    def test_remove_unknown_line_returns_404(self, distributor_client):
        _seed_catalog(distributor_client.mock_supabase)
        _seed_active_cart(distributor_client.mock_supabase)
        _seed_cart_items(distributor_client.mock_supabase, [])
        r = distributor_client.raw().delete(
            "/cart/items/nonexistent", headers=_distributor_headers()
        )
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# POST /cart/checkout
# ---------------------------------------------------------------------------


class TestCheckout:
    def test_checkout_with_empty_cart_returns_400(self, distributor_client):
        _seed_catalog(distributor_client.mock_supabase)
        _seed_active_cart(distributor_client.mock_supabase)
        _seed_cart_items(distributor_client.mock_supabase, [])
        r = distributor_client.raw().post(
            "/cart/checkout",
            json={"observacoes": "test"},
            headers=_distributor_headers(),
        )
        assert r.status_code == 400

    def test_checkout_creates_pedido_and_items(self, distributor_client):
        _seed_catalog(distributor_client.mock_supabase)
        _seed_active_cart(distributor_client.mock_supabase)
        _seed_cart_items(
            distributor_client.mock_supabase,
            [
                {
                    "id": "ic-1",
                    "cart_id": "cart-1",
                    "product_id": "p-1",
                    "quantidade": 2,
                    "price_at_add": 100.0,
                },
            ],
        )
        # Empty rules so accrue_for_pedido finds nothing (and doesn't error).
        distributor_client.mock_supabase.set_table_data(
            "regras_recompensa", []
        )
        r = distributor_client.raw().post(
            "/cart/checkout",
            json={"observacoes": "Entregar de manhã"},
            headers=_distributor_headers(),
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["status"] == "enviado"
        assert body["total"] == 200.0
        # Verify pedido + itens_pedido inserts.
        pedido_inserts = distributor_client.mock_supabase.table(
            "pedidos"
        ).inserted_payloads
        assert len(pedido_inserts) == 1
        assert pedido_inserts[0]["distributor_id"] == DIST_A_ID
        assert pedido_inserts[0]["cart_id"] == "cart-1"
        item_inserts = distributor_client.mock_supabase.table(
            "itens_pedido"
        ).inserted_payloads
        assert len(item_inserts) == 1
        assert item_inserts[0]["product_id"] == "p-1"
        assert item_inserts[0]["quantidade"] == 2
        assert float(item_inserts[0]["price_at_order"]) == 100.0
        # Cart status flipped to convertido.
        cart_updates = distributor_client.mock_supabase.table(
            "carts"
        ).updated_payloads
        assert any(u.get("status") == "convertido" for u in cart_updates)

    def test_checkout_unauth_rejected(self, client):
        r = client.raw().post("/cart/checkout", json={})
        assert r.status_code == 401
