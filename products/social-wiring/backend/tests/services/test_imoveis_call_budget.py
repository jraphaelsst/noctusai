"""Vista call budget of the imóveis refresh: a change signal first (ONE listar call), detalhes only for changed / unknown
codes, and ONE pacer (the seed adapter's per-org bucket -- no product-side acquire). Synthetic data, Fake adapter seam."""
from __future__ import annotations

import asyncio
import re
from datetime import date
from pathlib import Path

from noctusai_lib.domain.real_estate import Imovel
from noctusai_lib.integrations import http_pool
from noctusai_lib.integrations.vista import FakeVistaAdapter
from noctusai_lib.integrations.vista.adapter_factory import get_vista_adapter_for_org

from app.services import imoveis_descoberta, imoveis_service
from tests.services.test_imoveis_sync_detalhes import ORG, _db, _linha, _reg, _svc

DIA = date(2026, 11, 2)


class _Contando(FakeVistaAdapter):
    """The Fake plus a per-endpoint call counter (what the wire would see)."""

    def __init__(self):
        super().__init__()
        self.listar = 0
        self.detalhes: list[str] = []

    async def list_changed_since(self, since, *, page_size=50):
        self.listar += 1
        return await super().list_changed_since(since, page_size=page_size)

    async def refresh_imovel(self, code):
        self.detalhes.append(code)
        return await super().refresh_imovel(code)


def _vista(*codigos_datas):
    a = _Contando()
    for codigo, data in codigos_datas:
        a.add_imovel(Imovel(codigo=codigo, status="Venda", valor_venda=200.0, data_atualizacao=data, exibir_no_site=True))
    return a


def _espelho(*codigos, data="2026-11-02"):
    return _db(mirror=[_linha(c, data_atualizacao=data) for c in codigos], registry=[_reg(c) for c in codigos])


def _rodar(svc, **kw):
    return asyncio.run(svc.sync_detalhes(ORG, descobrir=True, **kw))


def test_a_run_where_nothing_changed_costs_one_listar_call_and_no_detalhes():
    a = _vista(("CA0001", DIA), ("CA0002", DIA))
    rep = _rodar(_svc(_espelho("CA0001", "CA0002"), a))
    assert a.listar == 1 and a.detalhes == []
    assert rep.chamadas.get("detalhes", 0) == 0 and rep.chamadas["sinal"] == 1 and rep.atualizados == 0


def test_only_changed_codes_get_a_detalhes_call():
    a = _vista(("CA0001", DIA), ("CA0002", date(2026, 11, 5)))
    rep = _rodar(_svc(_espelho("CA0001", "CA0002"), a))
    assert a.listar == 1 and a.detalhes == ["CA0002"]
    assert rep.atualizados == 1


def test_a_new_code_is_found_by_the_signal_without_the_forward_probe():
    a = _vista(("CA0001", DIA), ("CA0003", date(2026, 11, 6)))
    rep = _rodar(_svc(_espelho("CA0001"), a))
    assert a.detalhes == ["CA0003"] and rep.novos == 1 and "sonda" not in rep.chamadas


def test_a_silent_listar_falls_back_to_the_full_walk_never_to_nothing_changed():
    a = _Contando()  # Vista knows nothing: total == 0, the signal is unusable
    rep = _rodar(_svc(_espelho("CA0001"), a), descobridores=[])
    assert a.detalhes == ["CA0001"] and rep.removidos == 1


def test_a_vitrine_code_is_reread_on_a_todos_run_so_a_hidden_one_is_still_noticed():
    a = _vista(("CA0001", DIA), ("CA0002", DIA))
    rep = _rodar(_svc(_espelho("CA0001", "CA0002"), a), escopo="todos")
    assert sorted(a.detalhes) == ["CA0001", "CA0002"] and rep.chamadas["detalhes"] == 2


def test_no_product_side_pacing_remains():
    for mod in (imoveis_service, imoveis_descoberta):
        src = Path(mod.__file__).read_text()
        assert not re.search(r"rate_limit\s*\.\s*acquire|VISTA_RATE_BUCKET\s*\)", src), mod.__name__


def test_the_per_org_adapter_rides_the_shared_pooled_client():
    class _Creds:
        def get(self, org_id):
            return "https://vista.invalid", "k"

    cliente = get_vista_adapter_for_org(_Creds(), "org-1")._client()
    assert cliente._pooled is True

    async def _dois():
        return http_pool.shared_async_client(), http_pool.shared_async_client()

    um, dois = asyncio.run(_dois())
    assert um is dois and um is not None
