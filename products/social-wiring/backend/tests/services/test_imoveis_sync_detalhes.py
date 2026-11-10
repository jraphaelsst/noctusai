"""The Vista imóveis mirror when `/imoveis/listar` is silent (2026-10-23 on): the per-code refresh (`sync_detalhes`), its
discovery seams, the listar-empty SAFETY, and the overlay guarantee (the sync writes Vista columns only).

Driven through `FakeVistaAdapter` (`refresh_imovel` / `list_destaques` / `list_imoveis`) over a MockSupabaseClient. Synthetic data."""
from __future__ import annotations

import asyncio
import logging
from datetime import date
from uuid import uuid4

import pytest
from noctusai_lib.domain.real_estate import Imovel, ImovelPage
from noctusai_lib.integrations.vista import FakeVistaAdapter
from noctusai_lib.integrations.vista.client import VistaNotFound, VistaUpstreamError
from noctusai_lib.integrations.vista.imovel_normalizer import vista_to_imovel
from noctusai_lib.testing import MockSupabaseClient

from app.services import imoveis_descoberta
from app.services.imoveis_service import COLUNAS_VISTA, ImovelSyncService, _assert_so_vista, _imovel_to_row

ORG = uuid4()
OUTRA = uuid4()


class _Db(MockSupabaseClient):
    """`schema()` is a no-op (MockSupabaseClient.schema() hands back a DIFFERENT client) + a recording `rpc`."""

    def __init__(self):
        super().__init__()
        self.rpc_calls: list[tuple[str, dict]] = []

    def schema(self, _name):
        return self

    def rpc(self, name, params=None):
        self.rpc_calls.append((name, params or {}))
        outer = self

        class _R:
            def execute(self_inner):
                class _D:
                    data = [{"marcados_ativos": 0, "marcados_delistados": 0}]
                return _D()
        return _R()


def _linha(codigo, org=ORG, **kw):
    base = {"org_id": str(org), "codigo": codigo, "codigo_norm": codigo.upper(), "status": "Venda", "exibir_no_site": True,
            "data_atualizacao": "2026-10-01", "sincronizado_em": "2026-10-23T00:00:00+00:00", "foto_destaque": f"https://f/{codigo}.jpg",
            "banheiro_social": True, "codigo_imobiliaria": f"IM-{codigo}", "valor_venda": 100.0}
    base.update(kw)
    return base


def _reg(codigo, org=ORG, ativo=True, **kw):
    base = {"org_id": str(org), "codigo_canonical": codigo.upper(), "codigo_display": codigo, "ativo_no_vista": ativo,
            "origem_descoberta": "vista_sync", "primeiro_visto_em": "2026-08-01T00:00:00+00:00", "delistado_em": None if ativo else "2026-10-01T00:00:00+00:00"}
    base.update(kw)
    return base


def _db(*, mirror=(), registry=()):
    db = _Db()
    db.set_table_data("imoveis", [dict(r) for r in mirror])
    db.set_table_data("imovel_registry", [dict(r) for r in registry])
    for t in ("vista_divergencias_config", "imovel_campo_conflitos", "imovel_captacao", "imovel_dados", "julia_proprietarios_contatos"):
        db.set_table_data(t, [])
    return db


def _svc(db, adapter, **kw):
    return ImovelSyncService(db, adapter, duplicate_detector=lambda *a, **k: None, **kw)


def _rodar(svc, **kw):
    return asyncio.run(svc.sync_detalhes(ORG, descobrir=False, **kw))


def _vista(*codigos, **kw):
    a = FakeVistaAdapter()
    for c in codigos:
        a.add_imovel(Imovel(codigo=c, status="Venda", valor_venda=200.0, data_atualizacao=date(2026, 11, 2), exibir_no_site=True,
                            foto_destaque="https://nova.jpg", **kw))
    return a


# ─── the per-code refresh ─────────────────────────────────────────────────


def test_refresh_updates_the_mirror_row_and_keeps_the_listar_only_fields():
    db = _db(mirror=[_linha("CA0001")], registry=[_reg("CA0001")])
    rep = _rodar(_svc(db, _vista("CA0001")))
    [row] = db.table("imoveis").select("*").execute().data
    assert row["valor_venda"] == 200.0 and row["data_atualizacao"] == "2026-11-02"
    # detalhes carries no photo / banheiro_social / codigo_imobiliaria: the mirror keeps what it had
    assert row["foto_destaque"] == "https://f/CA0001.jpg" and row["banheiro_social"] is True and row["codigo_imobiliaria"] == "IM-CA0001"
    assert (rep.atualizados, rep.novos, rep.inalterados, rep.removidos) == (1, 0, 0, 0)
    assert rep.caminho == "detalhes" and rep.chamadas == {"sinal": 1, "detalhes": 1} and rep.status_final == "ok"


