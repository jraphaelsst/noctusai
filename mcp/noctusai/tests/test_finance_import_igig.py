"""Tests for ``noctus.dev.finance_import_igig`` -- hermetic: injected mock client, fixture rows, no live database.

The paid-invoice settlement path (row-locked RPC) is covered by the seed suite
(`seed/lib/backend/tests/domain/finance/test_igig_importer.py`); here the write leg uses open invoices only, so
the plain mock is faithful."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "seed" / "lib" / "backend"))

from noctusai_lib.testing.mocks import MockSupabaseClient  # noqa: E402
from tools.noctus.dev.finance_import_igig import finance_import_igig  # noqa: E402

ORG = "5b0e8f7a-1c2d-4e3f-9a8b-7c6d5e4f3a2b"
CLI = "c1111111-0000-4000-8000-000000000001"


def _fat(i, comp, total, status="aberta"):
    return {"id": f"f{i:07d}-0000-4000-8000-000000000000", "org_id": ORG, "cliente_id": CLI, "competencia": comp,
            "valor_total": total, "vencimento": None, "status": status, "pago_em": None}


def _db(faturas):
    db = MockSupabaseClient(validate_schema=False, schema="igig")
    db.set_table_data("fatura", faturas)
    db.set_table_data("fatura_item", [])
    db.set_table_data("cliente", [{"id": CLI, "org_id": ORG, "nome": "Alfa"}])
    return db


def test_real_database_refused_without_allow_prod_and_nothing_is_built():
    def boom():
        raise AssertionError("client must not be built")

    r = finance_import_igig(ORG, client_factory=boom)
    assert r["status"] == "refused_prod" and not r["ok"]


def test_allow_prod_without_credentials_is_not_configured():
    r = finance_import_igig(ORG, allow_prod=True, client_factory=lambda: None)
    assert r["status"] == "not_configured"


def test_confirm_with_dry_run_is_a_contradiction_and_bad_org_is_an_error():
    assert finance_import_igig(ORG, dry_run=True, confirm=True, db=_db([]))["status"] == "refused_contradiction"
    assert finance_import_igig("nope", db=_db([]))["status"] == "error"


def test_dry_run_returns_the_reconciliation_and_writes_nothing():
    db = _db([_fat(1, "2026-08", "100.10"), _fat(2, "2026-08", "50.00"), _fat(3, "2026-09", "10.00")])
    r = finance_import_igig(ORG, db=db)
    assert r["status"] == "dry_run" and r["ok"]
    rows = {x["competencia"]: x for x in r["reconciliation"]["rows"]}
    assert rows["2026-08"]["before_numeric"] == "150.10" and rows["2026-08"]["after_cents"] == 15010
    assert db.table("fin_entries").select("*").execute().data in (None, [])


def test_mismatch_refuses_even_with_confirm_and_lists_rows():
    db = _db([_fat(1, "2026-08", "10.00"), _fat(2, "2026-08", "-5.00")])
    r = finance_import_igig(ORG, dry_run=False, confirm=True, db=db)
    assert r["status"] == "refused_reconciliation"
    assert r["reconciliation"]["mismatches"][0]["faturas_not_booked"] == [_fat(2, "2026-08", "0")["id"]]
    assert db.table("fin_entries").select("*").execute().data in (None, [])


def test_dry_run_false_without_confirm_only_plans():
    db = _db([_fat(1, "2026-08", "10.00")])
    assert finance_import_igig(ORG, dry_run=False, db=db)["status"] == "planned"
    assert db.table("fin_entries").select("*").execute().data in (None, [])


def test_confirm_writes_idempotently_and_verifies_totals():
    db = _db([_fat(1, "2026-08", "100.10"), _fat(2, "2026-09", "10.00")])
    r = finance_import_igig(ORG, dry_run=False, confirm=True, db=db)
    assert r["status"] == "imported", r
    assert r["written"]["created"] == 2 and r["stored_cents"] == {"2026-08": 10010, "2026-09": 1000}
    again = finance_import_igig(ORG, dry_run=False, confirm=True, db=db)
    assert again["status"] == "imported" and again["written"]["created"] == 0 and again["written"]["existing"] == 2
    assert len(db.table("fin_entries").select("*").execute().data) == 2
