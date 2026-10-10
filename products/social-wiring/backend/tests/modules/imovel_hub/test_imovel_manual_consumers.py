"""A MANUAL imóvel (migration 226) is found AND rendered by every consumer.

Every consumer resolves an imóvel through the REGISTRY and renders it through
`busca_service.enriquecer` (mirror -> captação + imovel_dados -> registry
`snap_*`). A manual imóvel has no mirror row and no `snap_*`, so each consumer
below is proved to show its título and address — none reads the mirror directly
except `similares` / `permutas` (out of scope, documented in the delivery).

Covers: `/busca` (the lead form / shared `ImovelCodigoPicker` search),
atendimento imóveis, interesses, the campanhas imóvel path (código -> registry
id, solicitações listing, campaign CRUD titles), the list view read, null-safety
of every Vista-only key, and the sync/sweep isolation (roteiros + propostas
consumers live in `tests/modules/card_hub/test_manual_imovel_consumers.py`).
"""
from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

import pytest

from noctusai_lib.integrations.vista import FakeVistaAdapter
from noctusai_lib.domain.real_estate import Imovel

from app.modules.imovel_hub import busca_service
from app.modules.imovel_hub import captacao_service as cap
from app.services.campanhas_service import CampanhasService
from app.services.campanhas_veiculacao_service import CampanhasVeiculacaoService
from app.services.imoveis_service import ImoveisService, ImovelSyncService
from tests.modules.imovel_hub.conftest import ORG_ID, auth, dados_row, imovel_row, manual, registry_row, seed
from tests.modules.imovel_hub.relacionamentos_rows import (
    atendimento_row,
    cliente_row,
    espelho,
    registro,
    seed_tabelas,
)
from tests.support.campanhas_fake import FakeCampanhasClient

ENDERECO = "Alameda Liverpool, 81 — Reserva do Vianna, Cotia/SP"


# ─── (a) /busca ───────────────────────────────────────────────────────────


class TestBusca:
    @pytest.mark.parametrize(
        "termo", ["SW-0001", "sw-00", "Casa Reserva", "Liverpool", "Reserva do Vianna"]
    )
    def test_manual_e_encontrado_e_enriquecido(self, client, scoped, termo):
        manual(scoped, empreendimento_manual="Reserva do Vianna")
        r = client.get("/api/imoveis/busca", params={"q": termo}, headers=auth())
        assert r.status_code == 200, r.text
        item = next(i for i in r.json()["items"] if i["codigo"] == "SW-0001")
        assert item["fonte"] == "manual" and item["registrado"] is True
        assert item["origem"] == "manual" and item["ativo_no_vista"] is False
        assert item["titulo"] == "Casa Reserva do Vianna"
        assert item["endereco"] == ENDERECO
        assert item["valor"] == 1500000.0 and item["valor_tipo"] == "venda"
        # Vista-only keys: honest null/empty, never missing
        assert item["foto_destaque"] is None and item["corretores"] == []

    def test_registry_only_manual_acha_pelo_endereco(self, client, scoped):
        seed(
            scoped,
            registry=[registry_row("TYPED-1", ativo_no_vista=False, origem_descoberta="manual")],
            imoveis=[],
            dados=[dados_row("TYPED-1", endereco_manual_logradouro="Rua dos Ipês",
                             endereco_manual_numero="10", endereco_manual_bairro="Centro",
                             endereco_manual_cidade="Cotia", endereco_manual_uf="SP")],
        )
        scoped.set_table_data("imovel_captacao", [])
        item = client.get("/api/imoveis/busca", params={"q": "Ipês"}, headers=auth()).json()["items"][0]
        assert item["codigo"] == "TYPED-1" and item["fonte"] == "manual"
        assert item["titulo"] is None and item["endereco"] == "Rua dos Ipês, 10 — Centro, Cotia/SP"
        assert item["valor"] is None and item["foto_destaque"] is None

    def test_manual_de_outra_org_nao_aparece(self, client, scoped):
        manual(scoped)
        scoped.table("imovel_captacao")._data[0]["org_id"] = "00000000-0000-4000-8000-000000000099"
        scoped.table("imovel_dados")._data[0]["org_id"] = "00000000-0000-4000-8000-000000000099"
        r = client.get("/api/imoveis/busca", params={"q": "Liverpool"}, headers=auth())
        assert r.json()["items"] == []

    def test_mesmas_chaves_do_imovel_vista(self, scoped):
        """A manual item carries EXACTLY the keys a Vista item does."""
        manual(scoped)
        scoped.table("imoveis")._data.append(espelho("ONE1"))
        scoped.table("imovel_registry")._data.append(registro("ONE1"))
        out = busca_service.enriquecer(scoped, UUID(ORG_ID), ["SW-0001", "ONE1"])
        assert set(out["SW-0001"]) == set(out["ONE1"])


