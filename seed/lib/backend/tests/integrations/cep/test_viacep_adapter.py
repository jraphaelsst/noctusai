"""ViaCepAdapter tests — httpx client is MOCKED (external vendor SDK, per
the DI-test-seam carve-out; mirrors `tests/integrations/fx/test_bcb_
adapter.py`). Zero network calls; response bodies below match ViaCEP's/
BrasilAPI's own documented shapes."""

from unittest.mock import MagicMock

import httpx
import pytest

from noctusai_lib.integrations.cep import CepLookupAdapter, get_cep_lookup_adapter
from noctusai_lib.integrations.cep.viacep_adapter import ViaCepAdapter


def _response(status_code: int, json_body: dict | None = None, text: str = "") -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    if json_body is not None:
        resp.json.return_value = json_body
    else:
        resp.json.side_effect = ValueError("no json")
    resp.text = text
    return resp


def test_lookup_resolves_via_viacep() -> None:
    client = MagicMock()
    client.get.return_value = _response(
        200,
        {
            "cep": "01310-100", "logradouro": "Avenida Paulista",
            "bairro": "Bela Vista", "localidade": "São Paulo", "uf": "SP",
        },
    )
    adapter = ViaCepAdapter(http_client=client)

    resultado = adapter.lookup("01310100")

    assert resultado is not None
    assert resultado.cep == "01310-100"
    assert resultado.cidade == "São Paulo"
    assert resultado.uf == "SP"
    assert resultado.logradouro == "Avenida Paulista"
    client.get.assert_called_once_with("https://viacep.com.br/ws/01310100/json/")


def test_lookup_falls_back_to_brasilapi_when_viacep_reports_erro() -> None:
    client = MagicMock()
    client.get.side_effect = [
        _response(200, {"erro": True}),
        _response(
            200,
            {
                "cep": "01310-100", "state": "SP", "city": "São Paulo",
                "street": "Avenida Paulista", "neighborhood": "Bela Vista",
            },
        ),
    ]
    adapter = ViaCepAdapter(http_client=client)

    resultado = adapter.lookup("01310-100")

    assert resultado is not None
    assert resultado.cidade == "São Paulo"
    assert resultado.uf == "SP"
    assert client.get.call_count == 2
    assert "brasilapi.com.br" in client.get.call_args_list[1][0][0]


def test_lookup_falls_back_to_brasilapi_when_viacep_transport_fails() -> None:
    client = MagicMock()
    client.get.side_effect = [
        httpx.ConnectError("dns failed"),
        _response(200, {"state": "RJ", "city": "Rio de Janeiro"}),
    ]
    adapter = ViaCepAdapter(http_client=client)

    resultado = adapter.lookup("20040-020")

    assert resultado is not None
    assert resultado.uf == "RJ"


def test_lookup_returns_none_when_brasilapi_404s_too() -> None:
    client = MagicMock()
    client.get.side_effect = [
        _response(200, {"erro": True}),
        _response(404),
    ]
    adapter = ViaCepAdapter(http_client=client)

    assert adapter.lookup("00000-000") is None


def test_lookup_returns_none_on_malformed_cep() -> None:
    client = MagicMock()
    adapter = ViaCepAdapter(http_client=client)

    assert adapter.lookup("123") is None
    client.get.assert_not_called()


def test_lookup_returns_none_when_both_services_return_non_json() -> None:
    client = MagicMock()
    client.get.side_effect = [_response(200, None), _response(200, None)]
    adapter = ViaCepAdapter(http_client=client)

    assert adapter.lookup("01310-100") is None


def test_lookup_returns_none_on_non_200_from_viacep_then_no_brasilapi_record() -> None:
    client = MagicMock()
    client.get.side_effect = [_response(503, text="down"), _response(404)]
    adapter = ViaCepAdapter(http_client=client)

    assert adapter.lookup("01310-100") is None


def test_lookup_returns_none_when_viacep_response_missing_cidade_uf() -> None:
    client = MagicMock()
    client.get.side_effect = [
        _response(200, {"logradouro": "Rua X"}),
        _response(404),
    ]
    adapter = ViaCepAdapter(http_client=client)

    assert adapter.lookup("01310-100") is None


def test_adapter_closes_self_constructed_http_client() -> None:
    fake_internal_client = MagicMock()
    fake_internal_client.get.return_value = _response(200, {"erro": True})

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(httpx, "Client", lambda **_: fake_internal_client)
        adapter = ViaCepAdapter(http_client=None)
        adapter.lookup("01310-100")

    assert fake_internal_client.close.call_count == 2  # ViaCEP + BrasilAPI


def test_viacep_adapter_satisfies_the_cep_lookup_adapter_protocol() -> None:
    assert isinstance(ViaCepAdapter(), CepLookupAdapter)


# ---- Factory ---------------------------------------------------------------


def test_factory_returns_viacep_adapter_when_live_is_true() -> None:
    adapter = get_cep_lookup_adapter(live=True)
    assert isinstance(adapter, ViaCepAdapter)
