"""Possível duplicado — detect / surface / dismiss (migration 228, CONTRACT §8.6).

WHAT THIS PINS
--------------
- every signal, its score and its normalisation (matrícula digits, CRI, the
  logradouro type-prefix strip, ±5% área / ±10% preço); the 0.05 bonus per extra
  signal, the 0.99 cap, the ≥ 0.50 threshold;
- a `descartado` pair is never resurrected; a `pendente` one is refreshed; a
  linked manual imóvel (and an already-linked Vista row) is skipped;
- NOTHING is merged: detection writes only the candidates table;
- the hooks (Vista sync, manual create/edit) run detection as a separate step
  whose failure is logged loudly and never fails the host write;
- the routes: list shape/order/status filter, descartar, the Imovel additions,
  route order vs `GET /{codigo}`, strict `== 401`.
"""
from __future__ import annotations

import asyncio
import logging
import re
from uuid import UUID

import pytest

from noctusai_lib.integrations.vista import FakeVistaAdapter
from noctusai_lib.domain.real_estate import Imovel

from app.modules.imovel_hub import captacao_service as cap
from app.modules.imovel_hub import duplicatas_service as dup
from app.services.imoveis_service import ImovelSyncService
from tests.modules.imovel_hub.conftest import ORG_ID, auth
from tests.modules.imovel_hub.dup_rows import MANUAL, VISTA, ENDERECO_MANUAL, cenario, par_row

ORG = UUID(ORG_ID)


def candidatos(scoped) -> list[dict]:
    return scoped.table("imovel_duplicata_candidatos")._data


def detectar(scoped, **kw):
    return dup.detectar(scoped, ORG, **kw)


# ─── normalisation (pure) ─────────────────────────────────────────────────


class TestNormalizacao:
    @pytest.mark.parametrize(
        "a,b",
        [
            ("Rua das Flores", "R. das Flores"),
            ("Avenida Paulista", "Av. Paulista"),
            ("Av Paulista", "AVENIDA PAULISTA"),
            ("Alameda Liverpool", "Al. Liverpool"),
            ("Alameda Liverpool", "alameda  liverpool "),
            ("Rua São João", "rua sao joao"),
        ],
    )
    def test_logradouro_ignora_tipo_acento_e_caixa(self, a, b):
        assert dup.logradouro_norm(a) == dup.logradouro_norm(b) is not None

    def test_logradouro_so_tira_um_prefixo_e_so_no_inicio(self):
        assert dup.logradouro_norm("Rua Avenida Brasil") == "AVENIDA BRASIL"
        assert dup.logradouro_norm("Travessa da Rua") == "TRAVESSA DA RUA"
        assert dup.logradouro_norm("   ") is None

    def test_matricula_so_digitos(self):
        assert dup._digitos("79.826") == dup._digitos("79826") == "79826"
        assert dup._digitos("n/d") is None

    def test_cri_estrito_mas_ignora_acento_pontuacao_e_caixa(self):
        assert dup._cri("1º CRI") == dup._cri("1o cri") == dup._cri("1° C.R.I.")
        assert dup._cri("1º CRI") != dup._cri("2º CRI")
        assert dup._cri("1") != dup._cri("1º CRI de Cotia")  # never loosened to digits only

    def test_numero_sem_numero_nao_casa(self):
        assert dup._numero_imovel("S/N") is None and dup._numero_imovel("sn") is None
        assert dup._numero_imovel("81 ") == "81"


# ─── scoring (pure) ───────────────────────────────────────────────────────


def _m(**dados):
    return dup.fatos_manual("SW-1", dados, {})


def _v(espelho=None, **dados):
    return dup.fatos_vista("ONE1", espelho or {}, dados)


