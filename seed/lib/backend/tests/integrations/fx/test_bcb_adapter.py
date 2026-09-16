"""BcbPtaxAdapter tests — httpx client is MOCKED (external vendor SDK,
per the DI-test-seam carve-out; mirrors
`tests/integrations/google_maps/test_adapters.py`). Zero network calls;
response bodies below are the exact JSON captured from probing the live
Olinda API on 2026-09-16 (see `bcb_adapter.py` module docstring)."""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

import httpx
import pytest

from noctusai_lib.integrations.fx import (
    BcbPtaxAdapter,
    FxBulletinNotFoundError,
    FxRateAdapter,
    FxUpstreamError,
    get_fx_rate_adapter,
)


def _response(status_code: int, text: str) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    return resp


def test_get_ptax_parses_venda_rate_from_a_live_captured_body() -> None:
    body = (
        '{"@odata.context":"...","value":[{"cotacaoCompra":5.14840,'
        '"cotacaoVenda":5.14900,"dataHoraCotacao":"2026-09-15 13:09:19.199664"}]}'
    )
    client = MagicMock()
    client.get.return_value = _response(200, body)

    adapter = BcbPtaxAdapter(http_client=client)
    rate = adapter.get_ptax(date(2026, 9, 15))

    assert rate.rate == Decimal("5.14900")
    assert rate.quote_date == date(2026, 9, 15)


def test_get_ptax_builds_url_with_percent20_not_plus_for_orderby_space() -> None:
    """Regression guard for the BCB 400 confirmed live: `$orderby`'s
    space MUST be `%20`, never `+`."""
    client = MagicMock()
    client.get.return_value = _response(200, '{"value":[]}')
    # empty value -> FxBulletinNotFoundError, but we only care about the URL
    adapter = BcbPtaxAdapter(http_client=client)
    with pytest.raises(FxBulletinNotFoundError):
        adapter.get_ptax(date(2026, 9, 15))

    called_url = client.get.call_args[0][0]
    assert "%20desc" in called_url
    assert "+desc" not in called_url
    assert "CotacaoDolarPeriodo(dataInicial='09-05-2026',dataFinalCotacao='09-15-2026')" in called_url


def test_get_ptax_walks_back_window_covers_lookback_days() -> None:
    client = MagicMock()
    client.get.return_value = _response(200, '{"value":[]}')
    adapter = BcbPtaxAdapter(http_client=client, lookback_days=3)

    with pytest.raises(FxBulletinNotFoundError) as exc_info:
        adapter.get_ptax(date(2026, 9, 13))

    assert exc_info.value.lookback_days == 3
    called_url = client.get.call_args[0][0]
    assert "dataInicial='09-10-2026'" in called_url
    assert "dataFinalCotacao='09-13-2026'" in called_url


def test_get_ptax_raises_bulletin_not_found_on_empty_value() -> None:
    client = MagicMock()
    client.get.return_value = _response(200, '{"value":[]}')
    adapter = BcbPtaxAdapter(http_client=client)

    with pytest.raises(FxBulletinNotFoundError):
        adapter.get_ptax(date(2026, 9, 13))


def test_get_ptax_raises_upstream_error_on_non_200() -> None:
    client = MagicMock()
    client.get.return_value = _response(503, "backend overloaded")
    adapter = BcbPtaxAdapter(http_client=client)

    with pytest.raises(FxUpstreamError):
        adapter.get_ptax(date(2026, 9, 15))


def test_get_ptax_raises_upstream_error_on_non_json_body() -> None:
    client = MagicMock()
    client.get.return_value = _response(200, "not json")
    adapter = BcbPtaxAdapter(http_client=client)

    with pytest.raises(FxUpstreamError):
        adapter.get_ptax(date(2026, 9, 15))


def test_get_ptax_raises_upstream_error_on_unexpected_row_shape() -> None:
    client = MagicMock()
    client.get.return_value = _response(200, '{"value":[{"unexpected":"shape"}]}')
    adapter = BcbPtaxAdapter(http_client=client)

    with pytest.raises(FxUpstreamError):
        adapter.get_ptax(date(2026, 9, 15))


def test_get_ptax_wraps_httpx_transport_errors() -> None:
    client = MagicMock()
    client.get.side_effect = httpx.ConnectError("dns failed")
    adapter = BcbPtaxAdapter(http_client=client)

    with pytest.raises(FxUpstreamError):
        adapter.get_ptax(date(2026, 9, 15))


def test_get_ptax_caches_repeat_lookups_for_the_same_date() -> None:
    """PTAX for a past date is immutable — a repeat lookup must not
    re-hit the network."""
    body = (
        '{"value":[{"cotacaoCompra":5.14840,"cotacaoVenda":5.14900,'
        '"dataHoraCotacao":"2026-09-15 13:09:19.199664"}]}'
    )
    client = MagicMock()
    client.get.return_value = _response(200, body)
    adapter = BcbPtaxAdapter(http_client=client)

    first = adapter.get_ptax(date(2026, 9, 15))
    second = adapter.get_ptax(date(2026, 9, 15))

    assert first == second
    client.get.assert_called_once()


def test_get_ptax_caches_under_the_walked_back_bulletin_date_too() -> None:
    """A weekend lookup that resolves to Friday's bulletin should also
    satisfy a direct Friday lookup without a second network call."""
    body = (
        '{"value":[{"cotacaoCompra":5.09120,"cotacaoVenda":5.09180,'
        '"dataHoraCotacao":"2026-09-11 13:07:22.532196"}]}'
    )
    client = MagicMock()
    client.get.return_value = _response(200, body)
    adapter = BcbPtaxAdapter(http_client=client)

    weekend_result = adapter.get_ptax(date(2026, 9, 13))  # Sunday
    friday_result = adapter.get_ptax(date(2026, 9, 11))  # Friday direct

    assert weekend_result == friday_result
    client.get.assert_called_once()


def test_adapter_closes_self_constructed_http_client_on_exception() -> None:
    fake_internal_client = MagicMock()
    fake_internal_client.get.side_effect = httpx.ConnectError("dns failed")

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(httpx, "Client", lambda **_: fake_internal_client)

        adapter = BcbPtaxAdapter(http_client=None)
        with pytest.raises(FxUpstreamError):
            adapter.get_ptax(date(2026, 9, 15))

    fake_internal_client.close.assert_called_once()


def test_bcb_adapter_satisfies_the_fx_rate_adapter_protocol() -> None:
    assert isinstance(BcbPtaxAdapter(), FxRateAdapter)


# ---- Factory ---------------------------------------------------------------


def test_factory_returns_bcb_adapter_when_live_is_true() -> None:
    adapter = get_fx_rate_adapter(live=True)
    assert isinstance(adapter, BcbPtaxAdapter)
