"""Org scoping, auth boundary (strict 401), validation and the RPC refusal -> HTTP mapping."""
from __future__ import annotations

import pytest

from noctusai_lib.domain.inventory import reports, stock, warehouses
from noctusai_lib.domain.inventory._common import Scope
from noctusai_lib.domain.inventory.errors import InventoryError, from_refusal
from noctusai_lib.primitives.exceptions import NotFoundError

from .conftest import CFG, ITEM, ITEM2, ORG_A, ORG_B, WH1, WH2

# (method, path, json) for EVERY route; the auth tests iterate this so a new route without a test fails the count test.
READS = [
    ("GET", "/api/inventory/warehouses", None),
    ("GET", "/api/inventory/balances", None),
    ("GET", f"/api/inventory/kardex?item_id={ITEM}", None),
    ("GET", "/api/inventory/valuation", None),
    ("GET", "/api/inventory/low-stock", None),
]
WRITES = [
    ("POST", "/api/inventory/warehouses", {"name": "Matriz", "code": "MTZ"}),
    ("PATCH", f"/api/inventory/warehouses/{WH1}", {"name": "x"}),
    ("PUT", "/api/inventory/settings", {"item_id": ITEM, "warehouse_id": WH1, "min_qty": "2"}),
    ("POST", "/api/inventory/receive", {"item_id": ITEM, "warehouse_id": WH1, "qty": "1", "unit_cost_cents": 100}),
    ("POST", "/api/inventory/issue", {"item_id": ITEM, "warehouse_id": WH1, "qty": "1"}),
    ("POST", "/api/inventory/adjust", {"item_id": ITEM, "warehouse_id": WH1, "counted_qty": "1"}),
    ("POST", "/api/inventory/transfer", {"item_id": ITEM, "from_warehouse_id": WH1, "to_warehouse_id": WH2, "qty": "1"}),
]


def _send(h, method, path, body, headers):
    return h.client.request(method, path, json=body, headers=headers)


def test_every_route_is_covered(h):
    routes = {(m, r.path) for r in h.app.routes if hasattr(r, "methods") for m in r.methods if r.path.startswith("/api/inventory")}
    assert len(routes) == len(READS) + len(WRITES)


@pytest.mark.parametrize("method,path,body", READS + WRITES)
def test_unauthenticated_is_strictly_401(h, method, path, body):
    assert _send(h, method, path, body, {}).status_code == 401


@pytest.mark.parametrize("method,path,body", WRITES)
def test_staff_cannot_write_403(h, method, path, body):
    assert _send(h, method, path, body, h.staff()).status_code == 403


@pytest.mark.parametrize("method,path,body", READS)
def test_staff_can_read(h, method, path, body):
    assert _send(h, method, path, body, h.staff()).status_code == 200


def test_warehouse_crud_first_becomes_default_and_codes_are_unique(h):
    r = h.client.post("/api/inventory/warehouses", json={"name": "Matriz", "code": "MTZ", "address": {"city": "SP"}}, headers=h.admin)
    assert r.status_code == 201 and r.json()["data"]["is_default"] is True
    second = h.client.post("/api/inventory/warehouses", json={"name": "Filial", "code": "FIL"}, headers=h.admin).json()["data"]
    assert second["is_default"] is False
    rows = h.client.get("/api/inventory/warehouses", headers=h.staff()).json()["data"]
    assert [w["code"] for w in rows] == ["MTZ", "FIL"]  # the default first
    swap = h.client.patch(f"/api/inventory/warehouses/{second['id']}", json={"is_default": True}, headers=h.admin)
    assert swap.status_code == 200 and swap.json()["data"]["is_default"] is True
    rows = h.client.get("/api/inventory/warehouses", headers=h.staff()).json()["data"]
    assert [w["is_default"] for w in rows] == [True, False] and rows[0]["code"] == "FIL"


def test_unknown_field_is_422_not_silently_dropped(h):
    r = h.client.post("/api/inventory/warehouses", json={"name": "x", "code": "x", "org_id": ORG_B}, headers=h.admin)
    assert r.status_code == 422


@pytest.mark.parametrize(
    "path,body",
    [
        ("/api/inventory/receive", {"item_id": ITEM, "warehouse_id": WH1, "qty": "0", "unit_cost_cents": 1}),
        ("/api/inventory/receive", {"item_id": ITEM, "warehouse_id": WH1, "qty": "1.5555", "unit_cost_cents": 1}),
        ("/api/inventory/receive", {"item_id": ITEM, "warehouse_id": WH1, "qty": "1", "unit_cost_cents": -1}),
        ("/api/inventory/receive", {"item_id": "nope", "warehouse_id": WH1, "qty": "1", "unit_cost_cents": 1}),
        ("/api/inventory/issue", {"item_id": ITEM, "warehouse_id": WH1, "qty": "-1"}),
        ("/api/inventory/adjust", {"item_id": ITEM, "warehouse_id": WH1, "counted_qty": "-1"}),
        ("/api/inventory/transfer", {"item_id": ITEM, "from_warehouse_id": WH1, "to_warehouse_id": WH2, "qty": "0"}),
    ],
)
def test_bad_quantities_are_rejected_at_the_boundary(h, path, body):
    assert h.client.post(path, json=body, headers=h.admin).status_code == 422