class TestPontuacao:
    def test_pesos_dos_quatro_sinais(self):
        assert dup.pontuar([{"sinal": "matricula_cri"}]) == 0.95
        assert dup.pontuar([{"sinal": "matricula"}]) == 0.80
        assert dup.pontuar([{"sinal": "endereco"}]) == 0.70
        assert dup.pontuar([{"sinal": "empreendimento_area_preco"}]) == 0.50

    def test_mais_cinco_centesimos_por_outro_sinal_e_teto_099(self):
        assert dup.pontuar([{"sinal": "matricula"}, {"sinal": "endereco"}]) == 0.85
        assert dup.pontuar([{"sinal": "endereco"}, {"sinal": "empreendimento_area_preco"}]) == 0.75
        tudo = [{"sinal": s} for s in dup.SCORE_SINAL]
        assert dup.pontuar(tudo) == 0.99  # 0.95 + 0.15 capped

    def test_sem_sinais_pontua_zero(self):
        assert dup.pontuar([]) == 0.0


class TestSinalMatricula:
    def test_mesma_matricula_e_mesmo_cri(self):
        s = dup.sinais_do_par(
            _m(numero_matricula="79.826", numero_registro_imoveis="1º CRI"),
            _v(numero_matricula="79826", numero_registro_imoveis="1o cri"),
        )
        assert [x["sinal"] for x in s] == ["matricula_cri"]

    def test_cri_desconhecido_em_um_lado_e_so_matricula(self):
        s = dup.sinais_do_par(
            _m(numero_matricula="79826", numero_registro_imoveis="1º CRI"),
            _v(numero_matricula="79826"),
        )
        assert [x["sinal"] for x in s] == ["matricula"]
        s = dup.sinais_do_par(_m(numero_matricula="79826"), _v(numero_matricula="79826"))
        assert [x["sinal"] for x in s] == ["matricula"]

    def test_cris_conhecidos_e_diferentes_nao_casam(self):
        """Same number, two different cartório records: not the same property."""
        s = dup.sinais_do_par(
            _m(numero_matricula="79826", numero_registro_imoveis="1º CRI"),
            _v(numero_matricula="79826", numero_registro_imoveis="2º CRI"),
        )
        assert s == []

    def test_matricula_vista_do_espelho_conta_como_matricula(self):
        s = dup.sinais_do_par(
            _m(numero_matricula="79826", numero_registro_imoveis="1º CRI"),
            _v({"matricula_vista": "79.826"}),
        )
        assert [x["sinal"] for x in s] == ["matricula"]

    def test_matriculas_diferentes_ou_ausentes_nao_casam(self):
        assert dup.sinais_do_par(_m(numero_matricula="1"), _v(numero_matricula="2")) == []
        assert dup.sinais_do_par(_m(), _v()) == []


def _end(cep="06709-300", bairro="Reserva do Vianna", logradouro="Alameda Liverpool", numero="81"):
    return {
        "endereco_manual_logradouro": logradouro, "endereco_manual_numero": numero,
        "endereco_manual_cep": cep, "endereco_manual_bairro": bairro,
    }


def _esp(cep="06709300", bairro="Reserva do Vianna", logradouro="Al. Liverpool", numero="81", **extra):
    return {"logradouro": logradouro, "numero": numero, "cep": cep, "bairro": bairro, **extra}


class TestSinalEndereco:
    def test_mesmo_logradouro_numero_e_cep(self):
        s = dup.sinais_do_par(_m(**_end(bairro="Outro")), _v(_esp(bairro="Diferente")))
        assert [x["sinal"] for x in s] == ["endereco"]

    def test_mesmo_logradouro_numero_e_bairro_sem_cep(self):
        s = dup.sinais_do_par(_m(**_end(cep=None)), _v(_esp(cep=None)))
        assert [x["sinal"] for x in s] == ["endereco"]
        s = dup.sinais_do_par(_m(**_end(cep="01000-000")), _v(_esp(cep="06709300")))
        assert [x["sinal"] for x in s] == ["endereco"]  # CEP differs, bairro matches

    def test_nem_cep_nem_bairro_nao_casa(self):
        s = dup.sinais_do_par(_m(**_end(bairro="A", cep="01000-000")), _v(_esp(bairro="B")))
        assert s == []

    def test_numero_diferente_ou_ausente_nao_casa(self):
        assert dup.sinais_do_par(_m(**_end(numero="82")), _v(_esp())) == []
        assert dup.sinais_do_par(_m(**_end(numero="S/N")), _v(_esp(numero="S/N"))) == []
        assert dup.sinais_do_par(_m(**_end(numero=None)), _v(_esp(numero=None))) == []

    def test_logradouro_diferente_nao_casa(self):
        assert dup.sinais_do_par(_m(**_end(logradouro="Rua Outra")), _v(_esp())) == []


