"""FakeCepLookupAdapter behavioral tests — 100% offline, zero network."""

from noctusai_lib.integrations.cep import (
    CepEndereco,
    CepLookupAdapter,
    FakeCepLookupAdapter,
    get_cep_lookup_adapter,
)


def _sp() -> CepEndereco:
    return CepEndereco(
        cep="01310-100", cidade="Sao Paulo", uf="SP",
        logradouro="Avenida Paulista", bairro="Bela Vista",
    )


def test_fake_returns_registered_cep_regardless_of_punctuation() -> None:
    adapter = FakeCepLookupAdapter({"01310-100": _sp()})

    assert adapter.lookup("01310100") == _sp()
    assert adapter.lookup("01310-100") == _sp()


def test_fake_returns_none_for_unregistered_cep() -> None:
    adapter = FakeCepLookupAdapter()

    assert adapter.lookup("99999-999") is None


def test_fake_register_seeds_or_overrides_a_cep() -> None:
    adapter = FakeCepLookupAdapter()
    adapter.register("01310-100", _sp())

    assert adapter.lookup("01310-100") == _sp()


def test_fake_records_every_lookup_for_test_assertions() -> None:
    adapter = FakeCepLookupAdapter({"01310-100": _sp()})

    adapter.lookup("01310-100")
    adapter.lookup("01310-100")

    assert adapter.lookups == ["01310-100", "01310-100"]


def test_cep_endereco_is_frozen() -> None:
    import pytest

    endereco = _sp()
    with pytest.raises(AttributeError):
        endereco.cidade = "Outra"  # type: ignore[misc]


def test_fake_satisfies_the_cep_lookup_adapter_protocol() -> None:
    assert isinstance(FakeCepLookupAdapter(), CepLookupAdapter)


# ---- Factory ---------------------------------------------------------------


def test_factory_defaults_to_fake() -> None:
    adapter = get_cep_lookup_adapter()
    assert isinstance(adapter, FakeCepLookupAdapter)


def test_factory_returns_fake_when_live_is_false() -> None:
    adapter = get_cep_lookup_adapter(live=False)
    assert isinstance(adapter, FakeCepLookupAdapter)


def test_factory_forwards_kwargs_to_fake() -> None:
    adapter = get_cep_lookup_adapter(live=False, enderecos={"01310-100": _sp()})
    assert isinstance(adapter, FakeCepLookupAdapter)
    assert adapter.lookup("01310-100") == _sp()