def test_transfer_to_the_same_warehouse_is_a_422_before_any_rpc(h):
    r = h.client.post("/api/inventory/transfer", json={"item_id": ITEM, "from_warehouse_id": WH1, "to_warehouse_id": WH1, "qty": "1"}, headers=h.admin)
    assert r.status_code == 422 and r.json()["error"]["code"] == "transferencia_mesmo_deposito"
    assert h.db.rpc_calls == []


def test_rpc_success_is_wrapped_and_carries_the_actor_and_decimal_as_string(h):
    h.db.set_rpc_data("inv_receive", {"status": "ok", "moves": [{"id": "m1", "kind": "in"}]})
    r = h.client.post("/api/inventory/receive", json={"item_id": ITEM, "warehouse_id": WH1, "qty": "2.500", "unit_cost_cents": 1000}, headers=h.admin)
    assert r.status_code == 201 and r.json()["data"]["moves"][0]["kind"] == "in"
    name, params = h.db.rpc_calls[-1]
    assert name == "inv_receive" and params["p_org_id"] == ORG_A
    assert params["p_row"]["qty"] == "2.500" and params["p_row"]["created_by"]  # string: JSON floats would round


@pytest.mark.parametrize(
    "code,status",
    [("estoque_insuficiente", 409), ("abaixo_reservado", 409), ("deposito_invalido", 422), ("item_invalido", 422), ("custo_invalido", 422)],
)
def test_rpc_refusals_map_to_stable_codes(h, code, status):
    h.db.set_rpc_data("inv_issue", {"status": "refused", "code": code, "item_id": ITEM})
    r = h.client.post("/api/inventory/issue", json={"item_id": ITEM, "warehouse_id": WH1, "qty": "1"}, headers=h.admin)
    assert r.status_code == status
    assert r.json()["error"]["code"] == code and r.json()["error"]["details"]["item_id"] == ITEM


def test_an_unknown_refusal_code_is_loud_not_swallowed():
    with pytest.raises(RuntimeError):
        from_refusal({"status": "refused", "code": "something_new"})


def test_an_unexpected_rpc_payload_is_loud(s):
    s.db.set_rpc_data("inv_issue", {"unexpected": True})
    with pytest.raises(RuntimeError):
        stock.issue(s, {"item_id": ITEM, "warehouse_id": WH1, "qty": "1"})


# ── org isolation ───────────────────────────────────────────────────────────────────────
def test_a_foreign_org_warehouse_is_a_404_and_cannot_be_patched(s, s_b):
    mine = warehouses.create_warehouse(s, {"name": "Matriz", "code": "MTZ"})
    with pytest.raises(NotFoundError):
        warehouses.get_warehouse(s_b, mine["id"])
    with pytest.raises(NotFoundError):
        warehouses.update_warehouse(s_b, mine["id"], {"name": "hacked"})
    assert warehouses.get_warehouse(s, mine["id"])["name"] == "Matriz"
    assert warehouses.list_warehouses(s_b) == []


def test_each_org_has_its_own_default_and_code_space(s, s_b):
    a = warehouses.create_warehouse(s, {"name": "A", "code": "MTZ"})
    b = warehouses.create_warehouse(s_b, {"name": "B", "code": "MTZ"})
    assert a["is_default"] and b["is_default"]


def test_deactivating_a_default_warehouse_is_refused(s):
    wh = warehouses.create_warehouse(s, {"name": "A", "code": "A"})
    with pytest.raises(InventoryError) as exc:
        warehouses.update_warehouse(s, wh["id"], {"active": False})
    assert exc.value.code == "deposito_padrao"


def test_deactivating_a_warehouse_with_stock_is_refused(s):
    warehouses.create_warehouse(s, {"name": "A", "code": "A"})
    other = warehouses.create_warehouse(s, {"name": "B", "code": "B"})
    s.tbl("stock_balances").insert({"org_id": ORG_A, "item_id": ITEM, "warehouse_id": other["id"], "on_hand": 3, "reserved": 0, "avg_cost_cents": 10}).execute()
    with pytest.raises(InventoryError) as exc:
        warehouses.update_warehouse(s, other["id"], {"active": False})
    assert exc.value.code == "deposito_com_estoque" and exc.value.status_code == 409


def test_usable_warehouse_check_is_org_scoped_and_active_only(s, s_b):
    wh = warehouses.create_warehouse(s, {"name": "A", "code": "A"})
    assert warehouses.require_usable_warehouse(s, wh["id"], field="warehouse_id")["id"] == wh["id"]
    with pytest.raises(InventoryError) as exc:
        warehouses.require_usable_warehouse(s_b, wh["id"], field="warehouse_id")
    assert exc.value.code == "deposito_invalido"


