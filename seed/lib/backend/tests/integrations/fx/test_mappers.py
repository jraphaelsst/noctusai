"""Pure-function mapper tests — fixtures are JSON bodies CAPTURED from a
live BCB Olinda probe on 2026-09-16 (see `bcb_adapter.py` module
docstring); no network call happens in this test file."""

from datetime import date, datetime
from decimal import Decimal

import pytest

from noctusai_lib.integrations.fx.mappers import format_bcb_date, parse_ptax_response


def test_format_bcb_date_uses_mm_dd_yyyy() -> None:
    assert format_bcb_date(date(2026, 9, 15)) == "09-15-2026"


def test_parse_ptax_response_extracts_venda_rate_and_bulletin_date() -> None:
    # Captured verbatim from CotacaoDolarDia(dataCotacao='09-15-2026').
    payload = {
        "@odata.context": "https://was-p.bcnet.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata$metadata#_CotacaoDolarDia",
        "value": [
            {
                "cotacaoCompra": Decimal("5.14840"),
                "cotacaoVenda": Decimal("5.14900"),
                "dataHoraCotacao": "2026-09-15 13:09:19.199664",
            }
        ],
    }

    rate = parse_ptax_response(payload)

    assert rate is not None
    assert rate.rate == Decimal("5.14900")
    assert rate.quote_date == date(2026, 9, 15)
    assert rate.bulletin_at == datetime(2026, 9, 15, 13, 9, 19, 199664)
    assert rate.source == "bcb-ptax-olinda"


def test_parse_ptax_response_returns_none_for_empty_value() -> None:
    # Captured verbatim from a Saturday date (no bulletin published).
    payload = {
        "@odata.context": "https://was-p.bcnet.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata$metadata#_CotacaoDolarDia",
        "value": [],
    }

    assert parse_ptax_response(payload) is None


def test_parse_ptax_response_coerces_a_float_rate_to_decimal() -> None:
    """Defensive path: a caller that used `response.json()` instead of
    `json.loads(text, parse_float=Decimal)` would hand this function a
    float. It must still produce a Decimal, never propagate the float."""
    payload = {"value": [{"cotacaoVenda": 5.149, "dataHoraCotacao": "2026-09-15 13:09:19.199664"}]}

    rate = parse_ptax_response(payload)

    assert rate is not None
    assert isinstance(rate.rate, Decimal)


def test_parse_ptax_response_short_microsecond_digits_still_parse() -> None:
    """BCB emits a variable number of fractional-second digits (observed
    both `.199664` and `.70012` — 6 vs 5 digits) — strptime's %f must
    handle both."""
    payload = {
        "value": [
            {"cotacaoVenda": Decimal("5.11490"), "dataHoraCotacao": "2026-09-10 13:09:28.70012"}
        ]
    }

    rate = parse_ptax_response(payload)

    assert rate is not None
    # "70012" is a fractional-seconds string (0.70012s), so strptime's
    # %f right-pads it to microseconds: 700120, not 70012.
    assert rate.bulletin_at == datetime(2026, 9, 10, 13, 9, 28, 700120)


def test_parse_ptax_response_raises_keyerror_on_missing_value_key() -> None:
    with pytest.raises(KeyError):
        parse_ptax_response({"@odata.context": "..."})


def test_parse_ptax_response_raises_keyerror_on_missing_cotacao_venda() -> None:
    with pytest.raises(KeyError):
        parse_ptax_response({"value": [{"dataHoraCotacao": "2026-09-15 13:09:19.199664"}]})


def test_parse_ptax_response_raises_valueerror_on_bad_timestamp() -> None:
    with pytest.raises(ValueError):
        parse_ptax_response({"value": [{"cotacaoVenda": Decimal("5.0"), "dataHoraCotacao": "not-a-date"}]})
