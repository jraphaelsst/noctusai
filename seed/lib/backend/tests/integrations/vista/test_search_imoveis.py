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
