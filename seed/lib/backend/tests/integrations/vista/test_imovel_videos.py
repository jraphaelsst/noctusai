"""`list_imovel_videos` — the read-only `Video` relation of `/imoveis/detalhes` (project `julia-videos-prontos-youtube`, S3).

Vista keeps a listing's videos in the `Video` relation, NOT in the root fields (the imóveis sync never fetches it). The relation
arrives dict-keyed by video code (the `Foto` shape) or as a list; `parse_imovel_videos` normalises both and orders by `VideoCodigo`
(numeric), then arrival -- so a consumer's "first video" never depends on dict key order. Unlike `list_imovel_fotos`, an
unpublished / unknown code is NOT folded into `[]`: `VistaRecordUnpublished` propagates (its `payload_keys` tell an unpublished
record -- the `Corretor` stub -- from a code that does not exist), because an importer must count them apart from "no video".
"""
from __future__ import annotations

import inspect
import json

import httpx
import pytest

from noctusai_lib.domain.real_estate import ImovelVideo, parse_imovel_videos
from noctusai_lib.integrations.vista import FakeVistaAdapter, VistaCRMAdapter, VistaRecordUnpublished, VistaRESTAdapter

AMOSTRA = {"Codigo": "CA0001", "VideoCodigo": "7", "Video": "9cgV72Lq9gs", "Tipo": "youtube", "Destaque": "Nao",
           "ExibirNoSite": "Sim", "Data": "2025-08-01", "Descricao": "Tour", "DescricaoWeb": ""}


class TestParse:
    def test_the_live_sample_shape(self):
        [v] = parse_imovel_videos({"7": AMOSTRA})
        assert v == ImovelVideo(codigo="7", video="9cgV72Lq9gs", tipo="youtube", destaque=False, exibir_no_site=True,
                                data="2025-08-01", descricao="Tour", descricao_web=None)

    def test_dict_and_list_shapes_order_by_video_codigo_numerically(self):
        raw = {"10": {**AMOSTRA, "VideoCodigo": "10", "Video": "b"}, "9": {**AMOSTRA, "VideoCodigo": "9", "Video": "a"}}
        assert [v.video for v in parse_imovel_videos(raw)] == ["a", "b"]
        assert [v.video for v in parse_imovel_videos(list(raw.values()))] == ["a", "b"]

    def test_destaque_is_a_flag_not_an_order(self):
        raw = [{**AMOSTRA, "VideoCodigo": "1", "Video": "a"}, {**AMOSTRA, "VideoCodigo": "2", "Video": "b", "Destaque": "Sim"}]
        assert [(v.video, v.destaque) for v in parse_imovel_videos(raw)] == [("a", False), ("b", True)]

    def test_entries_without_a_value_and_garbage_are_dropped(self):
        assert parse_imovel_videos({"1": {**AMOSTRA, "Video": ""}, "2": "x"}) == []
        assert parse_imovel_videos(None) == [] and parse_imovel_videos("") == []

    def test_exibir_site_is_the_fallback_flag(self):
        [v] = parse_imovel_videos([{"VideoCodigo": "1", "Video": "a", "ExibirSite": "Nao"}])
        assert v.exibir_no_site is False


class TestFake:
    @pytest.mark.asyncio
    async def test_round_trip_through_the_parser(self):
        fake = FakeVistaAdapter()
        fake.add_imovel_videos("CA0001", {"7": AMOSTRA})
        assert [v.video for v in await fake.list_imovel_videos("CA0001")] == ["9cgV72Lq9gs"]
        assert await fake.list_imovel_videos("CA9999") == []

    @pytest.mark.asyncio
    async def test_a_seeded_error_is_raised(self):
        fake = FakeVistaAdapter()
        fake.falhar_videos("CA0002", VistaRecordUnpublished("CA0002", "/imoveis/detalhes", ["Corretor"]))
        with pytest.raises(VistaRecordUnpublished):
            await fake.list_imovel_videos("CA0002")


class TestReal:
    def test_is_async_and_on_the_protocol(self):
        assert inspect.iscoroutinefunction(VistaRESTAdapter.list_imovel_videos)
        assert "list_imovel_videos" in vars(VistaCRMAdapter)

    @pytest.mark.asyncio
    async def test_invalid_code_short_circuits_without_network(self):
        assert await VistaRESTAdapter(base_url="https://vista.test", api_key="K").list_imovel_videos("not_a_code") == []

    @pytest.mark.asyncio
    async def test_asks_detalhes_for_the_video_relation_and_parses_it(self, monkeypatch):
        vistos: list[httpx.Request] = []
        _wire(monkeypatch, vistos, {"Codigo": "CA0001", "Video": {"7": AMOSTRA}})
        [v] = await VistaRESTAdapter(base_url="https://t-rest.vistahost.com.br", api_key=KEY).list_imovel_videos("CA0001")
        assert v.video == "9cgV72Lq9gs"
        [req] = vistos
        assert req.method == "GET" and req.url.path == "/imoveis/detalhes" and req.url.params["imovel"] == "CA0001"
        fields = json.loads(req.url.params["pesquisa"])["fields"]
        assert fields[0] == "Codigo"
        video = next(f["Video"] for f in fields if isinstance(f, dict) and "Video" in f)
        assert {"VideoCodigo", "Video", "Tipo", "Destaque"} <= set(video)
        assert any(isinstance(f, dict) and "Corretor" in f for f in fields)  # the unpublished-vs-unknown discriminator

    @pytest.mark.asyncio
    @pytest.mark.parametrize("corpo,chaves", [([], []), ({"Corretor": {"1": {"Codigo": "1"}}}, ["Corretor"])])
    async def test_an_unpublished_or_unknown_code_propagates(self, monkeypatch, corpo, chaves):
        _wire(monkeypatch, [], corpo)
        with pytest.raises(VistaRecordUnpublished) as exc:
            await VistaRESTAdapter(base_url="https://t-rest.vistahost.com.br", api_key=KEY).list_imovel_videos("CA0001")
        assert exc.value.payload_keys == chaves


KEY = "0123456789abcdef0123456789ab644c"


def _wire(monkeypatch, vistos: list, corpo) -> None:
    """httpx (a third-party library, not our code) answers from a MockTransport -- the precedent of `test_adapter_write.py`."""
    def handler(request: httpx.Request) -> httpx.Response:
        vistos.append(request)
        return httpx.Response(200, json=corpo)

    transport = httpx.MockTransport(handler)
    real_async_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: real_async_client(*a, transport=transport, **{x: y for x, y in k.items() if x != "transport"}))
