"""Value-object invariants — Money never a float, FeeBreakdown never lies."""
from decimal import Decimal

import pytest

from noctusai_lib.integrations.payments.types import FeeBreakdown, Money


class TestMoney:
    def test_rejects_float_amount(self) -> None:
        with pytest.raises(TypeError):
            Money(29.90, "BRL")  # type: ignore[arg-type]

    def test_rejects_bool_amount(self) -> None:
        # bool is a subclass of int in Python — must not sneak through.
        with pytest.raises(TypeError):
            Money(True, "BRL")  # type: ignore[arg-type]

    def test_rejects_bad_currency(self) -> None:
        with pytest.raises(ValueError):
            Money(1000, "brl")  # lowercase — not a valid ISO code here
        with pytest.raises(ValueError):
            Money(1000, "R$")

    def test_add_same_currency(self) -> None:
        assert Money(100, "BRL") + Money(50, "BRL") == Money(150, "BRL")

    def test_add_mismatched_currency_raises(self) -> None:
        with pytest.raises(ValueError):
            Money(100, "BRL") + Money(50, "USD")

    def test_sub_same_currency(self) -> None:
        assert Money(150, "BRL") - Money(50, "BRL") == Money(100, "BRL")

    def test_from_decimal_reais_converts_to_cents(self) -> None:
        assert Money.from_decimal_reais(Decimal("150.00")) == Money(15000, "BRL")
        assert Money.from_decimal_reais(Decimal("29.99")) == Money(2999, "BRL")

    def test_from_decimal_reais_rejects_float(self) -> None:
        with pytest.raises(TypeError):
            Money.from_decimal_reais(29.90)  # type: ignore[arg-type]

    def test_to_decimal_round_trips(self) -> None:
        money = Money.from_decimal_reais(Decimal("42.50"))
        assert money.to_decimal() == Decimal("42.50")


class TestFeeBreakdown:
    def test_valid_breakdown(self) -> None:
        breakdown = FeeBreakdown(
            gross=Money(10_000, "BRL"), fee=Money(299, "BRL"), net=Money(9_701, "BRL")
        )
        assert breakdown.gross.amount_cents == breakdown.fee.amount_cents + breakdown.net.amount_cents

    def test_invariant_violation_raises(self) -> None:
        with pytest.raises(ValueError):
            FeeBreakdown(
                gross=Money(10_000, "BRL"),
                fee=Money(299, "BRL"),
                net=Money(9_999, "BRL"),  # fee + net != gross
            )

    def test_currency_mismatch_raises(self) -> None:
        with pytest.raises(ValueError):
            FeeBreakdown(
                gross=Money(10_000, "BRL"),
                fee=Money(299, "USD"),
                net=Money(9_701, "BRL"),
            )


class TestSubscriptionRequestTrialDays:
    def _req(self, trial_days):
        from noctusai_lib.integrations.payments.types import SubscriptionRequest

        return SubscriptionRequest(
            external_reference="org-1",
            customer_id_at_gateway="cus_1",
            price=Money(100, "BRL"),
            trial_days=trial_days,
        )

    def test_defaults_to_zero(self) -> None:
        from noctusai_lib.integrations.payments.types import SubscriptionRequest

        req = SubscriptionRequest(
            external_reference="org-1", customer_id_at_gateway="cus_1", price=Money(1, "BRL")
        )
        assert req.trial_days == 0

    def test_rejects_negative(self) -> None:
        with pytest.raises(ValueError):
            self._req(-1)

    def test_rejects_non_int(self) -> None:
        with pytest.raises(TypeError):
            self._req(True)
