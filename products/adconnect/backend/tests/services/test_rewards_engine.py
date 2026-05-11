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
    _fetch_active_rules,
    _resolve_org_id,
    accrue_for_pedido,
    accrue_for_sellout_approval,
    summarize_ledger,
)

ORG = "org-test"
DIST = "dist-001"


def _build_db(
    *,
    rules: list[dict],
    relatorio: dict | None = None,
    pedido: dict | None = None,
    distributors: list[dict] | None = None,
) -> MockSupabaseClient:
    """Seed a mock client with rules + a distributors row mapping DIST→ORG.

    The rewards service now resolves a distributor's owning brand `org_id`
    via the `distributors` table (Phase 1 fix — cross-tenant safety). Tests
    MUST seed at least one distributors row, otherwise `_resolve_org_id`
    returns None and the accrual is refused.
    """
    db = MockSupabaseClient(validate_schema=False, schema="adconnect")
    db.set_table_data(REGRAS_TABLE, rules)
    if distributors is None:
        distributors = [{"id": DIST, "org_id": ORG}]
    db.set_table_data("distributors", distributors)
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


def test_resolve_org_id_via_distributors_table() -> None:
    """The resolver JOINs through `adconnect.distributors` — this is the
    cross-tenant safety primitive. Reading `org_id` directly off
    `relatorios_sellout` / `pedidos` (the previous slip) returned None in
    production because those tables don't have an `org_id` column; the rule
    fetch then fell back to "all rows across every brand" (cross-tenant leak).

    Note on mock semantics: `MockSupabaseClient`'s SELECT path does NOT
    evaluate `.eq()` predicates against seeded rows (that's a documented
    limitation — it filters on UPDATE/DELETE only). For cross-tenant tests
    we drive the resolver via `set_responses(...)` so the response sequence
    is under test control, simulating both the "found" and "not found"
    PostgREST results that the real Supabase client would return.
    """
    from noctusai_lib.testing.mocks import MockSupabaseResponse

    db = MockSupabaseClient(validate_schema=False, schema="adconnect")
    db.table("distributors").set_responses([
        MockSupabaseResponse(data=[{"id": "dist-A", "org_id": "org-A"}]),
    ])
    assert _resolve_org_id(db, "dist-A") == "org-A"


def test_resolve_org_id_returns_none_when_distributor_missing() -> None:
    """Missing distributor row → None → caller refuses accrual."""
    from noctusai_lib.testing.mocks import MockSupabaseResponse

    db = MockSupabaseClient(validate_schema=False, schema="adconnect")
    db.table("distributors").set_responses([
        MockSupabaseResponse(data=[]),  # PostgREST returns empty list for no match
    ])
    assert _resolve_org_id(db, "dist-NOT-IN-DB") is None


def test_resolve_org_id_returns_none_when_distributor_id_falsy() -> None:
    """Defense-in-depth: empty / None distributor_id short-circuits — no SQL."""
    db = MockSupabaseClient(validate_schema=False, schema="adconnect")
    assert _resolve_org_id(db, "") is None


def test_fetch_active_rules_refuses_falsy_org_id() -> None:
    """Defense-in-depth: `_fetch_active_rules` MUST return [] for a falsy
    `org_id` — never fall back to "all rows across every brand".

    Regression: before this guard, the function would query
    `regras_recompensa` without an `org_id` predicate when caller passed
    None, returning every brand's active rules. Combined with the
    `_resolve_org_id` upstream fix this is a belt-and-suspenders defense.
    """
    db = MockSupabaseClient(validate_schema=False, schema="adconnect")
    # Seed rules belonging to two different orgs — the guard must refuse
    # regardless, never returning ANY of them.
    db.set_table_data(REGRAS_TABLE, [
        {"id": "rule-A", "org_id": "org-A", "ativa": True, "nome": "A"},
        {"id": "rule-B", "org_id": "org-B", "ativa": True, "nome": "B"},
    ])
    assert _fetch_active_rules(db, None) == []
    assert _fetch_active_rules(db, "") == []