# ─── (c) atendimento imóveis + interesses ─────────────────────────────────


@pytest.fixture
def cenario(client, scoped):
    cliente = cliente_row()
    seed_tabelas(
        scoped,
        clientes=[cliente],
        atendimentos=[atendimento_row(cliente_id=cliente["id"])],
        imovel_registry=[],
        imoveis=[],
        imovel_dados=[],
        atendimento_imoveis=[],
        atendimento_negociacao=[],
        cliente_imovel_interesses=[],
    )
    manual(scoped)
    return {"cliente": cliente, "scoped": scoped}


class TestAtendimentoImoveis:
    def test_vincular_e_listar_um_manual(self, client, cenario):
        base = f"/api/clientes/{cenario['cliente']['id']}/atendimento-imoveis"
        r = client.post(base, json={"codigo": "sw-0001"}, headers=auth())
        assert r.status_code == 201, r.text
        assert r.json()["imovel"]["titulo"] == "Casa Reserva do Vianna"
        body = client.get(base, headers=auth()).json()
        imovel = body["items"][0]["imovel"]
        assert body["items"][0]["codigo"] == "SW-0001"
        assert imovel["fonte"] == "manual"
        assert imovel["titulo"] == "Casa Reserva do Vianna" and imovel["endereco"] == ENDERECO
        assert imovel["foto_destaque"] is None


class TestInteresses:
    def test_adicionar_e_listar_um_manual(self, client, cenario):
        base = f"/api/clientes/{cenario['cliente']['id']}/interesses"
        r = client.post(base, json={"codigo": "SW-0001"}, headers=auth())
        assert r.status_code == 201, r.text
        item = client.get(base, headers=auth()).json()["items"][0]
        assert item["codigo"] == "SW-0001"
        assert item["imovel"]["titulo"] == "Casa Reserva do Vianna"
        assert item["imovel"]["endereco"] == ENDERECO


# ─── (b) campanhas ────────────────────────────────────────────────────────


def _campanha_fake() -> tuple[FakeCampanhasClient, str]:
    c = FakeCampanhasClient()
    org = uuid4()
    reg = c.add_imovel(org, "SW-0001")  # no snap_titulo: a manual imóvel never gets one
    c.tables["imovel_registry"][0].update(origem_descoberta="manual", ativo_no_vista=False)
    c.tables["imovel_captacao"] = [
        {"org_id": str(org), "codigo_canonical": "SW-0001", "titulo": "Casa Reserva do Vianna"}
    ]
    c.tables["imovel_dados"] = [
        {"org_id": str(org), "codigo": "SW-0001", "endereco_manual_bairro": "Reserva do Vianna",
         "endereco_manual_cidade": "Cotia", "endereco_manual_uf": "SP"}
    ]
    c._org, c._reg = org, reg
    return c, reg


class TestCampanhas:
    def test_codigo_resolve_para_o_id_do_registry(self):
        c, reg = _campanha_fake()
        assert CampanhasService(c).resolve_imovel_ref(c._org, "sw-0001") == reg

    def test_solicitar_para_um_manual(self):
        c, _ = _campanha_fake()
        out = CampanhasService(c).solicitar(c._org, "sw-0001", justificativa="lançar")
        assert out["status"] == "pendente"

    def test_listagem_de_solicitacoes_titula_o_manual(self):
        c, reg = _campanha_fake()
        c.tables["campanha_solicitacoes"] = [{
            "id": str(uuid4()), "org_id": str(c._org), "imovel_ref_id": reg, "status": "pendente",
            "solicitado_em": "2026-10-09T10:00:00+00:00",
            "imovel_registry": {
                "codigo_canonical": "SW-0001", "codigo_display": "SW-0001", "ativo_no_vista": False,
                "snap_titulo": None, "snap_bairro": None, "snap_cidade": None,
            },
        }]
        rows = CampanhasService(c).listar_solicitacoes(c._org)
        reg_out = rows[0]["imovel_registry"]
        assert reg_out["snap_titulo"] == "Casa Reserva do Vianna"
        assert reg_out["snap_bairro"] == "Reserva do Vianna" and reg_out["snap_cidade"] == "Cotia"

    def test_crud_de_campanha_titula_o_manual(self):
        c, _ = _campanha_fake()
        out = CampanhasVeiculacaoService(c).criar(
            c._org, nome="Lançamento", imovel_codigos=["sw-0001"], veiculacoes=[]
        )
        assert out["imoveis"] == [{"codigo": "SW-0001", "titulo": "Casa Reserva do Vianna"}]


