"""`StockPort`: Protocol conformance, the Fake's real rules, the factory, and the real port's RPC wiring."""
from __future__ import annotations

from decimal import Decimal

import pytest

from noctusai_lib.domain.inventory import FakeStockPort, InventoryError, NoopStockPort, StockPort, SupabaseStockPort, make_stock_port

from .conftest import CFG, ITEM, ITEM2, ORG_A, ORG_B, WH1, db  # noqa: F401  (db: fixture)


def test_every_implementation_satisfies_the_protocol():
    assert isinstance(FakeStockPort(), StockPort) and isinstance(NoopStockPort(), StockPort)
    assert isinstance(SupabaseStockPort(object(), CFG), StockPort)


def test_factory():
    assert isinstance(make_stock_port(), NoopStockPort)
    assert isinstance(make_stock_port("fake"), FakeStockPort)
    assert isinstance(make_stock_port("supabase", db=object(), cfg=CFG), SupabaseStockPort)
    with pytest.raises(ValueError):
        make_stock_port("supabase")
    with pytest.raises(ValueError):
        make_stock_port("redis")  # type: ignore[arg-type]


def test_noop_never_holds_or_fails():
    p = NoopStockPort()
    assert p.reserve(ORG_A, "O1", [{"item_id": ITEM, "qty": 5}])["moves"] == []
    assert p.commit(ORG_A, "O1")["status"] == "ok" and p.release(ORG_A, "O1")["status"] == "ok"


def test_fake_the_last_unit_cannot_be_sold_twice():
    p = FakeStockPort()
    p.receive(ORG_A, ITEM, 1, 5000)
    assert p.reserve(ORG_A, "O1", [{"item_id": ITEM, "qty": 1}])["status"] == "ok"
    with pytest.raises(InventoryError) as exc:
        p.reserve(ORG_A, "O2", [{"item_id": ITEM, "qty": 1}])
    assert exc.value.code == "estoque_insuficiente" and exc.value.status_code == 409
    assert p.available(ORG_A, ITEM) == 0


def test_fake_is_all_or_none_and_idempotent_by_order_ref():
    p = FakeStockPort()
    p.receive(ORG_A, ITEM, 5, 100)
    p.receive(ORG_A, ITEM2, 1, 100)
    with pytest.raises(InventoryError):
        p.reserve(ORG_A, "O1", [{"item_id": ITEM, "qty": 2}, {"item_id": ITEM2, "qty": 2}])
    assert p.available(ORG_A, ITEM) == 5  # nothing was held
    assert p.reserve(ORG_A, "O1", [{"item_id": ITEM, "qty": 2}])["status"] == "ok"
    assert p.reserve(ORG_A, "O1", [{"item_id": ITEM, "qty": 2}])["status"] == "replayed"
    assert p.available(ORG_A, ITEM) == 3


def test_fake_commit_converts_reserved_to_out_at_average_cost_once():
    p = FakeStockPort()
    p.receive(ORG_A, ITEM, 10, 100)
    p.receive(ORG_A, ITEM, 10, 200)
    p.reserve(ORG_A, "O1", [{"item_id": ITEM, "qty": 3}])
    done = p.commit(ORG_A, "O1")
    assert done["moves"][0]["unit_cost_cents"] == 150
    b = p.balance(ORG_A, ITEM)
    assert (b.on_hand, b.reserved) == (Decimal(17), Decimal(0))
    assert p.commit(ORG_A, "O1")["status"] == "replayed" and p.balance(ORG_A, ITEM).on_hand == 17
    with pytest.raises(InventoryError) as exc:
        p.release(ORG_A, "O1")
    assert exc.value.code == "reserva_consumida"


def test_fake_release_then_commit_is_refused_and_release_of_nothing_is_a_noop():
    p = FakeStockPort()
    p.receive(ORG_A, ITEM, 5, 100)
    p.reserve(ORG_A, "O1", [{"item_id": ITEM, "qty": 4}])
    assert p.release(ORG_A, "O1")["status"] == "ok" and p.available(ORG_A, ITEM) == 5
    assert p.release(ORG_A, "O1")["status"] == "replayed"
    with pytest.raises(InventoryError) as exc:
        p.commit(ORG_A, "O1")
    assert exc.value.code == "reserva_liberada"
    assert p.release(ORG_A, "NEVER")["moves"] == []
    with pytest.raises(InventoryError) as exc:
        p.commit(ORG_A, "NEVER")
    assert exc.value.code == "sem_reserva"


