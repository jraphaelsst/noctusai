"""FakeFxRateAdapter behavioral tests — 100% offline, zero network."""

from datetime import date, datetime
from decimal import Decimal

import pytest

from noctusai_lib.integrations.fx import (
    FakeFxRateAdapter,
    FxBulletinNotFoundError,
    FxRateAdapter,
    PtaxRate,
    get_fx_rate_adapter,
)


def test_fake_returns_exact_rate_for_a_bulletin_date() -> None:
    adapter = FakeFxRateAdapter({date(2026, 9, 15): Decimal("5.14900")})

    result = adapter.get_ptax(date(2026, 9, 15))

    assert result.rate == Decimal("5.14900")
    assert result.quote_date == date(2026, 9, 15)
    assert isinstance(result.bulletin_at, datetime)


def test_fake_walks_back_over_a_weekend_gap() -> None:
    """2026-09-12 was a Saturday with no bulletin; the last published
    bulletin was Friday 2026-09-11 — mirrors the real BCB calendar."""
    adapter = FakeFxRateAdapter({date(2026, 9, 11): Decimal("5.09180")})

    result = adapter.get_ptax(date(2026, 9, 13))  # Sunday

    assert result.quote_date == date(2026, 9, 11)
    assert result.rate == Decimal("5.09180")


def test_fake_raises_typed_error_when_nothing_in_lookback_window() -> None:
    adapter = FakeFxRateAdapter({}, lookback_days=3)

    with pytest.raises(FxBulletinNotFoundError) as exc_info:
        adapter.get_ptax(date(2026, 9, 13))

    assert exc_info.value.requested_date == date(2026, 9, 13)
    assert exc_info.value.lookback_days == 3


def test_fake_never_walks_past_the_lookback_window() -> None:
    """A bulletin 4 days back must NOT satisfy a 3-day lookback window."""
    adapter = FakeFxRateAdapter({date(2026, 9, 9): Decimal("5.0")}, lookback_days=3)

    with pytest.raises(FxBulletinNotFoundError):
        adapter.get_ptax(date(2026, 9, 13))


def test_fake_records_every_lookup_for_test_assertions() -> None:
    adapter = FakeFxRateAdapter({date(2026, 9, 15): Decimal("5.0")})

    adapter.get_ptax(date(2026, 9, 15))
    adapter.get_ptax(date(2026, 9, 15))

    assert adapter.lookups == [date(2026, 9, 15), date(2026, 9, 15)]


def test_fake_set_rate_seeds_or_overrides_a_bulletin() -> None:
    adapter = FakeFxRateAdapter()
    adapter.set_rate(date(2026, 9, 15), Decimal("5.20000"))

    assert adapter.get_ptax(date(2026, 9, 15)).rate == Decimal("5.20000")


def test_fake_rate_is_a_decimal_never_a_float() -> None:
    adapter = FakeFxRateAdapter({date(2026, 9, 15): Decimal("5.14900")})

    assert isinstance(adapter.get_ptax(date(2026, 9, 15)).rate, Decimal)


def test_fake_satisfies_the_fx_rate_adapter_protocol() -> None:
    assert isinstance(FakeFxRateAdapter(), FxRateAdapter)


def test_ptax_rate_is_frozen() -> None:
    rate = PtaxRate(
        rate=Decimal("5.0"),
        quote_date=date(2026, 9, 15),
        bulletin_at=datetime(2026, 9, 15, 13, 0),
        source="fake-ptax",
    )
    with pytest.raises(AttributeError):
        rate.rate = Decimal("6.0")  # type: ignore[misc]


# ---- Factory ---------------------------------------------------------------


def test_factory_defaults_to_fake() -> None:
    adapter = get_fx_rate_adapter()
    assert isinstance(adapter, FakeFxRateAdapter)


def test_factory_returns_fake_when_live_is_false() -> None:
    adapter = get_fx_rate_adapter(live=False)
    assert isinstance(adapter, FakeFxRateAdapter)


def test_factory_forwards_kwargs_to_fake() -> None:
    adapter = get_fx_rate_adapter(
        live=False, bulletins={date(2026, 9, 15): Decimal("5.5")}
    )
    assert isinstance(adapter, FakeFxRateAdapter)
    assert adapter.get_ptax(date(2026, 9, 15)).rate == Decimal("5.5")