def test_cross_tenant_accrual_refused_when_distributor_orphan() -> None:
    """End-to-end cross-tenant safety check: when the distributor referenced
    by the sellout report has NO row in `adconnect.distributors` (because the
    row belongs to a different tenant whose RLS-scoped client can't see it,
    or simply doesn't exist), the entire accrual is refused — zero ledger
    writes.

    Before the fix, this code path read `org_id` directly off the relatorio
    row (a column that doesn't exist), got None, and fell back to "fetch
    every active rule across every brand" — then wrote ledger entries
    against the wrong tenant's rules. Post-fix, `_resolve_org_id` returns
    None and the accrue function short-circuits with an explicit early
    return.

    Drives the empty-distributors-lookup branch via `set_responses` because
    the mock SELECT path doesn't evaluate `.eq()` predicates against seeded
    rows.
    """
    from noctusai_lib.testing.mocks import MockSupabaseResponse

    relatorio = {
        "id": "rel-orphan",
        "distributor_id": "dist-FROM-ORG-B",
        "submission_mode": "estruturado",
        "valor_total": 1000.0,
        "quantidade_itens": 1,
        "items_json": [],
        "status": "aprovado",
    }
    db = MockSupabaseClient(validate_schema=False, schema="adconnect")
    db.set_table_data("relatorios_sellout", [relatorio])
    # Force distributors lookup to return empty (the dist-id isn't visible
    # to this org's client — RLS-scoped, deleted, or simply non-existent).
    db.table("distributors").set_responses([MockSupabaseResponse(data=[])])

    inserted = accrue_for_sellout_approval(db, relatorio_id="rel-orphan")
    assert inserted == []
    assert db.table(LEDGER_TABLE).inserted_payloads == [], (
        "Cross-tenant safety violation: accrual fired for a distributor "
        "whose distributors-table row isn't visible to the current org."
    )


def test_accrual_refused_when_pedido_distributor_orphan() -> None:
    """Same orphan-distributor refusal for the `accrue_for_pedido` path.
    Mock SELECT semantics: drive via response_queue (see resolver test)."""
    from noctusai_lib.testing.mocks import MockSupabaseResponse

    pedido = {
        "id": "ped-orphan",
        "distributor_id": "dist-NOT-IN-DB",
        "valor_total": 500.0,
        "items": [],
    }
    db = MockSupabaseClient(validate_schema=False, schema="adconnect")
    db.set_table_data("pedidos", [pedido])
    db.table("distributors").set_responses([MockSupabaseResponse(data=[])])

    inserted = accrue_for_pedido(db, pedido_id="ped-orphan")
    assert inserted == []
    assert db.table(LEDGER_TABLE).inserted_payloads == []


def test_payload_excludes_nonexistent_columns() -> None:
    """Phase 2: the payload built by `_build_accrual_row` MUST NOT include
    columns that don't exist on `recompensas_acumuladas` (`org_id`, `moeda`,
    `descricao`). Mock accepts; prod would reject the INSERT with
    `column ... does not exist`."""
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
    relatorio = {
        "id": "rel-cols",
        "distributor_id": DIST,
        "submission_mode": "estruturado",
        "valor_total": 100.0,
        "quantidade_itens": 1,
        "items_json": [],
        "status": "aprovado",
    }
    db = _build_db(rules=rules, relatorio=relatorio)
    accrue_for_sellout_approval(db, relatorio_id="rel-cols")
    payloads = db.table(LEDGER_TABLE).inserted_payloads
    assert len(payloads) == 1
    payload = payloads[0]
    # The three keys removed in Phase 2 — none of these columns exist on
    # the migration's CREATE TABLE.
    assert "org_id" not in payload, (
        "recompensas_acumuladas has no org_id column — payload must not write it"
    )
    assert "moeda" not in payload, (
        "recompensas_acumuladas has no moeda column — payload must not write it"
    )
    assert "descricao" not in payload, (
        "recompensas_acumuladas has no descricao column — payload must not write it"
    )


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