def _par_emp(area_m, area_v, preco_m, preco_v, emp_m="Reserva do Vianna", emp_v="reserva do vianna",
             campo_area="area_total"):
    m = dup.fatos_manual(
        "SW-1", {"empreendimento_manual": emp_m},
        {campo_area: area_m, "valor_venda": preco_m},
    )
    v = dup.fatos_vista("ONE1", {"empreendimento": emp_v, campo_area: area_v, "valor_venda": preco_v}, {})
    return dup.sinais_do_par(m, v)


class TestSinalEmpreendimento:
    def test_empreendimento_area_e_preco_dentro_da_tolerancia(self):
        s = _par_emp(100, 104, 1_000_000, 1_090_000)
        assert [x["sinal"] for x in s] == ["empreendimento_area_preco"]

    def test_area_privativa_tambem_vale(self):
        s = _par_emp(80, 82, 500_000, 500_000, campo_area="area_privativa")
        assert [x["sinal"] for x in s] == ["empreendimento_area_preco"]

    def test_borda_da_area_5_por_cento(self):
        assert _par_emp(100, 105, 1_000_000, 1_000_000)  # exactly 5% of the larger
        assert _par_emp(100, 106, 1_000_000, 1_000_000) == []

    def test_borda_do_preco_10_por_cento(self):
        assert _par_emp(100, 100, 1_000_000, 1_100_000)  # exactly 10% of the larger
        assert _par_emp(100, 100, 1_000_000, 1_120_000) == []

    def test_empreendimento_diferente_ou_ausente_nao_casa(self):
        assert _par_emp(100, 100, 1, 1, emp_v="Outro") == []
        assert _par_emp(100, 100, 1, 1, emp_m=None, emp_v=None) == []

    def test_area_ou_preco_ausentes_nao_casam(self):
        assert _par_emp(None, 100, 1_000_000, 1_000_000) == []
        assert _par_emp(100, 100, None, 1_000_000) == []


# ─── detectar (IO) ────────────────────────────────────────────────────────


MATRICULA_CRI = dict(
    manual_dados={"numero_matricula": "79.826", "numero_registro_imoveis": "1º CRI"},
    vista_dados={"numero_matricula": "79826", "numero_registro_imoveis": "1o CRI"},
)