def test_fake_partial_lines_and_divergent_quantity():
    p = FakeStockPort()
    p.receive(ORG_A, ITEM, 5, 100)
    p.receive(ORG_A, ITEM2, 5, 100)
    p.reserve(ORG_A, "O1", [{"item_id": ITEM, "qty": 2}, {"item_id": ITEM2, "qty": 3}])
    with pytest.raises(InventoryError) as exc:
        p.commit(ORG_A, "O1", [{"item_id": ITEM, "qty": 9}])
    assert exc.value.code == "quantidade_divergente"
    assert len(p.commit(ORG_A, "O1", [{"item_id": ITEM}])["moves"]) == 1
    assert p.balance(ORG_A, ITEM2).reserved == 3


def test_fake_orgs_and_warehouses_are_isolated_and_fractional_kg_works():
    p = FakeStockPort()
    p.receive(ORG_A, ITEM, Decimal("2.500"), 1000)
    p.receive(ORG_A, ITEM, Decimal("1.500"), 2000)
    assert p.balance(ORG_A, ITEM).avg_cost_cents == 1375 and p.available(ORG_A, ITEM) == Decimal("4.000")
    with pytest.raises(InventoryError):
        p.reserve(ORG_B, "O1", [{"item_id": ITEM, "qty": "0.001"}])  # org B has none
    with pytest.raises(InventoryError):
        p.reserve(ORG_A, "O2", [{"item_id": ITEM, "qty": 1, "warehouse_id": WH1}])  # other warehouse, none there
    with pytest.raises(InventoryError) as exc:
        p.reserve(ORG_A, "O3", [{"item_id": ITEM, "qty": 0}])
    assert exc.value.code == "quantidade_invalida"


def test_fake_without_a_default_warehouse_requires_one_per_line():
    p = FakeStockPort(default_warehouse=None)
    with pytest.raises(InventoryError) as exc:
        p.reserve(ORG_A, "O1", [{"item_id": ITEM, "qty": 1}])
    assert exc.value.code == "sem_deposito_padrao"


def test_supabase_port_calls_the_rpcs_scoped_to_the_org(db):  # noqa: F811
    port = SupabaseStockPort(db, CFG)
    db.set_rpc_data("inv_reserve", {"status": "ok", "moves": [{"kind": "reserve"}]})
    db.set_rpc_data("inv_commit", {"status": "replayed", "moves": []})
    db.set_rpc_data("inv_release", {"status": "refused", "code": "reserva_consumida", "item_id": ITEM})
    assert port.reserve(ORG_A, "O1", [{"item_id": ITEM, "qty": Decimal("1.5")}])["status"] == "ok"
    name, params = db.rpc_calls[-1]
    assert (name, params["p_org_id"], params["p_order_ref"], params["p_source"]) == ("inv_reserve", ORG_A, "O1", "order")
    assert params["p_lines"] == [{"item_id": ITEM, "qty": "1.5"}]
    assert port.commit(ORG_B, "O1")["status"] == "replayed" and db.rpc_calls[-1][1]["p_org_id"] == ORG_B
    with pytest.raises(InventoryError) as exc:
        port.release(ORG_A, "O1")
    assert exc.value.code == "reserva_consumida"
    with pytest.raises(InventoryError):
        port.reserve(ORG_A, "O1", [])


def test_receive_stock_is_idempotent_on_source_ref_in_the_fake_and_calls_the_receive_rpc_in_the_real_port(db):  # noqa: F811
    fake = FakeStockPort()
    kw = dict(item_id=ITEM, warehouse_id=WH1, qty="2.500", unit_cost_cents=1234, source="purchasing", source_ref="rl-1")
    first = fake.receive_stock(ORG_A, **kw)
    again = fake.receive_stock(ORG_A, **kw)
    assert first["status"] == "ok" and again["status"] == "replayed"
    assert fake.balance(ORG_A, ITEM, WH1).on_hand == Decimal("2.5") and fake.balance(ORG_A, ITEM, WH1).avg_cost_cents == 1234
    assert fake.moves[-1]["source_ref"] == "rl-1" and fake.moves[-1]["unit_cost_cents"] == 1234
    with pytest.raises(InventoryError):
        fake.receive_stock(ORG_A, **{**kw, "qty": 0, "source_ref": "rl-2"})
    assert NoopStockPort().receive_stock(ORG_A, **kw)["status"] == "ok"

    db.set_rpc_data("inv_receive", {"status": "ok", "moves": [{"id": "m1"}]})
    real = make_stock_port("supabase", db=db, cfg=CFG)
    assert real.receive_stock(ORG_A, **kw, user_id="u1", note="NF 1")["status"] == "ok"
    name, params = db.rpc_calls[-1]
    assert name == "inv_receive" and params["p_org_id"] == ORG_A
    assert params["p_row"]["source"] == "purchasing" and params["p_row"]["source_ref"] == "rl-1"
    assert params["p_row"]["qty"] == "2.500" and params["p_row"]["unit_cost_cents"] == 1234 and params["p_row"]["created_by"] == "u1"