def test_the_listar_and_detalhes_paths_build_the_same_row():
    """Pins that mapping a detalhes payload alone (no listing row) gives the same mirror row as listing + detalhes, for every
    column except the listar-only ones."""
    detalhes = {"Codigo": "CA0002", "TituloSite": "Casa", "Categoria": "Casa", "Status": "Venda", "Cidade": "Cotia", "Bairro": "Granja",
                "ValorVenda": "900000", "ValorCondominio": "1200", "ValorIptu": "450", "Dormitorios": "3", "Suites": "1", "Vagas": "2",
                "AreaTotal": "300", "AreaPrivativa": "200", "DataAtualizacao": "2026-11-02", "ExibirNoSite": "Sim", "Caracteristicas": {"Piscina": "Sim"}}
    listagem = {k: v for k, v in detalhes.items() if k != "Caracteristicas"} | {"FotoDestaque": "https://x.jpg", "BanheiroSocial": "Sim", "CodigoImobiliaria": "IM1"}
    ambos = _imovel_to_row(vista_to_imovel(listing=listagem, detalhes=detalhes), ORG, "t")
    so_detalhes = _imovel_to_row(vista_to_imovel(listing=None, detalhes=detalhes), ORG, "t")
    so_listar = {"foto_destaque", "banheiro_social", "codigo_imobiliaria"}
    diferem = {k for k in ambos if ambos[k] != so_detalhes[k]}
    assert diferem <= so_listar | {"vista_raw"}, diferem
    assert so_detalhes["valor_venda"] == 900000.0 and so_detalhes["caracteristicas"] == ["piscina"]


def test_an_unchanged_data_atualizacao_costs_no_detalhes_call_and_no_write():
    """The change signal sees the code is unchanged: no detalhes call, nothing rewritten (`forcar` still re-reads)."""
    db = _db(mirror=[_linha("CA0001", data_atualizacao="2026-11-02", valor_venda=555.0)], registry=[_reg("CA0001")])
    rep = _rodar(_svc(db, _vista("CA0001")))
    [row] = db.table("imoveis").select("*").execute().data
    assert row["valor_venda"] == 555.0 and row["sincronizado_em"] == "2026-10-23T00:00:00+00:00"
    assert (rep.inalterados, rep.atualizados, rep.upserted) == (0, 0, 0) and rep.chamadas == {"sinal": 1}
    forcado = _rodar(_svc(db, _vista("CA0001")), forcar=True)
    assert forcado.atualizados == 1 and db.table("imoveis").select("*").execute().data[0]["valor_venda"] == 200.0


def test_a_code_gone_from_vista_is_marked_removed_in_the_registry_and_never_deleted():
    db = _db(mirror=[_linha("CA0001", titulo="Casa X", bairro="Granja")], registry=[_reg("CA0001")])
    rep = _rodar(_svc(db, FakeVistaAdapter()))  # Vista knows nothing => VistaNotFound
    assert rep.removidos == 1 and rep.removidos_codigos == ["CA0001"]
    [reg] = db.table("imovel_registry").select("*").execute().data
    assert reg["ativo_no_vista"] is False and reg["delistado_em"] and reg["snap_titulo"] == "Casa X" and reg["snap_bairro"] == "Granja"
    assert reg["origem_descoberta"] == "vista_sync" and reg["primeiro_visto_em"] == "2026-08-01T00:00:00+00:00"
    assert len(db.table("imoveis").select("*").execute().data) == 1  # the mirror row stays


def test_an_unpublished_code_is_removed_and_hidden():
    db = _db(mirror=[_linha("CA0001")], registry=[_reg("CA0001")])
    a = FakeVistaAdapter()
    a.add_imovel(Imovel(codigo="CA0001", exibir_no_site=False))
    rep = _rodar(_svc(db, a))
    assert rep.removidos == 1
    assert db.table("imoveis").select("*").execute().data[0]["exibir_no_site"] is False


def test_a_transport_failure_is_a_failure_never_a_removal():
    class _Quebra(FakeVistaAdapter):
        async def refresh_imovel(self, code):
            raise VistaUpstreamError(500, "boom", "/imoveis/detalhes")

    db = _db(mirror=[_linha("CA0001")], registry=[_reg("CA0001")])
    rep = _rodar(_svc(db, _Quebra()))
    assert rep.removidos == 0 and rep.detalhes_failed == ["CA0001"] and rep.status_final == "incompleto"
    assert db.table("imovel_registry").select("*").execute().data[0]["ativo_no_vista"] is True


