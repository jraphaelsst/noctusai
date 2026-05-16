"""Vista CRM integration tests — Fake + factory + normalizer round-trip.

The Real `VistaClient` HTTP behavior is already covered by the ERP
showcase router/service suites; this module covers the seed additions
made by `social-wiring-absorption` Wave 1:

- `FakeVistaClient` — config leniency, typed-error injection, call
  recording, signature parity with `VistaClient`.
- `make_vista_client` — Fake/Real routing, leniency preserved.
- **Validated-shape round-trip** — feed the Fake a real
  `/imoveis/detalhes`-shaped payload (the One Consultoria ONE10121
  shape from the validated workspace) and assert the *real*
  `vista_imovel_detalhes_to_showcase` normalizer produces the
  expected `ShowcaseImovelDetalhes` — proving the Fake exercises the
  same mapping code path as the Real client.

Network-free: the Fake never touches httpx or the filesystem.
"""
from __future__ import annotations

import pytest

from noctusai_lib.integrations.vista import (
    FakeVistaClient,
    VistaCallResult,
    VistaConfigError,
    VistaPermissionDenied,
    make_vista_client,
    vista_imovel_detalhes_to_showcase,
)
from noctusai_lib.integrations.vista.client import VistaClient


# ============================================================================
# FakeVistaClient
# ============================================================================


@pytest.mark.asyncio
async def test_fake_returns_seeded_payload() -> None:
    fake = FakeVistaClient(
        responses={"/imoveis/detalhes": {"Codigo": "ONE10121"}}
    )
    result = await fake.detalhes_imovel("ONE10121", fields=["Codigo"])
    assert isinstance(result, VistaCallResult)
    assert result.status == 200
    assert result.data == {"Codigo": "ONE10121"}
    assert fake.calls == [("/imoveis/detalhes", ["imovel", "key", "pesquisa"])]


@pytest.mark.asyncio
async def test_fake_empty_when_unseeded() -> None:
    fake = FakeVistaClient()
    result = await fake.listar_imoveis(fields=["Codigo"])
    assert result.data == {}
    assert result.status == 200


@pytest.mark.asyncio
async def test_fake_unconfigured_raises_config_error_at_call_time() -> None:
    fake = FakeVistaClient(configured=False)
    assert fake.configured is False
    with pytest.raises(VistaConfigError):
        await fake.detalhes_imovel("ONE1", fields=["Codigo"])


@pytest.mark.asyncio
async def test_fake_injects_typed_error() -> None:
    err = VistaPermissionDenied(401, "{}", "/clientes/listar")
    fake = FakeVistaClient(errors={"/clientes/listar": err})
    with pytest.raises(VistaPermissionDenied):
        await fake.listar_clientes(fields=["Codigo"])


@pytest.mark.asyncio
async def test_fake_probe_never_raises() -> None:
    fake = FakeVistaClient(
        errors={"/x": VistaPermissionDenied(401, "{}", "/x")}
    )
    row = await fake.probe("/x")
    assert row["endpoint"] == "/x"
    assert row["status"] == "error"
    assert row["http_status"] == 401


def test_fake_base_url_parity() -> None:
    fake = FakeVistaClient(base_url="https://t.example/")
    assert fake.base_url == "https://t.example"


# ============================================================================
# Factory
# ============================================================================


def test_factory_returns_fake_when_use_fake_true() -> None:
    client = make_vista_client(use_fake=True)
    assert isinstance(client, FakeVistaClient)


def test_factory_returns_real_when_use_fake_false() -> None:
    client = make_vista_client(use_fake=False, base_url="https://v", api_key="k")
    assert isinstance(client, VistaClient)
    assert client.configured is True


def test_factory_real_leniency_no_raise_without_credentials() -> None:
    # Leniency contract: missing creds must NOT raise at build time.
    client = make_vista_client(use_fake=False)
    assert isinstance(client, VistaClient)
    assert client.configured is False


def test_factory_pre_seeds_fake() -> None:
    client = make_vista_client(
        use_fake=True, fake_responses={"/imoveis/detalhes": {"Codigo": "X"}}
    )
    assert isinstance(client, FakeVistaClient)


# ============================================================================
# Validated-shape round-trip through the Fake
# ============================================================================


@pytest.mark.asyncio
async def test_fake_detalhes_round_trips_through_real_normalizer() -> None:
    """ONE10121-shaped detalhes payload (validated workspace shape) →
    Fake → real normalizer → expected ShowcaseImovelDetalhes."""
    detalhes_payload = {
        "Codigo": "ONE10121",
        "TituloSite": "Casa com 2 dormitórios para locação - Granja Viana - Cotia - SP",
        "Categoria": "Casa em Condomínio",
        "Finalidade": "Locação",
        "Cidade": "Cotia",
        "Bairro": "Granja Viana",
        "UF": "SP",  # per-tenant: oneconsu-rest exposes UF, not Estado
        "ValorLocacao": "4500,00",  # comma decimal — coercion path
        "AreaTotal": "180.00",
        "Dormitorios": "2",
        "BanheiroSocial": "2",  # Banheiros denied on this tenant
        "Caracteristicas": {"Piscina": "Sim", "Churrasqueira": "Sim"},
        "Corretor": {"103": {"Nome": "Fernanda"}},
    }
    fake = FakeVistaClient(responses={"/imoveis/detalhes": detalhes_payload})
    result = await fake.detalhes_imovel("ONE10121", fields=["Codigo"])

    showcase = vista_imovel_detalhes_to_showcase(result.data)
    assert showcase.codigo == "ONE10121"
    assert showcase.base.finalidade == "Locação"
    assert showcase.base.estado == "SP"  # UF fallback
    assert showcase.base.valor_locacao == 4500.0  # comma → dot
    assert showcase.base.banheiros == 2  # BanheiroSocial fallback
    assert showcase.base.corretor_nome == "Fernanda"  # dict-keyed Corretor
    assert showcase.caracteristicas == {"Piscina": "Sim", "Churrasqueira": "Sim"}
