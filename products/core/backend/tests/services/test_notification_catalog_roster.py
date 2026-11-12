"""The Notificações page covers EVERY live product — one that declares no kinds yet still shows up (as empty),
instead of vanishing and making the owner think nothing is wired."""
from __future__ import annotations

from datetime import datetime, timezone

from app.services import notification_catalog_service as svc
from noctusai_lib.testing import MockSupabaseClient

NOW = datetime(2026, 11, 12, 12, 0, tzinfo=timezone.utc)


def _kind(product: str, kind: str) -> dict:
    return {"product": product, "kind": kind, "titulo": kind, "descricao": "d", "gatilho": "g", "canais": ["whatsapp"],
            "enabled": True, "toggled_at": None, "registered_at": None, "last_seen_at": None}


def _db(products: list[dict], kinds: list[dict]) -> MockSupabaseClient:
    db = MockSupabaseClient()
    db.set_table_data("products", products)
    db.set_table_data("notification_kinds", kinds)
    db.set_table_data("notification_sends", [])
    return db


def test_live_product_without_kinds_is_listed_empty():
    db = _db(
        [{"slug": "agents", "ativo": True, "deploy_scope": "live"}, {"slug": "monica", "ativo": True, "deploy_scope": "live"}],
        [_kind("agents", "eval_loop_parada")],
    )
    out = {p["product"]: p for p in svc.list_catalog(db, NOW)["products"]}
    assert set(out) == {"agents", "monica", "core"}  # core is the platform shell: always on the roster
    assert out["monica"]["kinds"] == [] and out["monica"]["total"] == 0 and out["monica"]["declared"] is False
    assert out["agents"]["declared"] is True and out["agents"]["total"] == 1


def test_asleep_or_dev_products_are_not_added_to_the_roster():
    db = _db(
        [{"slug": "igig", "ativo": False, "deploy_scope": "dev"}, {"slug": "erp", "ativo": True, "deploy_scope": "dev"}],
        [],
    )
    assert [p["product"] for p in svc.list_catalog(db, NOW)["products"]] == ["core"]


def test_a_product_with_kinds_stays_listed_even_when_no_longer_live():
    db = _db([{"slug": "igig", "ativo": False, "deploy_scope": "dev"}], [_kind("igig", "x")])
    assert "igig" in [p["product"] for p in svc.list_catalog(db, NOW)["products"]]