def test_the_circuit_breaker_refuses_a_mass_removal(caplog):
    codigos = [f"CA{i:04d}" for i in range(1, 61)]
    db = _db(mirror=[_linha(c) for c in codigos], registry=[_reg(c) for c in codigos])
    with caplog.at_level(logging.ERROR):
        rep = _rodar(_svc(db, FakeVistaAdapter()))  # Vista "lost" all 60
    assert rep.status_final == "removidos_excessivos" and rep.removidos == 0
    assert all(r["ativo_no_vista"] for r in db.table("imovel_registry").select("*").execute().data)
    assert any("refusing to mark" in r.getMessage() for r in caplog.records)


def test_a_returning_code_is_reactivated():
    db = _db(mirror=[_linha("CA0001")], registry=[_reg("CA0001", ativo=False)])
    _rodar(_svc(db, _vista("CA0001")), escopo="resto")
    [reg] = db.table("imovel_registry").select("*").execute().data
    assert reg["ativo_no_vista"] is True and reg["delistado_em"] is None and reg["origem_descoberta"] == "vista_sync"


# ─── tiers ────────────────────────────────────────────────────────────────


def _tiers():
    return _db(
        mirror=[_linha("CA0001"), _linha("CA0002", status="Vendido"), _linha("CA0003", exibir_no_site=False), _linha("CA0004"), _linha("OUT9", org=OUTRA)],
        registry=[_reg("CA0001"), _reg("CA0002"), _reg("CA0003"), _reg("CA0004", ativo=False)],
    )


@pytest.mark.parametrize("escopo,esperados", [
    ("vitrine", {"CA0001"}), ("resto", {"CA0002", "CA0003", "CA0004"}), ("todos", {"CA0001", "CA0002", "CA0003", "CA0004"}),
])
def test_tiers_pick_vitrine_or_rest(escopo, esperados):
    visto: list[str] = []

    class _Espia(FakeVistaAdapter):
        async def refresh_imovel(self, code):
            visto.append(code)
            return await super().refresh_imovel(code)

    a = _Espia()
    for c in ("CA0001", "CA0002", "CA0003", "CA0004"):
        a.add_imovel(Imovel(codigo=c, status="Venda", data_atualizacao=date(2026, 11, 2)))
    _rodar(_svc(_tiers(), a), escopo=escopo)
    assert set(visto) == esperados  # never another org's code


# ─── discovery ────────────────────────────────────────────────────────────


def test_destaques_discovery_finds_a_new_code_and_upserts_it_with_a_registry_row():
    db = _db(mirror=[_linha("CA0001")], registry=[_reg("CA0001")])
    a = _vista("CA0001", )
    a.add_imovel(Imovel(codigo="CA0050", status="Venda", data_atualizacao=date(2026, 11, 2)))
    a.set_destaques(["CA0001", "CA0050"])
    rep = asyncio.run(_svc(db, a).sync_detalhes(ORG, descobridores=[imoveis_descoberta.por_destaques]))
    assert rep.novos == 1 and rep.descobertos == ["CA0050"] and rep.chamadas.get("destaques") == 1
    assert {r["codigo"] for r in db.table("imoveis").select("*").execute().data} == {"CA0001", "CA0050"}
    assert any(r["codigo_canonical"] == "CA0050" and r["origem_descoberta"] == "vista_sync" for r in db.table("imovel_registry").select("*").execute().data)


def test_forward_probe_crosses_a_hole_but_stops_after_n_consecutive_misses():
    a = FakeVistaAdapter()
    for n in (1, 2, 5, 6):  # holes at 3-4 (2 misses), then 7.. nothing
        a.add_imovel(Imovel(codigo=f"CA{n:04d}", status="Venda", data_atualizacao=date(2026, 11, 2)))
    db = _db(mirror=[_linha("CA0001"), _linha("CA0002")], registry=[_reg("CA0001"), _reg("CA0002")])
    svc = _svc(db, a, sonda_max_falhas=3)
    rep = asyncio.run(svc.sync_detalhes(ORG, descobridores=[imoveis_descoberta.criar_sonda(3)]))
    assert sorted(rep.descobertos) == ["CA0005", "CA0006"]
    assert rep.chamadas["sonda"] == 7  # 3,4 miss; 5,6 hit; 7,8,9 miss => stop after 3 consecutive


def test_probe_groups_by_prefix_and_width():
    assert imoveis_descoberta.maiores_por_prefixo({"CA0190", "CA2830", "ONE10640", "ONE9", "x", "AP0643"}) == {
        "CA": (2830, 4), "ONE": (10640, 5), "AP": (643, 4)}


# ─── the listar-empty safety ──────────────────────────────────────────────