class TestDetectar:
    def test_grava_o_par_com_score_e_sinais(self, client, scoped):
        cenario(scoped, **MATRICULA_CRI)
        r = detectar(scoped)
        assert r["avaliados"] == 1 and r["criados"] == 1
        (par,) = candidatos(scoped)
        assert (par["codigo_manual"], par["codigo_vista"], par["status"]) == (MANUAL, VISTA, "pendente")
        assert par["score"] == 0.95
        assert [s["sinal"] for s in par["sinais"]] == ["matricula_cri"]
        assert all(set(s) == {"sinal", "detalhe"} for s in par["sinais"])

    def test_varios_sinais_somam_cinco_centesimos_cada(self, client, scoped):
        cenario(scoped, manual_dados={**MATRICULA_CRI["manual_dados"], **ENDERECO_MANUAL},
                vista_dados=MATRICULA_CRI["vista_dados"])
        detectar(scoped)
        (par,) = candidatos(scoped)
        assert [s["sinal"] for s in par["sinais"]] == ["matricula_cri", "endereco"]  # strongest first
        assert par["score"] == 0.99  # 0.95 + 0.05, capped

    def test_so_o_endereco_ja_passa_do_limiar(self, client, scoped):
        cenario(scoped, manual_dados=ENDERECO_MANUAL)
        detectar(scoped)
        (par,) = candidatos(scoped)
        assert par["score"] == 0.70 and [s["sinal"] for s in par["sinais"]] == ["endereco"]

    def test_abaixo_de_050_nao_grava(self, client, scoped):
        """Area alone (no empreendimento, no matrícula, no address) is no signal."""
        cenario(
            scoped, manual_cap={"area_total": 100}, espelho={"area_total": 100, "logradouro": "Rua X"},
            manual_dados={"empreendimento_manual": "Cond Z"},
        )
        assert detectar(scoped)["criados"] == 0
        assert candidatos(scoped) == []

    def test_empreendimento_area_e_preco_de_ponta_a_ponta(self, client, scoped):
        cenario(
            scoped,
            manual_dados={"empreendimento_manual": "Reserva do Vianna"},
            manual_cap={"area_total": 100, "valor_venda": 1_000_000},
            espelho={"empreendimento": "RESERVA DO VIANNA", "area_total": 103, "valor_venda": 1_050_000,
                     "logradouro": "Rua Z"},
        )
        detectar(scoped)
        (par,) = candidatos(scoped)
        assert par["score"] == 0.50 and par["sinais"][0]["sinal"] == "empreendimento_area_preco"

    def test_matricula_vista_do_espelho(self, client, scoped):
        cenario(scoped, manual_dados={"numero_matricula": "79826"}, espelho={"matricula_vista": "79.826"})
        detectar(scoped)
        (par,) = candidatos(scoped)
        assert par["score"] == 0.80 and par["sinais"][0]["sinal"] == "matricula"

    def test_redeteccao_atualiza_o_pendente_sem_duplicar(self, client, scoped):
        cenario(scoped, manual_dados=ENDERECO_MANUAL)
        detectar(scoped)
        scoped.table("imovel_dados")._data[0].update(
            numero_matricula="79826", numero_registro_imoveis="1º CRI"
        )
        scoped.table("imovel_dados")._data[1].update(
            numero_matricula="79826", numero_registro_imoveis="1º CRI"
        )
        r = detectar(scoped)
        assert (r["criados"], r["atualizados"]) == (0, 1)
        (par,) = candidatos(scoped)
        assert par["score"] == 0.99 and len(par["sinais"]) == 2

    def test_descartado_nunca_ressuscita_mesmo_com_sinais_novos(self, client, scoped):
        cenario(scoped, manual_dados=ENDERECO_MANUAL)
        detectar(scoped)
        candidatos(scoped)[0].update(status="descartado", resolvido_em="2026-10-10T00:00:00+00:00")
        scoped.table("imovel_dados")._data[0].update(
            numero_matricula="79826", numero_registro_imoveis="1º CRI"
        )
        scoped.table("imovel_dados")._data[1].update(
            numero_matricula="79826", numero_registro_imoveis="1º CRI"
        )
        r = detectar(scoped)
        (par,) = candidatos(scoped)
        assert par["status"] == "descartado" and par["score"] == 0.70
        assert r["criados"] == 0 and r["ignorados_resolvidos"] == 1

    def test_confirmado_tambem_nao_e_tocado(self, client, scoped):
        cenario(scoped, manual_dados=ENDERECO_MANUAL, pares=[par_row("confirmado", 0.5)])
        detectar(scoped)
        (par,) = candidatos(scoped)
        assert par["status"] == "confirmado" and par["score"] == 0.5

    def test_manual_ja_vinculado_e_pulado(self, client, scoped):
        reg = cenario(scoped, manual_dados=ENDERECO_MANUAL)
        scoped.table("imovel_registry")._data[0]["vinculado_a"] = reg["vista"]["id"]
        r = detectar(scoped)
        assert r["avaliados"] == 0 and candidatos(scoped) == []

    def test_vista_que_ja_tem_manual_vinculado_sai_do_universo(self, client, scoped):
        """A SECOND manual imóvel cannot be paired with a Vista row that already
        carries a link (one manual per Vista row)."""
        from tests.modules.imovel_hub.conftest import dados_row, registry_row

        reg = cenario(
            scoped, extra_registry=[registry_row("SW-0002", ativo_no_vista=False, origem_descoberta="manual")]
        )
        scoped.table("imovel_registry")._data[0]["vinculado_a"] = reg["vista"]["id"]
        scoped.table("imovel_dados")._data.append(dados_row("SW-0002", **ENDERECO_MANUAL))
        r = detectar(scoped)
        assert r["avaliados"] == 1 and candidatos(scoped) == []

    def test_restringe_aos_codigos_pedidos(self, client, scoped):
        from tests.modules.imovel_hub.conftest import dados_row, registry_row

        cenario(scoped, manual_dados=ENDERECO_MANUAL,
                extra_registry=[registry_row("SW-0002", ativo_no_vista=False, origem_descoberta="manual")])
        scoped.table("imovel_dados")._data.append(dados_row("SW-0002", **ENDERECO_MANUAL))
        detectar(scoped, codigos_manuais=["sw-0002"])
        assert [p["codigo_manual"] for p in candidatos(scoped)] == ["SW-0002"]

    def test_outra_org_nao_vaza(self, client, scoped):
        cenario(scoped, manual_dados=ENDERECO_MANUAL)
        for t in ("imovel_registry", "imoveis", "imovel_dados", "imovel_captacao"):
            for row in scoped.table(t)._data:
                row["org_id"] = "00000000-0000-4000-8000-000000000099"
        assert detectar(scoped)["avaliados"] == 0

    def test_nada_e_mesclado_so_a_tabela_de_candidatos_e_escrita(self, client, scoped):
        """No auto-merge anywhere: registry (incl. `vinculado_a`), captação,
        imovel_dados and the mirror are byte-identical after detection."""
        import copy

        cenario(scoped, manual_dados={**ENDERECO_MANUAL, **MATRICULA_CRI["manual_dados"]},
                vista_dados=MATRICULA_CRI["vista_dados"])
        antes = {t: copy.deepcopy(scoped.table(t)._data)
                 for t in ("imovel_registry", "imovel_captacao", "imovel_dados", "imoveis")}
        detectar(scoped)
        assert candidatos(scoped)
        for t, linhas in antes.items():
            assert scoped.table(t)._data == linhas, t
        assert all(r.get("vinculado_a") is None for r in scoped.table("imovel_registry")._data)


