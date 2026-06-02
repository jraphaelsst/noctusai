"""
Service-level tests for the admin aggregation logic (Phase 6).

The service is a pure-function-on-DB-rows aggregator — feed it seeded mock
data and assert the shape it produces. Routers are tested separately at
`tests/routers/test_admin_router.py`.

Mock note: `MockSupabaseClient`'s `.eq()` / `.in_()` are no-ops for most
ops, but `.gte()`/`.lte()` ARE evaluated literally — so `placed_at` dates
for `pedidos_this_month` MUST fall within the current calendar month
(computed from `date.today()`), matching the same source used by
`admin_service._month_bounds()`. Static May-2026 dates broke in June.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

from noctusai_lib.testing import (
    MockSupabaseClient,
    MockUser,
    MockUserResponse,
)

from app.services import admin_service

# Dates relative to the current month so `dashboard_metrics`'s
# `_month_bounds()` (which uses `date.today()`) always includes them.
_TODAY = date.today()
_THIS_MONTH_START = _TODAY.replace(day=1).isoformat()        # e.g. "2026-06-01"
_THIS_MONTH_MID = _TODAY.replace(day=min(8, _TODAY.day)).isoformat()  # e.g. "2026-06-08" or earlier


ORG_ID = "org-test-123"
DIST_A = "11111111-1111-1111-1111-111111111111"
DIST_B = "22222222-2222-2222-2222-222222222222"


def _mk_db() -> MockSupabaseClient:
    db = MockSupabaseClient(validate_schema=False, schema="adconnect")
    db.auth.get_user = MagicMock(return_value=MockUserResponse(MockUser(org_id=ORG_ID)))
    return db


# ---------------------------------------------------------------------------
# dashboard_metrics
# ---------------------------------------------------------------------------


class TestDashboardMetrics:
    def test_aggregates_by_status_buckets(self) -> None:
        db = _mk_db()
        # MockSupabaseClient applies .eq() predicates at SELECT — seeded rows
        # for tables the service filters by .eq("org_id", ORG_ID) MUST carry
        # org_id. distributors + relatorios_sellout are org_id-scoped; pedidos
        # / recompensas / faturas are queried without an org filter so they
        # don't need it.
        db.set_table_data(admin_service.DISTRIBUTORS_TABLE, [
            {"id": DIST_A, "org_id": ORG_ID, "status": "ativo"},
            {"id": DIST_B, "org_id": ORG_ID, "status": "ativo"},
            {"id": "dist-3", "org_id": ORG_ID, "status": "inativo"},
        ])
        db.set_table_data(admin_service.PEDIDOS_TABLE, [
            {"id": "p1", "status": "enviado", "placed_at": _THIS_MONTH_START},
            {"id": "p2", "status": "entregue", "placed_at": _THIS_MONTH_MID},
        ])
        db.set_table_data(admin_service.SELLOUT_TABLE, [
            {"id": "s1", "org_id": ORG_ID, "status": "pendente"},
            {"id": "s2", "org_id": ORG_ID, "status": "aprovado"},
        ])
        db.set_table_data(admin_service.RECOMPENSAS_TABLE, [
            {"id": "r1", "status": "acumulado", "valor": 100.0},
            {"id": "r2", "status": "acumulado", "valor": 50.5},
            {"id": "r3", "status": "resgatado", "valor": 25.0},
        ])
        db.set_table_data(admin_service.FATURAS_TABLE, [
            {"id": "f1", "status": "emitida"},
            {"id": "f2", "status": "paga"},
            {"id": "f3", "status": "vencida"},
        ])

        out = admin_service.dashboard_metrics(db, org_id=ORG_ID)

        assert out["distributors"]["total"] == 3
        assert out["distributors"]["by_status"]["ativo"] == 2
        assert out["distributors"]["by_status"]["inativo"] == 1
        assert out["pedidos_this_month"]["total"] == 2
        assert out["sellout"]["by_status"]["pendente"] == 1
        assert out["sellout"]["by_status"]["aprovado"] == 1
        # recompensas total is the sum, not just count.
        assert out["recompensas"]["total"] == int(100.0 + 50.5 + 25.0)
        assert out["recompensas"]["by_status"]["acumulado"] == 2
        assert out["faturas"]["by_status"]["emitida"] == 1
        assert out["faturas"]["by_status"]["paga"] == 1
        assert out["faturas"]["by_status"]["vencida"] == 1

    def test_empty_returns_zeros(self) -> None:
        db = _mk_db()
        # No data seeded → every bucket should be zero.
        out = admin_service.dashboard_metrics(db, org_id=ORG_ID)
        assert out["distributors"]["total"] == 0
        assert out["pedidos_this_month"]["total"] == 0
        # by_status keys all present but zero.
        assert all(v == 0 for v in out["distributors"]["by_status"].values())


# ---------------------------------------------------------------------------
# distributor_list_with_metrics
# ---------------------------------------------------------------------------


class TestDistributorListWithMetrics:
    def test_aggregates_per_distributor(self) -> None:
        db = _mk_db()
        db.set_table_data(admin_service.DISTRIBUTORS_TABLE, [
            {"id": DIST_A, "org_id": ORG_ID, "cnpj": "11.111.111/0001-11",
             "nome": "Distribuidor A", "status": "ativo", "tier": "STARTER"},
            {"id": DIST_B, "org_id": ORG_ID, "cnpj": "22.222.222/0001-22",
             "nome": "Distribuidor B", "status": "ativo", "tier": "MASTER"},
        ])
        db.set_table_data(admin_service.PEDIDOS_TABLE, [
            {"id": "p1", "distributor_id": DIST_A, "placed_at": "2026-05-01T10:00:00"},
            {"id": "p2", "distributor_id": DIST_A, "placed_at": "2026-05-08T15:00:00"},
            {"id": "p3", "distributor_id": DIST_B, "placed_at": "2026-04-12T09:00:00"},
        ])
        db.set_table_data(admin_service.RECOMPENSAS_TABLE, [
            {"distributor_id": DIST_A, "valor": 100.0, "status": "acumulado"},
            {"distributor_id": DIST_A, "valor": 50.0, "status": "acumulado"},
            {"distributor_id": DIST_A, "valor": 25.0, "status": "resgatado"},
            {"distributor_id": DIST_B, "valor": 200.0, "status": "acumulado"},
        ])
        db.set_table_data(admin_service.FATURAS_TABLE, [
            {"distributor_id": DIST_A, "status": "emitida"},
            {"distributor_id": DIST_A, "status": "vencida"},
            {"distributor_id": DIST_A, "status": "paga"},
            {"distributor_id": DIST_B, "status": "emitida"},
        ])

        out = admin_service.distributor_list_with_metrics(db, org_id=ORG_ID)
        assert len(out) == 2
        a = next(d for d in out if d["id"] == DIST_A)
        b = next(d for d in out if d["id"] == DIST_B)

        assert a["metrics"]["total_pedidos"] == 2
        # Only acumulado rows roll into balance — resgatado excluded.
        assert a["metrics"]["recompensa_balance"] == 150.0
        # Pending = emitida + vencida (paga not pending).
        assert a["metrics"]["invoices_pending"] == 2
        assert a["metrics"]["last_pedido_at"] == "2026-05-08T15:00:00"

        assert b["metrics"]["total_pedidos"] == 1
        assert b["metrics"]["recompensa_balance"] == 200.0
        assert b["metrics"]["invoices_pending"] == 1

    def test_distributor_with_no_activity_zeros(self) -> None:
        db = _mk_db()
        db.set_table_data(admin_service.DISTRIBUTORS_TABLE, [
            {"id": "fresh", "org_id": ORG_ID, "cnpj": "00.000.000/0001-00",
             "nome": "Fresh Distributor", "status": "pendente", "tier": "STARTER"},
        ])
        out = admin_service.distributor_list_with_metrics(db, org_id=ORG_ID)
        assert len(out) == 1
        assert out[0]["metrics"]["total_pedidos"] == 0
        assert out[0]["metrics"]["recompensa_balance"] == 0.0
        assert out[0]["metrics"]["invoices_pending"] == 0
        assert out[0]["metrics"]["last_pedido_at"] is None


# ---------------------------------------------------------------------------
# sellout_queue
# ---------------------------------------------------------------------------


class TestSelloutQueue:
    def test_returns_only_pending_or_em_analise(self) -> None:
        db = _mk_db()
        # MockSupabaseClient applies .eq() predicates at SELECT — seeded rows
        # MUST carry org_id matching ORG_ID so `.eq("org_id", ORG_ID)` in
        # admin_service.sellout_queue returns them.
        db.set_table_data(admin_service.SELLOUT_TABLE, [
            {"id": "s1", "org_id": ORG_ID, "status": "pendente"},
            {"id": "s2", "org_id": ORG_ID, "status": "em_analise"},
            {"id": "s3", "org_id": ORG_ID, "status": "aprovado"},
            {"id": "s4", "org_id": ORG_ID, "status": "recusado"},
        ])
        out = admin_service.sellout_queue(db, org_id=ORG_ID)
        statuses = {r["status"] for r in out}
        assert statuses == {"pendente", "em_analise"}
        assert len(out) == 2


# ---------------------------------------------------------------------------
# list_invoices_with_filters
# ---------------------------------------------------------------------------


class TestListInvoicesWithFilters:
    def test_filters_by_status(self) -> None:
        db = _mk_db()
        db.set_table_data(admin_service.DISTRIBUTORS_TABLE, [
            {"id": DIST_A, "org_id": ORG_ID},
        ])
        db.set_table_data(admin_service.FATURAS_TABLE, [
            {"id": "f1", "distributor_id": DIST_A, "status": "emitida",
             "due_date": "2026-06-15"},
            {"id": "f2", "distributor_id": DIST_A, "status": "paga",
             "due_date": "2026-04-01"},
            {"id": "f3", "distributor_id": DIST_A, "status": "vencida",
             "due_date": "2026-03-10"},
        ])
        emitidas = admin_service.list_invoices_with_filters(
            db, org_id=ORG_ID, status="emitida"
        )
        assert len(emitidas) == 1
        assert emitidas[0]["status"] == "emitida"

    def test_filters_by_distributor_id_and_due_range(self) -> None:
        db = _mk_db()
        db.set_table_data(admin_service.DISTRIBUTORS_TABLE, [
            {"id": DIST_A, "org_id": ORG_ID},
            {"id": DIST_B, "org_id": ORG_ID},
        ])
        db.set_table_data(admin_service.FATURAS_TABLE, [
            {"id": "f1", "distributor_id": DIST_A, "status": "emitida",
             "due_date": "2026-06-15"},
            {"id": "f2", "distributor_id": DIST_B, "status": "emitida",
             "due_date": "2026-07-01"},
        ])
        a_only = admin_service.list_invoices_with_filters(
            db, org_id=ORG_ID, distributor_id=DIST_A
        )
        assert len(a_only) == 1
        assert a_only[0]["id"] == "f1"

        june_only = admin_service.list_invoices_with_filters(
            db, org_id=ORG_ID, due_from="2026-06-01", due_to="2026-06-30"
        )
        assert len(june_only) == 1
        assert june_only[0]["id"] == "f1"

    def test_excludes_invoices_for_distributors_outside_org(self) -> None:
        db = _mk_db()
        # Only DIST_A is in the admin's org.
        db.set_table_data(admin_service.DISTRIBUTORS_TABLE, [
            {"id": DIST_A, "org_id": ORG_ID},
        ])
        db.set_table_data(admin_service.FATURAS_TABLE, [
            {"id": "f1", "distributor_id": DIST_A, "status": "emitida"},
            {"id": "f-leak", "distributor_id": "OTHER-ORG-DIST",
             "status": "emitida"},
        ])
        out = admin_service.list_invoices_with_filters(db, org_id=ORG_ID)
        ids = {r["id"] for r in out}
        assert ids == {"f1"}


# ---------------------------------------------------------------------------
# list_reward_rules
# ---------------------------------------------------------------------------


class TestListRewardRules:
    def test_returns_all_when_only_active_false(self) -> None:
        db = _mk_db()
        db.set_table_data(admin_service.REGRAS_TABLE, [
            {"id": "r1", "org_id": ORG_ID, "ativa": True, "nome": "Active"},
            {"id": "r2", "org_id": ORG_ID, "ativa": False, "nome": "Inactive"},
        ])
        out = admin_service.list_reward_rules(db, org_id=ORG_ID, only_active=False)
        assert len(out) == 2
