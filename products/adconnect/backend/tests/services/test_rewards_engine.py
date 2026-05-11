"""
Pure-function tests of the rewards engine.

Seeds the mock Supabase with two reward rules + one sellout report, drives
`accrue_for_sellout_approval`, and asserts the resulting ledger writes hit
the right rules with the right amounts.
"""
from __future__ import annotations

from datetime import date, timedelta

from noctusai_lib.testing import MockSupabaseClient

from app.services.rewards_service import (
    LEDGER_TABLE,
    REGRAS_TABLE,
    accrue_for_pedido,
    accrue_for_sellout_approval,
    summarize_ledger,
)

ORG = "org-test"
DIST = "dist-001"


def _build_db(*, rules: list[dict], relatorio: dict | None = None, pedido: dict | None = None) -> MockSupabaseClient:
    db = MockSupabaseClient(validate_schema=False, schema="adconnect")
    db.set_table_data(REGRAS_TABLE, rules)
    if relatorio is not None:
        db.set_table_data("relatorios_sellout", [relatorio])
    if pedido is not None:
        db.set_table_data("pedidos", [pedido])
    return db


def test_accrue_for_sellout_approval_matches_active_rules() -> None:
    today = date.today()
    rules = [
        {
            "id": "rule-1",
            "org_id": ORG,
            "nome": "Cabo 5%",
            "tipo": "cashback",
            "valor": 5.0,
            "aplicavel_categorias": ["Cabos"],
            "aplicavel_produtos": [],
            "aplicavel_distribuidores": [],
            "valor_minimo_pedido": 0,
            "quantidade_minima": 0,
            "ativa": True,
            "valido_de": None,
            "valido_ate": None,
        },
        {
            "id": "rule-2",
            "org_id": ORG,
            "nome": "Geral 1%",
            "tipo": "cashback",
            "valor": 1.0,
            "aplicavel_categorias": [],
            "aplicavel_produtos": [],
            "aplicavel_distribuidores": [],
            "valor_minimo_pedido": 0,
            "quantidade_minima": 0,
            "ativa": True,
            "valido_de": None,
            "valido_ate": None,
        },
        {
            "id": "rule-3-expired",
            "org_id": ORG,
            "nome": "Expirada",
            "tipo": "cashback",
            "valor": 99.0,
            "aplicavel_categorias": [],
            "aplicavel_produtos": [],
            "aplicavel_distribuidores": [],
            "valor_minimo_pedido": 0,
            "quantidade_minima": 0,
            "ativa": True,
            "valido_de": None,
            "valido_ate": (today - timedelta(days=1)).isoformat(),
        },
    ]
    relatorio = {
        "id": "rel-001",
        "org_id": ORG,
        "distributor_id": DIST,
        "submission_mode": "estruturado",
        "valor_total": 1000.0,
        "quantidade_itens": 5,
        "items_json": [{"sku": "CAB-1", "categoria": "Cabos", "quantidade": 5}],
        "status": "aprovado",
    }
    db = _build_db(rules=rules, relatorio=relatorio)
    inserted = accrue_for_sellout_approval(db, relatorio_id="rel-001")

    payloads = db.table(LEDGER_TABLE).inserted_payloads
    # Two rules match (rule-1 by category, rule-2 catch-all); rule-3 expired.
    assert len(payloads) == 2
    assert len(inserted) == 2
    by_rule = {p["regra_id"]: p["valor"] for p in payloads}
    assert by_rule["rule-1"] == 50.0  # 5% of 1000
    assert by_rule["rule-2"] == 10.0  # 1% of 1000
    for p in payloads:
        assert p["distributor_id"] == DIST
        assert p["source_relatorio_sellout_id"] == "rel-001"
        assert p["source_pedido_id"] is None
        assert p["status"] == "pendente"


def test_accrue_for_sellout_approval_skips_unapproved() -> None:
    rules = [
        {
            "id": "rule-1",
            "org_id": ORG,
            "nome": "X",
            "tipo": "cashback",
            "valor": 5.0,
            "aplicavel_categorias": [],
            "aplicavel_produtos": [],
            "aplicavel_distribuidores": [],
            "valor_minimo_pedido": 0,
            "quantidade_minima": 0,
            "ativa": True,
        }
    ]
    relatorio = {
        "id": "rel-002",
        "org_id": ORG,
        "distributor_id": DIST,
        "submission_mode": "estruturado",
        "valor_total": 500.0,
        "quantidade_itens": 1,
        "items_json": [],
        "status": "pendente",
    }
    db = _build_db(rules=rules, relatorio=relatorio)
    inserted = accrue_for_sellout_approval(db, relatorio_id="rel-002")
    assert inserted == []
    assert db.table(LEDGER_TABLE).inserted_payloads == []