# ─── hooks: failure never fails the host write ────────────────────────────


def _falha(*_a, **_k):
    raise RuntimeError("detector exploded")


class TestHooks:
    def test_falha_na_deteccao_pos_sync_nao_falha_o_sync_e_e_logada(self, client, scoped, caplog):
        cenario(scoped)
        scoped.set_rpc_data("sweep_imovel_registry", [{"marcados_ativos": 1, "marcados_delistados": 0}])
        adapter = FakeVistaAdapter()
        adapter.add_imovel(Imovel(codigo="ONE9999", categoria="Casa"))

        class _Cliente:
            def schema(self, _n):
                return scoped

        with caplog.at_level(logging.ERROR, logger="app.modules.imovel_hub.duplicatas_service"):
            report = asyncio.run(
                ImovelSyncService(_Cliente(), adapter, duplicate_detector=_falha).sync(
                    ORG, with_detalhes=False
                )
            )
        assert report.complete is True and report.upserted == 1
        assert "detection failed after vista sync" in caplog.text
        assert any(r.exc_info for r in caplog.records)  # the traceback is kept

    def test_sync_completo_roda_a_deteccao_com_o_catalogo_novo(self, client, scoped):
        cenario(scoped, manual_dados=ENDERECO_MANUAL)
        scoped.set_rpc_data("sweep_imovel_registry", [{"marcados_ativos": 1, "marcados_delistados": 0}])
        chamadas = []

        class _Cliente:
            def schema(self, _n):
                return scoped

        asyncio.run(
            ImovelSyncService(
                _Cliente(), FakeVistaAdapter(),
                duplicate_detector=lambda c, o, codigos=None: chamadas.append((o, codigos)),
            ).sync(ORG, with_detalhes=False)
        )
        # an empty fake catalog still counts as a complete run
        assert chamadas == [(ORG, None)]

    def test_sync_incompleto_nao_roda_a_deteccao(self, client, scoped):
        cenario(scoped)
        chamadas = []

        class _Cliente:
            def schema(self, _n):
                return scoped

        class _Quebrado(FakeVistaAdapter):
            async def list_imoveis(self, **_k):
                raise RuntimeError("vista down")

        report = asyncio.run(
            ImovelSyncService(
                _Cliente(), _Quebrado(), duplicate_detector=lambda *a, **k: chamadas.append(a)
            ).sync(ORG, with_detalhes=False)
        )
        assert report.complete is False and chamadas == []

    @pytest.fixture
    def valores_novos(self):
        return {"titulo": "Casa", "endereco": {
            "cep": "06709-300", "logradouro": "Alameda Liverpool", "numero": "81",
            "bairro": "Reserva do Vianna", "cidade": "Cotia", "uf": "SP"}}

    def test_cadastro_manual_roda_a_deteccao_so_para_o_codigo_novo(self, client, scoped, valores_novos):
        scoped.set_table_data("imovel_registry", [])
        scoped.set_table_data("imovel_captacao", [])
        chamadas = []
        out = cap.registrar_manual(
            scoped, ORG, valores_novos, usuario_id=None,
            detector=lambda c, o, codigos=None: chamadas.append(codigos),
        )
        assert chamadas == [[out["codigo_norm"]]] and out["codigo_norm"] == "SW-0001"

    def test_edicao_manual_roda_a_deteccao(self, client, scoped):
        cenario(scoped)
        chamadas = []
        cap.atualizar_manual(
            scoped, ORG, "sw-0001", {"observacoes": "x"}, usuario_id=None,
            detector=lambda c, o, codigos=None: chamadas.append(codigos),
        )
        assert chamadas == [["SW-0001"]]

    def test_falha_na_deteccao_nao_falha_o_cadastro_nem_a_edicao(self, client, scoped, valores_novos, caplog):
        scoped.set_table_data("imovel_registry", [])
        scoped.set_table_data("imovel_captacao", [])
        with caplog.at_level(logging.ERROR, logger="app.modules.imovel_hub.duplicatas_service"):
            out = cap.registrar_manual(scoped, ORG, valores_novos, usuario_id=None, detector=_falha)
            assert out["fonte"] == "manual"
            cap.atualizar_manual(scoped, ORG, out["codigo_norm"], {"observacoes": "y"},
                                 usuario_id=None, detector=_falha)
        assert caplog.text.count("detection failed after manual") == 2

    def test_rota_de_cadastro_manual_dispara_a_deteccao_real(self, client, scoped):
        """End to end through the route: a manual imóvel registered with the
        same address as a Vista listing leaves a pending pair."""
        cenario(scoped, vista_dados={})
        scoped.set_table_data("imovel_registry", [r for r in scoped.table("imovel_registry")._data
                                                  if r["codigo_canonical"] == VISTA])
        scoped.set_table_data("imovel_dados", [])
        scoped.set_table_data("imovel_captacao", [])
        body = {"titulo": "Casa", "endereco": {
            "cep": "06709-300", "logradouro": "Alameda Liverpool", "numero": "81",
            "bairro": "Reserva do Vianna", "cidade": "Cotia", "uf": "SP"}}
        r = client.post("/api/imoveis/manuais", json=body, headers=auth())
        assert r.status_code == 201, r.text
        (par,) = candidatos(scoped)
        assert (par["codigo_manual"], par["codigo_vista"], par["score"]) == ("SW-0001", VISTA, 0.70)