class _ListarVazio(FakeVistaAdapter):
    def __init__(self, modo):
        super().__init__()
        self._modo = modo

    async def list_imoveis(self, **kw):
        if self._modo == "notfound":
            raise VistaNotFound(404, "A pesquisa não retornou resultados", "/imoveis/listar")
        return ImovelPage(items=[], total=0, page=1, pages=1)


@pytest.mark.parametrize("modo", ["notfound", "vazia"])
def test_listar_empty_while_the_mirror_has_rows_refuses_the_sweep(modo, caplog):
    db = _db(mirror=[_linha("CA0001")], registry=[_reg("CA0001")])
    with caplog.at_level(logging.ERROR):
        rep = asyncio.run(_svc(db, _ListarVazio(modo)).sync(ORG))
    assert rep.status_final == "listar_vazio"
    assert db.rpc_calls == [], "the registry sweep MUST NOT run on an empty listar"
    assert db.table("imovel_registry").select("*").execute().data[0]["ativo_no_vista"] is True
    assert any("listar_vazio" in r.getMessage() for r in caplog.records)


def test_listar_empty_with_an_empty_mirror_is_not_an_alarm():
    rep = asyncio.run(_svc(_db(), _ListarVazio("vazia")).sync(ORG))
    assert rep.status_final != "listar_vazio"


def test_a_listar_that_answers_still_sweeps():
    db = _db(mirror=[_linha("CA0001")], registry=[_reg("CA0001")])
    a = FakeVistaAdapter()
    a.add_imovel(Imovel(codigo="CA0001", status="Venda"))
    rep = asyncio.run(_svc(db, a).sync(ORG, with_detalhes=False))
    assert rep.status_final == "ok" and [c[0] for c in db.rpc_calls] == ["sweep_imovel_registry"] and rep.chamadas["listar"] >= 1


# ─── OUR data is an overlay: the sync writes Vista columns only ────────────


def _donos():
    """One row in every table WE own, with values a sync must never touch."""
    return {
        "imovel_dados": [{"org_id": str(ORG), "codigo": "CA0001", "endereco_manual_logradouro": "Rua Nossa", "empreendimento_manual": "Cond Nosso",
                          "numero_registro_imoveis": "123", "situacao_onus": "livre", "condominio_id": "c1", "casa_de_rua": False}],
        "imovel_captacao": [{"org_id": str(ORG), "codigo_canonical": "CA0001", "valor_venda": 777.0, "titulo": "Manual", "updated_por": "u1"}],
        "imovel_duplicatas": [{"org_id": str(ORG), "codigo_a": "CA0001", "codigo_b": "MAN1", "status": "revisado"}],
        "julia_proprietarios_contatos": [{"id": "p1", "org_id": str(ORG), "imovel_codigo": "CA0001", "preco_confirmado": 111.0,
                                          "preco_tipo_confirmado": "venda", "confirmado_at": "2026-10-30T00:00:00+00:00", "status_confirmado": "disponivel"}],
        "atendimento_imoveis": [{"org_id": str(ORG), "codigo": "CA0001", "nota": "visita marcada"}],
        "imovel_documentos": [{"org_id": str(ORG), "codigo": "CA0001", "tipo_documento": "matricula"}],
    }


def _snapshot(db, donos):
    return {t: [dict(r) for r in db.table(t).select("*").execute().data] for t in donos}


@pytest.mark.parametrize("caminho", ["listar", "detalhes"])
def test_no_sync_path_touches_anything_we_own(caminho):
    donos = _donos()
    db = _db(mirror=[_linha("CA0001")], registry=[_reg("CA0001", origem_descoberta="lead")])
    for t, rows in donos.items():
        db.set_table_data(t, [dict(r) for r in rows])
    antes = _snapshot(db, donos)
    a = _vista("CA0001")
    if caminho == "listar":
        asyncio.run(_svc(db, a).sync(ORG, with_detalhes=True))
    else:
        asyncio.run(_svc(db, a).sync_detalhes(ORG, escopo="todos", descobrir=False))
    assert _snapshot(db, donos) == antes
    reg = db.table("imovel_registry").select("*").execute().data[0]
    assert reg["origem_descoberta"] == "lead" and reg["primeiro_visto_em"] == "2026-08-01T00:00:00+00:00"


def test_the_upsert_column_list_is_exactly_the_vista_columns_and_a_foreign_column_is_refused():
    assert set(_imovel_to_row(Imovel(codigo="CA0001"), ORG, "t")) == set(COLUNAS_VISTA)
    with pytest.raises(ValueError, match="non-Vista column"):
        _assert_so_vista([{"org_id": "o", "codigo": "x", "nota_interna": "nunca"}])
    for owned in ("created_at", "updated_at", "codigo_norm", "condominio_id", "casa_de_rua", "notas"):
        assert owned not in COLUNAS_VISTA
