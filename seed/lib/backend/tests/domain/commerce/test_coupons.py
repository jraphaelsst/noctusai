"""Coupons: integer-cents math, validity window, usage cap, uniqueness."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from noctusai_lib.domain.commerce import CommerceError, coupons
from noctusai_lib.domain.commerce.coupons import compute_discount
from noctusai_lib.primitives.exceptions import NotFoundError

from .conftest import ORG_A, ORG_B

NOW = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)


def make(db, org=ORG_A, **over):
    data = {"code": "NATAL10", "kind": "percent", "value": 10, **over}
    return coupons.create_coupon(db, org, data)


class TestMath:
    @pytest.mark.parametrize(
        "kind,value,subtotal,expected",
        [
            ("percent", 10, 4700, 470),
            ("percent", 33, 999, 329),       # floor: 329.67 -> 329, never rounds in the buyer's disfavour of the shop
            ("percent", 100, 500, 500),
            ("percent", 1, 99, 0),
            ("fixed", 1000, 4700, 1000),
            ("fixed", 9999, 4700, 4700),     # capped at the subtotal
        ],
    )
    def test_discount_is_integer_cents(self, kind, value, subtotal, expected):
        got = compute_discount(kind, value, subtotal)
        assert got == expected and isinstance(got, int)

    def test_unknown_kind_is_refused(self):
        with pytest.raises(ValueError):
            compute_discount("bogo", 1, 100)


class TestCheck:
    def test_percent_and_fixed_discounts(self, db):
        make(db, code="P10", kind="percent", value=10)
        make(db, code="F500", kind="fixed", value=500)
        _, d, err = coupons.check_coupon(db, ORG_A, "p10", 10000, at=NOW)  # case-insensitive
        assert (d, err) == (1000, None)
        _, d, err = coupons.check_coupon(db, ORG_A, "F500", 10000, at=NOW)
        assert (d, err) == (500, None)

    def test_unknown_inactive_and_foreign_org_codes(self, db):
        make(db, code="OFF", active=False)
        make(db, org=ORG_B, code="THEIRS")
        assert coupons.check_coupon(db, ORG_A, "NOPE", 1000, at=NOW)[2] == coupons.NAO_ENCONTRADO
        assert coupons.check_coupon(db, ORG_A, "OFF", 1000, at=NOW)[2] == coupons.INATIVO
        assert coupons.check_coupon(db, ORG_A, "THEIRS", 1000, at=NOW)[2] == coupons.NAO_ENCONTRADO

    def test_validity_window(self, db):
        make(db, code="FUTURE", starts_at=NOW + timedelta(days=1))
        make(db, code="PAST", ends_at=NOW - timedelta(seconds=1))
        make(db, code="LIVE", starts_at=NOW - timedelta(days=1), ends_at=NOW + timedelta(days=1))
        assert coupons.check_coupon(db, ORG_A, "FUTURE", 1000, at=NOW)[2] == coupons.AINDA_NAO_VALE
        assert coupons.check_coupon(db, ORG_A, "PAST", 1000, at=NOW)[2] == coupons.EXPIRADO
        assert coupons.check_coupon(db, ORG_A, "LIVE", 1000, at=NOW)[2] is None

    def test_the_window_end_is_exclusive(self, db):
        make(db, code="EDGE", ends_at=NOW)
        assert coupons.check_coupon(db, ORG_A, "EDGE", 1000, at=NOW)[2] == coupons.EXPIRADO

    def test_usage_cap(self, db):
        c = make(db, code="ONCE", max_uses=1)
        assert coupons.check_coupon(db, ORG_A, "ONCE", 1000, at=NOW)[2] is None
        assert coupons.reserve_use(db, ORG_A, c) is True
        assert coupons.check_coupon(db, ORG_A, "ONCE", 1000, at=NOW)[2] == coupons.ESGOTADO

    def test_a_coupon_that_zeroes_the_total_is_refused(self, db):
        make(db, code="FREE", kind="percent", value=100)
        coupon, d, err = coupons.check_coupon(db, ORG_A, "FREE", 1000, at=NOW)
        assert (coupon, d, err) == (None, 0, coupons.TOTAL_ZERO)


class TestUsage:
    def test_reserve_is_capped_and_release_gives_it_back(self, db):
        c = make(db, code="TWO", max_uses=2)
        assert coupons.reserve_use(db, ORG_A, c) and coupons.reserve_use(db, ORG_A, c)
        assert coupons.reserve_use(db, ORG_A, c) is False
        coupons.release_use(db, ORG_A, c)
        assert coupons.reserve_use(db, ORG_A, c) is True
        assert db.table("commerce_coupons").select("*").execute().data[0]["uses_count"] == 2

    def test_stale_snapshot_still_respects_the_cap(self, db):
        c = make(db, code="ONE", max_uses=1)
        stale = dict(c)  # uses_count 0, as a quote read it
        assert coupons.reserve_use(db, ORG_A, c)
        assert coupons.reserve_use(db, ORG_A, stale) is False  # re-reads, sees the cap

    def test_release_never_goes_below_zero(self, db):
        c = make(db, code="Z")
        coupons.release_use(db, ORG_A, c)
        assert db.table("commerce_coupons").select("*").execute().data[0]["uses_count"] == 0


class TestCrud:
    def test_code_is_stored_uppercase_and_unique_per_org_case_insensitively(self, db):
        c = make(db, code="Natal10")
        assert c["code"] == "NATAL10"
        with pytest.raises(CommerceError) as exc:
            make(db, code="natal10")
        assert exc.value.status_code == 409
        assert make(db, org=ORG_B, code="natal10")["code"] == "NATAL10"

    def test_update_validates_the_percent_range_against_the_merged_row(self, db):
        c = make(db, code="PC", kind="percent", value=10)
        with pytest.raises(CommerceError):
            coupons.update_coupon(db, ORG_A, c["id"], {"value": 150})
        assert coupons.update_coupon(db, ORG_A, c["id"], {"kind": "fixed", "value": 150})["kind"] == "fixed"

    def test_update_to_another_coupons_code_conflicts(self, db):
        make(db, code="A1")
        b = make(db, code="B1")
        with pytest.raises(CommerceError):
            coupons.update_coupon(db, ORG_A, b["id"], {"code": "a1"})

    def test_delete_and_cross_org_404(self, db):
        c = make(db)
        with pytest.raises(NotFoundError):
            coupons.delete_coupon(db, ORG_B, c["id"])
        coupons.delete_coupon(db, ORG_A, c["id"])
        assert coupons.list_coupons(db, ORG_A) == []