# ─── routes ───────────────────────────────────────────────────────────────

URL = "/api/imoveis/duplicatas"


class TestRotas:
    def test_a_rota_alcanca_o_handler_e_nao_o_get_codigo(self, client, scoped):
        """One segment: `imoveis_router`'s `GET /{codigo}` would read it as the
        código "DUPLICATAS" (404 or an imóvel). The handler must win."""
        cenario(scoped, pares=[par_row(score=0.7)])
        r = client.get(URL, headers=auth())
        assert r.status_code == 200, r.text
        assert isinstance(r.json(), list)

    def test_declarada_antes_do_catch_all(self):
        from app.main import app

        paths = [getattr(r, "path", "") for r in app.routes]
        assert paths.index(URL) < paths.index("/api/imoveis/{codigo}")

    def test_lista_ordenada_por_score_com_resumo_dos_dois_lados(self, client, scoped):
        cenario(
            scoped, manual_dados=ENDERECO_MANUAL,
            manual_cap={"valor_venda": 1_500_000, "area_total": 300},
            espelho={"valor_venda": "1480000.00", "area_total": "298.50", "titulo": "Casa Vista"},
            pares=[par_row(score=0.6, id="00000000-0000-4000-8000-0000000000aa"),
                   par_row(score=0.9, vista="ONE1234", manual="SW-0001")],
        )
        itens = client.get(URL, headers=auth()).json()
        assert [i["score"] for i in itens] == [0.9, 0.6]
        item = itens[0]
        assert set(item) == {
            "id", "score", "sinais", "status", "detectado_em", "resolvido_por", "resolvido_em",
            "manual", "vista",
        }
        resumo = {"codigo", "titulo", "endereco_resumo", "valor_venda", "area_total", "foto_destaque"}
        assert set(item["manual"]) == set(item["vista"]) == resumo
        assert item["manual"]["codigo"] == "SW-0001" and item["manual"]["valor_venda"] == 1_500_000.0
        assert item["manual"]["endereco_resumo"].startswith("Alameda Liverpool, 81")
        assert item["vista"]["codigo"] == VISTA and item["vista"]["titulo"] == "Casa Vista"
        assert item["vista"]["area_total"] == 298.5 and item["vista"]["foto_destaque"] == "https://img/vista.jpg"
        assert item["sinais"] == [{"sinal": "matricula", "detalhe": "matrícula 79826"}]

    def test_filtro_de_status_default_pendente(self, client, scoped):
        cenario(scoped, pares=[par_row("pendente"), par_row("descartado", manual="SW-0001", vista="ONE1234")])
        assert [i["status"] for i in client.get(URL, headers=auth()).json()] == ["pendente"]
        assert [i["status"] for i in client.get(URL + "?status=descartado", headers=auth()).json()] == ["descartado"]

    def test_status_invalido_e_400(self, client, scoped):
        cenario(scoped)
        r = client.get(URL + "?status=qualquer", headers=auth())
        assert r.status_code == 400, r.text
        assert "status inválido" in r.text

    def test_outra_org_nao_aparece(self, client, scoped):
        cenario(scoped, pares=[par_row(org_id="00000000-0000-4000-8000-000000000099")])
        assert client.get(URL, headers=auth()).json() == []

    def test_descartar_marca_descartado_com_resolvido_por_e_em(self, client, scoped):
        p = par_row()
        cenario(scoped, pares=[p])
        r = client.post(f"{URL}/{p['id']}/descartar", headers=auth())
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "descartado" and body["resolvido_em"] and body["id"] == p["id"]
        assert candidatos(scoped)[0]["status"] == "descartado"
        # never re-suggested
        assert client.get(URL, headers=auth()).json() == []

    def test_descartar_duas_vezes_e_409_duplicata_ja_resolvida(self, client, scoped):
        p = par_row("descartado")
        cenario(scoped, pares=[p])
        r = client.post(f"{URL}/{p['id']}/descartar", headers=auth())
        assert r.status_code == 409 and r.json()["error"]["code"] == "duplicata_ja_resolvida"

    def test_descartar_confirmado_tambem_e_409(self, client, scoped):
        p = par_row("confirmado")
        cenario(scoped, pares=[p])
        assert client.post(f"{URL}/{p['id']}/descartar", headers=auth()).status_code == 409

    def test_descartar_desconhecido_e_404(self, client, scoped):
        cenario(scoped)
        assert client.post(f"{URL}/{'0' * 8}-0000-4000-8000-{'0' * 12}/descartar", headers=auth()).status_code == 404

    def test_imovel_traz_duplicatas_pendentes_dos_dois_lados(self, client, scoped, espelho_vista):
        cenario(scoped, pares=[par_row(score=0.8), par_row("descartado", manual="SW-0001", vista="ONE1234")])
        do_manual = client.get("/api/imoveis/SW-0001", headers=auth()).json()
        do_vista = client.get(f"/api/imoveis/{VISTA}", headers=auth()).json()
        esperado = [{"id": candidatos(scoped)[0]["id"], "outro_codigo": VISTA, "score": 0.8}]
        assert do_manual["duplicatas_pendentes"] == esperado
        assert do_vista["duplicatas_pendentes"] == [{**esperado[0], "outro_codigo": "SW-0001"}]
        assert do_manual["vinculo"] is None and do_vista["vinculo"] is None

    def test_imovel_sem_par_tem_lista_vazia(self, client, scoped, espelho_vista):
        cenario(scoped)
        assert client.get("/api/imoveis/SW-0001", headers=auth()).json()["duplicatas_pendentes"] == []

    def test_lista_aceita_possivel_duplicado(self, client, scoped, espelho_vista):
        """The filter reaches the catalog view as `possivel_duplicado = true`."""
        cenario(scoped)
        scoped.set_table_data("imoveis_catalogo", [
            {"org_id": ORG_ID, "codigo": "A", "possivel_duplicado": True, "data_atualizacao": "2026-10-01",
             "caracteristicas": []},
            {"org_id": ORG_ID, "codigo": "B", "possivel_duplicado": False, "data_atualizacao": "2026-10-02",
             "caracteristicas": []},
        ])
        todos = client.get("/api/imoveis", headers=auth()).json()
        so_dup = client.get("/api/imoveis?possivel_duplicado=true", headers=auth()).json()
        so_nao = client.get("/api/imoveis?possivel_duplicado=false", headers=auth()).json()
        assert {i["codigo"] for i in todos["items"]} == {"A", "B"}
        assert [i["codigo"] for i in so_dup["items"]] == ["A"]
        assert [i["codigo"] for i in so_nao["items"]] == ["B"]


