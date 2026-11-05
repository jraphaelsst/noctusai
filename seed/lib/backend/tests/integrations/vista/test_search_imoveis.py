"""`search_imoveis` -- the filtered catalog read on the `VistaCRMAdapter` seam (Julia live catalog, 2026-11).

Fake: the Vista filter grammar evaluated in memory. Real: pagination, concurrency-bounded page walk, `detalhes`
enrichment and the empty-match / error contract, network-free via `httpx.MockTransport` injected through the
adapter's own `_client()` seam (a subclass supplies the client; nothing of ours is patched)."""
from __future__ import annotations

import asyncio
import json
from datetime import date

import httpx
import pytest

from noctusai_lib.domain.real_estate import Imovel
from noctusai_lib.integrations.vista import FakeVistaAdapter, VistaRESTAdapter
from noctusai_lib.integrations.vista.client import VistaClient, VistaPermissionDenied


def _fake() -> FakeVistaAdapter:
    f = FakeVistaAdapter()
    for codigo, status, bairro, venda, dorm, vagas, cat, pub, dia in [
        ("A1", "Venda", "Granja Viana", 900_000.0, 3, 2, "Casa", True, 3),
        ("A2", "Venda e Aluguel", "Alphaville", 1_500_000.0, 4, 3, "Casa", True, 2),
        ("A3", "Aluguel", "Granja Viana", None, 2, 1, "Apartamento", True, 1),
        ("A4", "Venda", "Granja Viana", 700_000.0, 2, 1, "Apartamento", False, 4),
    ]:
        f.add_imovel(Imovel(codigo=codigo, status=status, bairro=bairro, valor_venda=venda, dormitorios=dorm, vagas=vagas,
                            categoria=cat, exibir_no_site=pub, data_atualizacao=date(2026, 10, dia)))
    return f


def _codes(page) -> list[str]:
    return [i.codigo for i in page.items]


class TestFake:
    def test_no_filter_returns_everything_capped(self):
        page = asyncio.run(_fake().search_imoveis(max_results=2))
        assert len(page.items) == 2 and page.total == 4

    @pytest.mark.parametrize("filtro,esperado", [
        ({"Status": ["Venda", "Venda e Aluguel"]}, {"A1", "A2", "A4"}),
        ({"Bairro": "granja viana"}, {"A1", "A3", "A4"}),
        ({"Bairro": ["Alphaville", "Granja Viana"], "Categoria": "Casa"}, {"A1", "A2"}),
        ({"ValorVenda": [800_000, 1_000_000]}, {"A1"}),
        ({"ValorVenda": [">=", 900_000]}, {"A1", "A2"}),
        ({"Dormitorios": [">=", 3], "Vagas": [">=", 3]}, {"A2"}),
        ({"Codigo": ["!=", "A1"]}, {"A2", "A3", "A4"}),
        ({"Codigo": ["A1", "A3"]}, {"A1", "A3"}),
        ({"Bairro": ["like", "%viana%"]}, {"A1", "A3", "A4"}),
        ({"ExibirNoSite": "Sim"}, {"A1", "A2", "A3"}),
    ])
    def test_filter_grammar(self, filtro, esperado):
        assert set(_codes(asyncio.run(_fake().search_imoveis(filter_=filtro)))) == esperado

    def test_order_desc_by_date(self):
        page = asyncio.run(_fake().search_imoveis(order={"DataAtualizacao": "desc"}))
        assert _codes(page) == ["A4", "A1", "A2", "A3"]

    def test_unsupported_filter_key_is_loud_not_ignored(self):
        with pytest.raises(ValueError):
            asyncio.run(_fake().search_imoveis(filter_={"Inventada": "x"}))


# ─── Real ────────────────────────────────────────────────────────────────

class _Real(VistaRESTAdapter):
    def __init__(self, handler):
        super().__init__(base_url="https://search-imoveis.test", api_key="K")
        self._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    def _client(self) -> VistaClient:
        return VistaClient(self._base_url, self._api_key, http_client=self._http)


def _row(i: int) -> dict:
    return {"Codigo": f"C{i:03d}", "Status": "Venda", "Bairro": "Granja Viana", "ValorVenda": "900000",
            "Dormitorios": "3", "Vagas": "2", "ExibirNoSite": "Sim"}