# ── reports (mock rows stand in for what the RPCs wrote) ──────────────────────────────
def _bal(s, item, wh, on_hand, reserved=0, avg=100):
    s.tbl("stock_balances").insert({"org_id": s.org_id, "item_id": item, "warehouse_id": wh, "on_hand": on_hand, "reserved": reserved, "avg_cost_cents": avg}).execute()


def test_valuation_is_sum_of_on_hand_times_average_cost(s):
    wa = warehouses.create_warehouse(s, {"name": "A", "code": "A"})["id"]
    wb = warehouses.create_warehouse(s, {"name": "B", "code": "B"})["id"]
    _bal(s, ITEM, wa, 10, avg=150)       # 1500
    _bal(s, ITEM2, wa, 2.5, avg=1375)    # 3437.5 -> 3438
    _bal(s, ITEM, wb, 4, avg=200)        # 800
    _bal(s, ITEM2, wb, 0, avg=999)       # nothing on hand: no value
    v = reports.valuation(s)
    assert v["method"] == "average_cost"
    assert v["total_cents"] == 1500 + 3438 + 800
    assert {g["warehouse_id"]: g["value_cents"] for g in v["by_warehouse"]} == {wa: 4938, wb: 800}
    assert reports.valuation(s, warehouse_id=wb)["total_cents"] == 800


def test_valuation_and_balances_never_leak_another_org(s, s_b):
    wa = warehouses.create_warehouse(s, {"name": "A", "code": "A"})["id"]
    wb = warehouses.create_warehouse(s_b, {"name": "A", "code": "A"})["id"]
    _bal(s, ITEM, wa, 10)
    _bal(s_b, ITEM, wb, 99)
    assert reports.valuation(s)["total_cents"] == 1000
    rows, total, *_ = reports.list_balances(s)
    assert total == 1 and rows[0]["on_hand"] == 10


def test_low_stock_uses_available_and_min_qty_and_counts_missing_balance_as_zero(s):
    wa = warehouses.create_warehouse(s, {"name": "A", "code": "A"})["id"]
    _bal(s, ITEM, wa, 10, reserved=8)      # available 2
    reports.set_min_qty(s, ITEM, wa, "3")
    reports.set_min_qty(s, ITEM2, wa, "1")  # no balance row -> 0 available -> low
    low = reports.low_stock(s)
    assert {r["item_id"] for r in low} == {ITEM, ITEM2}
    reports.set_min_qty(s, ITEM, wa, "1")   # upsert: available 2 > 1 -> no longer low
    assert {r["item_id"] for r in reports.low_stock(s)} == {ITEM2}
    reports.set_min_qty(s, ITEM2, wa, "0")  # 0 disables the alert
    assert reports.low_stock(s) == []


def test_min_qty_for_a_foreign_warehouse_is_404(s, s_b):
    wa = warehouses.create_warehouse(s, {"name": "A", "code": "A"})["id"]
    with pytest.raises(NotFoundError):
        reports.set_min_qty(s_b, ITEM, wa, "1")


def test_balances_flag_low_stock_and_available(h):
    s = Scope(h.db, CFG, ORG_A)
    wa = warehouses.create_warehouse(s, {"name": "A", "code": "A"})["id"]
    _bal(s, ITEM, wa, 5, reserved=4)
    reports.set_min_qty(s, ITEM, wa, "2")
    data = h.client.get("/api/inventory/balances", headers=h.staff()).json()
    row = data["data"][0]
    assert row["available"] == 1 and row["low_stock"] is True and row["value_cents"] == 500
    assert data["pagination"]["total"] == 1


def test_kardex_is_scoped_to_the_item_and_org_and_ordered(h):
    s = Scope(h.db, CFG, ORG_A)
    wa = warehouses.create_warehouse(s, {"name": "A", "code": "A"})["id"]
    base = {"warehouse_id": wa, "unit_cost_cents": 100, "source": "manual", "reserved_after": 0, "avg_cost_after_cents": 100}
    for seq, (org, item, kind, qty, after) in enumerate(
        [(ORG_A, ITEM, "in", 10, 10), (ORG_A, ITEM, "out", 3, 7), (ORG_A, ITEM2, "in", 1, 1), (ORG_B, ITEM, "in", 99, 99)], start=1
    ):
        s.tbl("stock_moves").insert({**base, "seq": seq, "org_id": org, "item_id": item, "kind": kind, "qty": qty, "on_hand_after": after}).execute()
    rows = h.client.get(f"/api/inventory/kardex?item_id={ITEM}", headers=h.staff()).json()["data"]
    assert [(r["kind"], r["on_hand_after"]) for r in rows] == [("in", 10), ("out", 7)]