# ─── migration 228 ────────────────────────────────────────────────────────

from pathlib import Path  # noqa: E402

MIGRATIONS = Path(__file__).resolve().parents[3] / "migrations"
# Located by name, never by number (SW numbers are taken at integrate time).
(MIGRATION,) = sorted(MIGRATIONS.glob("*_imovel_duplicatas.sql"))


class TestMigracao:
    def test_view_e_arms_carregam_possivel_duplicado_apos_fonte(self):
        sql = "\n".join(l for l in MIGRATION.read_text().splitlines() if not l.strip().startswith("--"))
        assert sql.count("AS possivel_duplicado") == 2
        assert sql.count("'pendente'") >= 2

    def test_os_dois_bracos_da_view_viva_tem_as_mesmas_colunas_na_mesma_ordem(self):
        """Drift guard for the CURRENT `imoveis_catalogo` (228 supersedes 226's
        definition): mirror columns, then `fonte`, then `possivel_duplicado`."""
        from tests.modules.imovel_hub.test_imovel_captacao_manual import _bracos_da_view

        vista, manual_arm = _bracos_da_view(MIGRATION)
        assert [re.sub(r"^i\.", "", i) for i in vista[:-2]] == list(cap.MIRROR_COLUMNS)
        for arm in (vista, manual_arm):
            assert arm[-2].endswith("AS fonte") and arm[-1].endswith("AS possivel_duplicado")
        assert len(vista) == len(manual_arm) == len(cap.MIRROR_COLUMNS) + 2

    def test_view_continua_security_invoker(self):
        assert "security_invoker = true" in MIGRATION.read_text()

    def test_vinculo_tem_unique_parcial_e_check_contra_si_mesmo(self):
        sql = MIGRATION.read_text()
        assert "UNIQUE INDEX IF NOT EXISTS uq_imovel_registry_vinculado_a" in sql
        assert "WHERE vinculado_a IS NOT NULL" in sql
        assert "CHECK (vinculado_a IS NULL OR vinculado_a <> id)" in sql


# ─── strict 401 ───────────────────────────────────────────────────────────

_ID = "00000000-0000-4000-8000-0000000000aa"


@pytest.mark.parametrize(
    "metodo,caminho",
    [
        ("get", "/api/imoveis/duplicatas"),
        ("get", "/api/imoveis/duplicatas?status=descartado"),
        ("post", f"/api/imoveis/duplicatas/{_ID}/descartar"),
        ("post", f"/api/imoveis/duplicatas/{_ID}/vincular"),
        ("post", "/api/imoveis/SW-0001/desvincular"),
        ("get", "/api/imoveis?possivel_duplicado=true"),
    ],
)
def test_novas_rotas_exigem_auth_com_401_estrito(anon_client, metodo, caminho):
    resp = getattr(anon_client, metodo)(caminho)
    assert resp.status_code == 401, f"{metodo.upper()} {caminho} -> {resp.status_code}: {resp.text}"