# ─── list reads the view ──────────────────────────────────────────────────


class TestListaLeDaView:
    def test_list_e_filtros_leem_imoveis_catalogo(self, scoped):
        """Filters / count / order / pages stay ONE query — against the view."""
        scoped.set_table_data("imoveis_catalogo", [
            {"org_id": ORG_ID, "codigo": "SW-0001", "titulo": "Casa", "categoria": "Casa",
             "status": "Venda", "cidade": "Cotia", "bairro": "Centro", "caracteristicas": [],
             "vista_raw": {}, "fonte": "manual", "data_atualizacao": "2026-10-09"},
        ])
        scoped.set_table_data("imoveis", [])  # the mirror table is NOT what the list reads

        class _Mesmo:
            def schema(self, _n):
                return scoped

        svc = ImoveisService(_Mesmo())
        page = svc.list(UUID(ORG_ID))
        assert page["total"] == 1
        row = page["items"][0]
        assert row["fonte"] == "manual" and row["codigo"] == "SW-0001"
        # Vista-only derived keys are null-safe on a manual row
        assert row["dias_desde_atualizacao"] is None and row["orientacao_solar"] == []
        assert svc.filter_options(UUID(ORG_ID))["cidade"] == ["Cotia"]
        assert svc.caracteristica_counts(UUID(ORG_ID)) == {}


# ─── isolation: sync + sweep never touch a manual imóvel ──────────────────


class _TocaSo:
    """Recording client: every table the sync touches, and the sweep RPC."""

    def __init__(self, scoped):
        self._scoped, self.tabelas, self.rpcs = scoped, [], []

    def schema(self, _n):
        return self

    def table(self, nome):
        self.tabelas.append(nome)
        return self._scoped.table(nome)

    def rpc(self, nome, params=None):
        self.rpcs.append((nome, params))
        return self._scoped.rpc(nome, params)


class TestIsolamento:
    def test_sync_e_sweep_nao_tocam_o_manual(self, scoped):
        manual(scoped)
        scoped.set_rpc_data("sweep_imovel_registry", [{"marcados_ativos": 1, "marcados_delistados": 0}])
        antes = {
            t: [dict(r) for r in scoped.table(t)._data]
            for t in ("imovel_registry", "imovel_captacao", "imovel_dados")
        }
        adapter = FakeVistaAdapter()
        adapter.add_imovel(Imovel(codigo="ONE1000", categoria="Casa"))
        rec = _TocaSo(scoped)
        report = asyncio.run(ImovelSyncService(rec, adapter).sync(UUID(ORG_ID), with_detalhes=False))

        assert report.complete is True and report.upserted == 1
        assert [n for n, _ in rec.rpcs] == ["sweep_imovel_registry"]
        # the sync only ever addresses the mirror and the registry
        assert set(rec.tabelas) <= {"imoveis", "imovel_registry"}
        # the manual registry row is untouched; captação + deal refs untouched
        registry = {r["codigo_canonical"]: r for r in scoped.table("imovel_registry")._data}
        assert registry["SW-0001"] == next(r for r in antes["imovel_registry"] if r["codigo_canonical"] == "SW-0001")
        assert scoped.table("imovel_captacao")._data == antes["imovel_captacao"]
        assert scoped.table("imovel_dados")._data == antes["imovel_dados"]
        # the mirror holds ONLY the Vista imóvel: a manual one is never in it,
        # so it can never feed `_last_sync_at` (NULL `sincronizado_em`) nor the sweep
        assert [r["codigo"] for r in scoped.table("imoveis")._data] == ["ONE1000"]

    def test_o_sweep_so_enxerga_linhas_ativas_no_vista(self):
        """The SQL guard behind the isolation: a manual registry row is born
        `ativo_no_vista=false` and the sweep's delist/activate statements
        only select `ativo_no_vista` rows that are in (or leave) the mirror."""
        from pathlib import Path

        sql = (Path(__file__).resolve().parents[3] / "migrations" / "064_registry_sweep_guard.sql").read_text()
        assert "AND r.ativo_no_vista" in sql
        assert "FROM presentes p" in sql  # activation joins on the MIRROR's codigo_norm

    def test_ultimo_sync_ignora_o_manual(self, scoped):
        from app.services.imoveis_sync_scheduler import _last_sync_at

        manual(scoped)
        scoped.set_table_data("imoveis", [])

        class _Mesmo:
            def schema(self, _n):
                return scoped

        assert _last_sync_at(_Mesmo(), ORG_ID) is None
