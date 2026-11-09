"""Main broker vs partners on the Imovel (CodigoCorretor / CorretorNome / Agenciador), the unpublished-record stub keeping its `Corretor`
relation, and the broker roster seam (`list_corretores`) on the Fake adapter + the Real client's `fields` wire shape."""
from __future__ import annotations

import asyncio
from datetime import date

import pytest
from noctusai_lib.domain.real_estate import Imovel
from noctusai_lib.domain.real_estate.imovel import Corretor
from noctusai_lib.integrations.vista import CANDIDATE_IMOVEL_DETAIL_FIELDS, FakeVistaAdapter
from noctusai_lib.integrations.vista.client import VistaRecordUnpublished, _assert_detalhes_describes_record
from noctusai_lib.integrations.vista.imovel_normalizer import vista_to_imovel


def test_detail_fields_request_the_main_broker_fields():
    assert {"CodigoCorretor", "CorretorNome", "Agenciador"} <= {f for f in CANDIDATE_IMOVEL_DETAIL_FIELDS if isinstance(f, str)}


def test_the_normalizer_reads_the_main_broker_and_keeps_every_other_entry_as_a_partner_candidate():
    imovel = vista_to_imovel(listing=None, detalhes={
        "Codigo": "ONE10972", "CodigoCorretor": "112", "CorretorNome": "112:Diego Gomes", "Agenciador": "112:Diego Gomes",
        "Corretor": {"112": {"Codigo": "112", "Nome": "Diego Gomes"}, "56": {"Codigo": "56", "Nome": "Priscila Hijazi"}},
    })
    assert imovel.codigo_corretor == "112" and imovel.corretor_nome == "Diego Gomes" and imovel.agenciador == "112:Diego Gomes"
    assert [c.codigo for c in imovel.corretores] == ["112", "56"]


def test_a_record_without_the_main_broker_fields_leaves_them_none():
    imovel = vista_to_imovel(listing=None, detalhes={"Codigo": "X1"})
    assert imovel.codigo_corretor is None and imovel.corretor_nome is None and imovel.agenciador is None


def test_the_unpublished_stub_keeps_its_corretor_relation_on_the_exception():
    class R:
        endpoint = "/imoveis/detalhes"
        data = {"Corretor": {"112": {"Codigo": "112", "Nome": "Diego"}}}

    with pytest.raises(VistaRecordUnpublished) as e:
        _assert_detalhes_describes_record(R(), "ONE10959")
    assert e.value.payload["Corretor"]["112"]["Nome"] == "Diego" and e.value.payload_keys == ["Corretor"]


def test_the_fake_adapter_unpublished_record_carries_the_corretor_relation():
    a = FakeVistaAdapter()
    a.add_imovel(Imovel(codigo="ONE10959", exibir_no_site=False, data_atualizacao=date(2026, 11, 1), corretores=[Corretor(codigo="56", nome="Priscila")]))
    with pytest.raises(VistaRecordUnpublished) as e:
        asyncio.run(a.refresh_imovel("ONE10959"))
    assert e.value.payload["Corretor"]["56"]["Nome"] == "Priscila"


def test_the_fake_adapter_serves_the_roster_page_by_page_in_vistas_shape():
    a = FakeVistaAdapter()
    for n in range(1, 8):
        a.add_corretor({"Codigo": str(n), "Nome": f"P{n}"})
    itens, pag = asyncio.run(a.list_corretores(page=2, page_size=3))
    assert [i["Codigo"] for i in itens] == ["4", "5", "6"] and pag == {"total": 7, "paginas": 3, "pagina": 2, "quantidade": 3}


def test_the_real_client_sends_fields_as_pesquisa_only_when_given():
    from noctusai_lib.integrations.vista.client import VistaClient

    visto = {}

    async def request(self, endpoint, **kw):
        visto.update(kw)
        return object()

    VistaClient._request, original = request, VistaClient._request
    try:
        c = VistaClient.__new__(VistaClient)
        asyncio.run(c.listar_corretores(page=1, page_size=50))
        assert "pesquisa" not in visto
        asyncio.run(c.listar_corretores(page=1, page_size=50, fields=["Codigo", "Nome", "CRECI"]))
        assert visto["pesquisa"] == {"fields": ["Codigo", "Nome", "CRECI"]} and visto["extra_params"] == {"page": 1, "limit": 50}
    finally:
        VistaClient._request = original
