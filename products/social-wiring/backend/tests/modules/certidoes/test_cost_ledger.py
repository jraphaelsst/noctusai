"""`app.modules.certidoes.cost_ledger` — InfoSimples spend booking.

Pure unit tests: `MockSupabaseClient(schema="public")` stands in for
`get_core_client()` (validates columns against the migration-derived
`public.cost_ledger` schema — 046_permissions_fx_cost_ledger.sql — so a
typo'd column here fails the test, not production).
"""
from __future__ import annotations

from noctusai_lib.testing import MockSupabaseClient

from app.modules.certidoes.cost_ledger import (
    CATEGORY,
    REFERENCE_TYPE,
    _extract_price,
    book_infosimples_cost,
)

ORG = "11111111-1111-4111-8111-111111111111"


def _db() -> MockSupabaseClient:
    return MockSupabaseClient(schema="public")


class TestExtractPrice:
    def test_header_price_field(self):
        assert _extract_price({"header": {"price": "1.23"}}) is not None
        assert str(_extract_price({"header": {"price": "1.23"}})) == "1.23"

    def test_falls_back_to_consumed_price(self):
        assert str(_extract_price({"header": {"consumed_price": 2.5}})) == "2.5"

    def test_falls_back_to_custo(self):
        assert str(_extract_price({"header": {"custo": "0.90"}})) == "0.90"

    def test_prefers_first_match_in_declared_order(self):
        # header.price wins over header.consumed_price when both present.
        assert str(
            _extract_price({"header": {"price": "1.00", "consumed_price": "9.00"}})
        ) == "1.00"

    def test_none_when_no_recognized_field(self):
        assert _extract_price({"header": {"api_version": "2"}}) is None

    def test_none_when_response_is_not_a_dict(self):
        assert _extract_price(None) is None
        assert _extract_price([]) is None

    def test_none_when_price_not_numeric(self):
        assert _extract_price({"header": {"price": "grátis"}}) is None

    def test_none_when_price_negative(self):
        assert _extract_price({"header": {"price": "-1.00"}}) is None


class TestBookInfosimplesCost:
    def test_books_a_brl_row_matching_the_cost_ledger_check_constraint(self):
        db = _db()
        booked = book_infosimples_cost(
            db,
            org_id=ORG,
            tipo="cnd_federal",
            raw_response={"header": {"price": "1.50"}},
            reference_id="resultado-001",
        )
        assert booked is True
        rows = db.table("cost_ledger").select("*").execute().data
        assert len(rows) == 1
        row = rows[0]
        assert row["org_id"] == ORG
        assert row["category"] == CATEGORY == "infosimples"
        assert row["reference_type"] == REFERENCE_TYPE == "certidao_consulta"
        assert row["reference_id"] == "resultado-001"
        assert row["step"] == "certidoes.cnd_federal"
        assert row["currency"] == "BRL"
        assert row["amount_native"] == "1.50"
        # The CHECK constraint's BRL branch: amount_brl == amount_native,
        # fx_pending false, fx_rate/fx_quote_date both absent (NULL).
        assert row["amount_brl"] == "1.50"
        assert row["fx_pending"] is False
        assert row.get("fx_rate") is None
        assert row.get("fx_quote_date") is None

    def test_skips_when_org_id_missing(self):
        db = _db()
        booked = book_infosimples_cost(
            db,
            org_id=None,
            tipo="cnd_federal",
            raw_response={"header": {"price": "1.50"}},
            reference_id="resultado-002",
        )
        assert booked is False
        assert db.table("cost_ledger").select("*").execute().data == []

    def test_skips_when_no_price_extractable_never_invents_one(self):
        db = _db()
        booked = book_infosimples_cost(
            db,
            org_id=ORG,
            tipo="cnd_federal",
            raw_response={"header": {"api_version": "2"}},
            reference_id="resultado-003",
        )
        assert booked is False
        assert db.table("cost_ledger").select("*").execute().data == []

    def test_never_raises_when_insert_fails(self):
        class _BoomDb:
            def table(self, name):
                raise RuntimeError("boom")

        booked = book_infosimples_cost(
            _BoomDb(),
            org_id=ORG,
            tipo="cnd_federal",
            raw_response={"header": {"price": "1.50"}},
            reference_id="resultado-004",
        )
        assert booked is False


class TestBillableFlag:
    """Real InfoSimples responses carry `header.billable` beside the price
    (verified on 215 stored responses) — an unbilled call costs nothing."""

    def test_an_unbilled_call_books_nothing(self):
        db = _db()
        booked = book_infosimples_cost(
            db,
            org_id=ORG,
            tipo="trt2_digital",
            raw_response={"header": {"price": "0.24", "billable": False}},
            reference_id="resultado-nb",
        )
        assert booked is False
        assert db.table("cost_ledger").select("*").execute().data == []

    def test_a_billed_call_books_the_header_price(self):
        db = _db()
        booked = book_infosimples_cost(
            db,
            org_id=ORG,
            tipo="trt2_digital",
            raw_response={"header": {"price": "0.24", "billable": True}},
            reference_id="resultado-b",
        )
        assert booked is True
        rows = db.table("cost_ledger").select("*").execute().data
        assert len(rows) == 1 and str(rows[0]["amount_brl"]) == "0.24"