def test_accrue_thresholds_block_small_orders() -> None:
    rules = [
        {
            "id": "rule-min",
            "org_id": ORG,
            "nome": "Min",
            "tipo": "cashback",
            "valor": 5.0,
            "aplicavel_categorias": [],
            "aplicavel_produtos": [],
            "aplicavel_distribuidores": [],
            "valor_minimo_pedido": 1000.0,
            "quantidade_minima": 0,
            "ativa": True,
        }
    ]
    relatorio = {
        "id": "rel-003",
        "org_id": ORG,
        "distributor_id": DIST,
        "submission_mode": "estruturado",
        "valor_total": 500.0,
        "quantidade_itens": 1,
        "items_json": [],
        "status": "aprovado",
    }
    db = _build_db(rules=rules, relatorio=relatorio)
    assert accrue_for_sellout_approval(db, relatorio_id="rel-003") == []


def test_accrue_distributor_filter() -> None:
    rules = [
        {
            "id": "rule-dist",
            "org_id": ORG,
            "nome": "Só dist-002",
            "tipo": "cashback",
            "valor": 5.0,
            "aplicavel_categorias": [],
            "aplicavel_produtos": [],
            "aplicavel_distribuidores": ["dist-002"],
            "valor_minimo_pedido": 0,
            "quantidade_minima": 0,
            "ativa": True,
        }
    ]
    relatorio = {
        "id": "rel-004",
        "org_id": ORG,
        "distributor_id": DIST,
        "submission_mode": "estruturado",
        "valor_total": 500.0,
        "quantidade_itens": 1,
        "items_json": [],
        "status": "aprovado",
    }
    db = _build_db(rules=rules, relatorio=relatorio)
    assert accrue_for_sellout_approval(db, relatorio_id="rel-004") == []


def test_accrue_for_pedido_writes_ledger_row() -> None:
    rules = [
        {
            "id": "rule-1",
            "org_id": ORG,
            "nome": "Geral",
            "tipo": "cashback",
            "valor": 2.5,
            "aplicavel_categorias": [],
            "aplicavel_produtos": [],
            "aplicavel_distribuidores": [],
            "valor_minimo_pedido": 0,
            "quantidade_minima": 0,
            "ativa": True,
        }
    ]
    pedido = {
        "id": "ped-1",
        "org_id": ORG,
        "distributor_id": DIST,
        "valor_total": 200.0,
        "items": [{"sku": "X", "quantidade": 4}],
    }
    db = _build_db(rules=rules, pedido=pedido)
    inserted = accrue_for_pedido(db, pedido_id="ped-1")
    payloads = db.table(LEDGER_TABLE).inserted_payloads
    assert len(payloads) == 1
    assert payloads[0]["valor"] == 5.0  # 2.5% of 200
    assert payloads[0]["source_pedido_id"] == "ped-1"
    assert payloads[0]["source_relatorio_sellout_id"] is None
    assert len(inserted) == 1


def test_accrue_for_pedido_via_explicit_row() -> None:
    """Service layer often passes the row directly (avoid an extra SELECT)."""
    rules = [
        {
            "id": "rule-1",
            "org_id": ORG,
            "nome": "Geral",
            "tipo": "cashback",
            "valor": 1.0,
            "aplicavel_categorias": [],
            "aplicavel_produtos": [],
            "aplicavel_distribuidores": [],
            "valor_minimo_pedido": 0,
            "quantidade_minima": 0,
            "ativa": True,
        }
    ]
    db = _build_db(rules=rules)
    inserted = accrue_for_pedido(
        db,
        pedido_id="ped-99",
        pedido_row={
            "id": "ped-99",
            "org_id": ORG,
            "distributor_id": DIST,
            "valor_total": 1000.0,
            "items": [],
        },
    )
    assert len(inserted) == 1
    assert db.table(LEDGER_TABLE).inserted_payloads[0]["valor"] == 10.0


def test_summarize_ledger_groups_by_type_and_status() -> None:
    rows = [
        {"tipo": "cashback", "status": "liberado", "valor": 100.0},
        {"tipo": "cashback", "status": "utilizado", "valor": 30.0},
        {"tipo": "cashback", "status": "pendente", "valor": 50.0},
        {"tipo": "verba_mkt", "status": "liberado", "valor": 20.0},
    ]
    summary = summarize_ledger(rows)
    assert summary["cashbackAvailable"] == 70.0  # 100 - 30
    assert summary["cashbackPending"] == 50.0
    assert summary["cashbackUsed"] == 30.0
    assert summary["verbaMktAvailable"] == 20.0
    assert summary["verbaMktPending"] == 0.0
