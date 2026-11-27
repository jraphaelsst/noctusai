"""`atualizar_imovel` / `pode_atualizar_imovel` on the domain-shape adapters (Fake+Real parity, 2026-11-04)."""
from __future__ import annotations

import inspect
import json

import httpx
import pytest

from noctusai_lib.integrations.vista import VistaNotFound, VistaPermissionDenied
from noctusai_lib.integrations.vista.fake_adapter import FakeVistaAdapter
from noctusai_lib.integrations.vista.real import VistaRESTAdapter

KEY = "0123456789abcdef0123456789ab644c"
MISSING_401 = '{"status":401,"message":"Voc\\u00ea deve informar os dados em json no par\\u00e2metro \\"cadastro\\""}'


def test_fake_and_real_adapters_share_the_write_signatures() -> None:
    for name in ("atualizar_imovel", "pode_atualizar_imovel"):
        fake = list(inspect.signature(getattr(FakeVistaAdapter, name)).parameters)
        real = list(inspect.signature(getattr(VistaRESTAdapter, name)).parameters)
        assert fake == real, name


UPD = dict(motivo="proprietário confirmou", autor="NoctusAI", canal="WhatsApp")


@pytest.mark.asyncio
async def test_real_adapter_probes_non_mutatingly_and_writes_through_put_with_a_note(monkeypatch) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.method == "GET":
            return httpx.Response(200, json={"Codigo": "CA2830", "ObsVenda": ""})
        return httpx.Response(401, text=MISSING_401) if "cadastro" not in request.url.params else httpx.Response(200, json={"status": 200})

    transport = httpx.MockTransport(handler)
    real_async_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: real_async_client(*a, transport=transport, **{x: y for x, y in k.items() if x != "transport"}))
    adapter = VistaRESTAdapter(base_url="https://t-rest.vistahost.com.br", api_key=KEY)
    assert await adapter.pode_atualizar_imovel() is True
    probe = seen[-1]
    assert probe.method == "PUT" and "cadastro" not in probe.url.params and probe.url.path == "/imoveis/detalhes"
    linha = await adapter.atualizar_imovel("CA2830", {"ValorVenda": "1"}, **UPD)
    assert seen[-1].method == "PUT" and json.loads(seen[-1].url.params["cadastro"])["fields"]["ObsVenda"] == linha  # empty field => just our line
    assert await adapter.update_property_video_url("CA2830", "https://v/1", motivo="vídeo novo") is True
    assert json.loads(seen[-1].url.params["cadastro"])["fields"]["VideoDestaque"] == "https://v/1"  # the featured-video field, not Tour360
    with pytest.raises(ValueError):
        await adapter.update_property_video_url("CA2830", "https://v/1", motivo="")


@pytest.mark.asyncio
async def test_fake_adapter_records_updates_with_the_note_and_models_denial_unknown_code_and_read_failure() -> None:
    from noctusai_lib.domain.real_estate import Imovel

    fake = FakeVistaAdapter(imoveis={"CA1": Imovel(codigo="CA1")})
    fake.set_registro("CA1", {"ValorVenda": "900", "ObsVenda": "Cabeçalho\n10/10/26 X informa y. (Z)"})
    linha = await fake.atualizar_imovel("CA1", {"ValorVenda": "5"}, **UPD)
    [(cod, campos)] = fake.atualizacoes
    assert cod == "CA1" and campos["ObsVenda"].split("\n") == ["Cabeçalho", linha, "10/10/26 X informa y. (Z)"]
    with pytest.raises(ValueError):
        await fake.atualizar_imovel("CA1", {"ValorVenda": "5"}, motivo="", autor="a")
    with pytest.raises(VistaNotFound):
        await fake.atualizar_imovel("NOPE", {"ValorVenda": "5"}, **UPD)
    fake.falhar_leitura(VistaNotFound(404, "x", "/imoveis/detalhes"))
    n = len(fake.atualizacoes)
    with pytest.raises(VistaNotFound):
        await fake.atualizar_imovel("CA1", {"ValorVenda": "6"}, **UPD)
    assert len(fake.atualizacoes) == n  # a failed read writes nothing
    fake.falhar_leitura(None)
    fake.permitir_escrita(False)
    assert await fake.pode_atualizar_imovel() is False
    with pytest.raises(VistaPermissionDenied):
        await fake.atualizar_imovel("CA1", {"ValorVenda": "5"}, **UPD)