def _catalog(total: int, seen: list[dict]):
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/imoveis/detalhes"):
            codigo = req.url.params["imovel"]
            return httpx.Response(200, json={"Codigo": codigo, "Caracteristicas": {"Piscina": "Sim"}})
        pesquisa = json.loads(req.url.params["pesquisa"])
        seen.append(pesquisa)
        pag = pesquisa["paginacao"]["pagina"]
        first = (pag - 1) * 50
        rows = {str(i): _row(i) for i in range(first, min(first + 50, total))}
        body = {**rows, "total": total, "paginas": -(-total // 50), "pagina": pag, "quantidade": len(rows)}
        return httpx.Response(200, json=body)
    return handler


class TestReal:
    def test_walks_pages_up_to_max_results_and_sends_filter_and_order(self):
        seen: list[dict] = []
        real = _Real(_catalog(130, seen))
        filtro = {"Status": ["Venda"], "ValorVenda": [800_000, 1_000_000]}
        page = asyncio.run(real.search_imoveis(filter_=filtro, order={"DataAtualizacao": "desc"}, max_results=120))
        assert len(page.items) == 120 and page.total == 130 and page.pages == 3
        mine = [p for p in seen if p.get("filter") == filtro]
        assert {p["paginacao"]["pagina"] for p in mine} == {1, 2, 3}
        assert all(p["order"] == {"DataAtualizacao": "desc"} and p["paginacao"]["quantidade"] == 50 for p in mine)
        assert page.items[0].valor_venda == 900_000.0 and page.items[0].dormitorios == 3

    def test_with_detalhes_fills_caracteristicas(self):
        real = _Real(_catalog(3, []))
        page = asyncio.run(real.search_imoveis(max_results=3, with_detalhes=True))
        assert all("piscina" in i.caracteristicas for i in page.items)

    def test_empty_match_is_an_empty_page(self):
        def handler(req):
            return httpx.Response(404, json={"status": 404, "message": "A pesquisa não retornou resultados."})
        page = asyncio.run(_Real(handler).search_imoveis(filter_={"Bairro": "Nenhum"}))
        assert page.items == [] and page.total == 0

    def test_upstream_failure_raises_not_swallowed(self):
        def handler(req):
            return httpx.Response(401, json={"status": 401, "message": "Acesso negado"})
        with pytest.raises(VistaPermissionDenied):
            asyncio.run(_Real(handler).search_imoveis(filter_={"Bairro": "x"}))


# ─── refresh_imovel / list_destaques (per-code refresh while listar is down) ─────────────────────────────


from noctusai_lib.integrations.vista.client import VistaNotFound, VistaRecordUnpublished  # noqa: E402


class TestFakeRefresh:
    def test_returns_the_imovel_without_listar_only_fields(self):
        f = FakeVistaAdapter()
        f.add_imovel(Imovel(codigo="CA1", foto_destaque="u", banheiro_social=True, codigo_imobiliaria="X", valor_venda=1.0))
        got = asyncio.run(f.refresh_imovel("CA1"))
        assert got.valor_venda == 1.0 and got.foto_destaque is None and got.banheiro_social is None and got.codigo_imobiliaria is None

    def test_unknown_is_not_found_and_hidden_is_unpublished(self):
        f = FakeVistaAdapter()
        f.add_imovel(Imovel(codigo="CA2", exibir_no_site=False))
        with pytest.raises(VistaNotFound):
            asyncio.run(f.refresh_imovel("CA9"))
        with pytest.raises(VistaRecordUnpublished):
            asyncio.run(f.refresh_imovel("CA2"))

    def test_destaques(self):
        f = FakeVistaAdapter()
        assert asyncio.run(f.list_destaques()) == []
        f.set_destaques(["CA1", "ONE5"])
        assert asyncio.run(f.list_destaques()) == ["CA1", "ONE5"]


def _detalhes_handler(seen, *, corpo):
    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        if req.url.path.endswith("/imoveis/detalhes"):
            return httpx.Response(200, json=corpo(req.url.params["imovel"]))
        if req.url.path.endswith("/imoveis/destaques"):
            return httpx.Response(200, json={"CA0001": {"Codigo": "CA0001"}, "ONE5555": {"Codigo": "ONE5555"}, "total": 2})
        return httpx.Response(200, json={})  # listar: nothing (the outage)
    return handler


class TestRealRefresh:
    def test_uses_detalhes_alone_even_when_listar_is_empty_and_calibrates_with_the_code(self):
        seen: list[httpx.Request] = []
        real = _Real(_detalhes_handler(seen, corpo=lambda c: {"Codigo": c, "Status": "Venda", "ValorVenda": "900000", "Bairro": "X"}))
        got = asyncio.run(real.refresh_imovel("CA0190"))
        assert got.codigo == "CA0190" and got.valor_venda == 900_000.0 and got.foto_destaque is None
        assert all("/imoveis/listar" not in r.url.path for r in seen)
        assert seen and all(r.url.params.get("imovel") == "CA0190" for r in seen if r.url.path.endswith("/imoveis/detalhes"))

    def test_nonexistent_is_not_found_unpublished_is_unpublished(self):
        gone = _Real(_detalhes_handler([], corpo=lambda c: []))
        with pytest.raises(VistaNotFound):
            asyncio.run(gone.refresh_imovel("CA7777"))
        hidden = _Real(_detalhes_handler([], corpo=lambda c: {"Corretor": {"1": {"Nome": "B"}}}))
        with pytest.raises(VistaRecordUnpublished):
            asyncio.run(hidden.refresh_imovel("CA7778"))

    def test_invalid_code_is_not_found_without_a_call(self):
        seen: list[httpx.Request] = []
        with pytest.raises(VistaNotFound):
            asyncio.run(_Real(_detalhes_handler(seen, corpo=lambda c: {})).refresh_imovel("not a code"))
        assert seen == []

    def test_destaques_are_codes(self):
        assert asyncio.run(_Real(_detalhes_handler([], corpo=lambda c: {})).list_destaques()) == ["CA0001", "ONE5555"]
