"""Certidão -> party profile feed (CONTRACT §1.7, `certidoes.feed_parte`).

PF -> `clientes` through the one write chokepoint
(`identidade_extracao_service.aplicar_campos_ao_cliente`), PJ -> `empresas`
through the `dados_*` group provenance; both fill-empty / conflict-on-
disagree, origem `certidao`.
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from noctusai_lib.integrations.storage import FakeStorageBackend
from noctusai_lib.testing import MockSupabaseClient

from app.modules.certidoes import feed_parte, service
from app.modules.card_hub.proveniencia import fontes
from tests.modules.test_certidoes_service import (
    ORG,
    CONFIG_FEDERAL,
    _FakeHttp,
    _api_ok,
    _consulta_row,
    _noop_analyze,
    _noop_extract_text,
    _resultado,
)

CPF = "41295423898"
CNPJ = "11222333000181"


def _db(**tables) -> MockSupabaseClient:
    client = MockSupabaseClient(schema="social_wiring")
    base = {
        "clientes": [], "empresas": [], "atendimentos": [], "atendimento_partes": [],
        "cliente_campo_conflitos": [], "empresa_campo_conflitos": [],
        "cliente_empresa_participacoes": [],
    }
    for nome, rows in {**base, **tables}.items():
        client.set_table_data(nome, rows)
    return client


def _cliente(cid: str, **over) -> dict:
    row = {"id": cid, "org_id": ORG, "nome": "Fulano", "nome_oficial": None, "cpf": None,
           "data_nascimento": None}
    row.update(over)
    return row


def _empresa(eid: str, **over) -> dict:
    row = {
        "id": eid, "org_id": ORG, "cnpj": CNPJ, "razao_social": None,
        "situacao_cadastral": None, "data_situacao_cadastral": None,
        "dados_origem": None, "dados_documento_id": None, "dados_em": None,
        "dados_confirmado_por": None, "dados_confirmado_em": None,
    }
    row.update(over)
    return row


def _resposta_pf(**over) -> dict:
    item = {
        "nome": "FULANO DE TAL", "cpf": "412.954.238-98", "normalizado_cpf": CPF,
        "emissao_data": "01/10/2026", "site_receipt": "https://x/f.pdf",
    }
    item.update(over)
    return {"code": 200, "data": [item]}


def _consulta_pf(cid: str, **over) -> dict:
    return {"id": "consulta-001", "tipo_documento": "cpf", "documento": CPF,
            "cliente_id": cid, "empresa_id": None, **over}


def _consulta_pj(eid: str, **over) -> dict:
    return {"id": "consulta-002", "tipo_documento": "cnpj", "documento": CNPJ,
            "cliente_id": None, "empresa_id": eid, **over}


def _linha(db, tabela, id_):
    return db.table(tabela).select("*").eq("id", id_).execute().data[0]


class TestFonteRegistrada:
    def test_a_fonte_certidao_esta_no_catalogo(self):
        f = fontes.FONTES["certidao"]
        assert f.origens == frozenset({feed_parte.ORIGEM})
        assert fontes.Entrada.CERTIDAO_ROBO in f.entradas
        assert {"nome", "cpf", "data_nascimento"} <= f.campos_sem_capacidade
        assert fontes.resolver_extrator(f) is feed_parte.alimentar_parte

    def test_so_a_cnd_federal_alimenta(self):
        assert feed_parte.TIPOS_FONTE == frozenset({"cnd_federal"})


class TestPF:
    def test_preenche_campos_vazios_com_proveniencia_de_maquina(self):
        cid = str(uuid4())
        db = _db(clientes=[_cliente(cid)])
        out = feed_parte.alimentar_parte(db, ORG, _consulta_pf(cid), "cnd_federal", _resposta_pf())
        row = _linha(db, "clientes", cid)
        assert set(out["aplicados"]) == {"nome_oficial", "cpf"}
        assert (row["nome_oficial"], row["cpf"]) == ("FULANO DE TAL", CPF)
        assert row["nome_oficial_origem"] == "certidao" == row["cpf_origem"]
        assert row["nome_oficial_documento_id"] is None
        assert row["nome_oficial_confirmado_por"] is None and row["nome_oficial_confirmado_em"] is None
        assert row["nome_oficial_em"] and row["cpf_em"]
        assert out["conflitos"] == []

    def test_data_nascimento_so_quando_a_resposta_traz(self):
        cid = str(uuid4())
        db = _db(clientes=[_cliente(cid)])
        feed_parte.alimentar_parte(db, ORG, _consulta_pf(cid), "cnd_federal", _resposta_pf())
        assert _linha(db, "clientes", cid)["data_nascimento"] is None
        db2 = _db(clientes=[_cliente(cid)])
        out = feed_parte.alimentar_parte(
            db2, ORG, _consulta_pf(cid), "cnd_federal", _resposta_pf(nascimento="03/02/1980"),
        )
        assert "data_nascimento" in out["aplicados"]
        assert _linha(db2, "clientes", cid)["data_nascimento"] == "1980-02-03"

    def test_discordancia_abre_conflito_e_nao_sobrescreve(self):
        cid = str(uuid4())
        db = _db(clientes=[_cliente(
            cid, nome_oficial="BELTRANO DA SILVA", nome_oficial_origem="manual",
            nome_oficial_confirmado_em="2026-09-01T00:00:00+00:00",
        )])
        out = feed_parte.alimentar_parte(db, ORG, _consulta_pf(cid), "cnd_federal", _resposta_pf())
        assert _linha(db, "clientes", cid)["nome_oficial"] == "BELTRANO DA SILVA"
        assert "nome_oficial" not in out["aplicados"]
        conflitos = db.table("cliente_campo_conflitos").select("*").execute().data
        assert [c["campo"] for c in conflitos] == ["nome_oficial"]
        assert conflitos[0]["valor_proposto"] == "FULANO DE TAL"
        assert conflitos[0]["origem_proposto"] == "certidao"
        assert conflitos[0]["status"] == "pendente"
        assert [c["campo"] for c in out["conflitos"]] == ["nome_oficial"]

    def test_mesmo_valor_nao_faz_nada(self):
        cid = str(uuid4())
        db = _db(clientes=[_cliente(
            cid, nome_oficial="FULANO DE TAL", nome_oficial_origem="rg", cpf=CPF, cpf_origem="rg",
        )])
        out = feed_parte.alimentar_parte(db, ORG, _consulta_pf(cid), "cnd_federal", _resposta_pf())
        assert out["aplicados"] == [] and out["conflitos"] == []
        assert _linha(db, "clientes", cid)["nome_oficial_origem"] == "rg"

    def test_documento_da_resposta_diferente_da_consulta_nao_escreve(self):
        cid = str(uuid4())
        db = _db(clientes=[_cliente(cid)])
        out = feed_parte.alimentar_parte(
            db, ORG, _consulta_pf(cid), "cnd_federal",
            _resposta_pf(normalizado_cpf="52998224725", cpf="529.982.247-25"),
        )
        assert out["aviso"] == "documento_divergente" and out["aplicados"] == []
        assert _linha(db, "clientes", cid)["nome_oficial"] is None

    @pytest.mark.parametrize("tipo", ["trf3", "cnd_trabalhista_tst", "cenprot"])
    def test_outros_tipos_nao_alimentam(self, tipo):
        cid = str(uuid4())
        db = _db(clientes=[_cliente(cid)])
        out = feed_parte.alimentar_parte(db, ORG, _consulta_pf(cid), tipo, _resposta_pf())
        assert out["aplicados"] == [] and _linha(db, "clientes", cid)["nome_oficial"] is None

    def test_consulta_sem_parte_ou_sem_resposta_e_noop(self):
        cid = str(uuid4())
        db = _db(clientes=[_cliente(cid)])
        assert feed_parte.alimentar_parte(
            db, ORG, _consulta_pf(cid, cliente_id=None), "cnd_federal", _resposta_pf(),
        )["aplicados"] == []
        assert feed_parte.alimentar_parte(
            db, ORG, _consulta_pf(cid), "cnd_federal", None,
        )["aplicados"] == []

    def test_nunca_propaga_falha_do_banco(self):
        class _Quebrado:
            def table(self, *_a, **_k):
                raise RuntimeError("db fora do ar")

        out = feed_parte.alimentar_parte(
            _Quebrado(), ORG, _consulta_pf(str(uuid4())), "cnd_federal", _resposta_pf(),
        )
        assert out["aviso"] == "falha" and out["aplicados"] == []


class TestPJ:
    def test_preenche_razao_e_situacao_quando_o_grupo_nao_tem_proveniencia(self):
        eid = str(uuid4())
        db = _db(empresas=[_empresa(eid)])
        consulta = _consulta_pj(eid, situacao_cadastral="ativa", data_situacao="2020-05-01")
        out = feed_parte.alimentar_parte(
            db, ORG, consulta, "cnd_federal",
            {"code": 200, "data": [{"razao_social": "EMPRESA XYZ LTDA", "normalizado_cnpj": CNPJ}]},
            resultado_id="r1",
        )
        row = _linha(db, "empresas", eid)
        assert set(out["aplicados"]) == {"razao_social", "situacao_cadastral", "data_situacao_cadastral"}
        assert (row["razao_social"], row["situacao_cadastral"], row["data_situacao_cadastral"]) == (
            "EMPRESA XYZ LTDA", "ativa", "2020-05-01",
        )
        assert row["dados_origem"] == "certidao"
        assert row["dados_documento_id"] is None and row["dados_confirmado_em"] is None

    def test_grupo_com_proveniencia_nao_e_restampado_nem_preenchido(self):
        """A confirmed Cartão CNPJ must not be demoted to a machine-pending
        certidão read: an empty field is left for its owner."""
        eid = str(uuid4())
        db = _db(empresas=[_empresa(
            eid, razao_social="EMPRESA XYZ LTDA", dados_origem="cartao_cnpj",
            dados_confirmado_em="2026-09-01T00:00:00+00:00",
        )])
        out = feed_parte.alimentar_parte(
            db, ORG, _consulta_pj(eid, situacao_cadastral="ativa"), "cnd_federal",
            {"code": 200, "data": [{"razao_social": "EMPRESA XYZ LTDA", "normalizado_cnpj": CNPJ}]},
        )
        row = _linha(db, "empresas", eid)
        assert out["aplicados"] == []
        assert row["dados_origem"] == "cartao_cnpj" and row["situacao_cadastral"] is None
        assert row["dados_confirmado_em"] == "2026-09-01T00:00:00+00:00"

    def test_discordancia_abre_conflito_de_empresa(self):
        eid = str(uuid4())
        db = _db(empresas=[_empresa(eid, razao_social="OUTRA NOME LTDA", dados_origem="cartao_cnpj")])
        out = feed_parte.alimentar_parte(
            db, ORG, _consulta_pj(eid), "cnd_federal",
            {"code": 200, "data": [{"razao_social": "EMPRESA XYZ LTDA", "normalizado_cnpj": CNPJ}]},
            resultado_id="r1",
        )
        assert _linha(db, "empresas", eid)["razao_social"] == "OUTRA NOME LTDA"
        [c] = db.table("empresa_campo_conflitos").select("*").execute().data
        assert (c["campo"], c["valor_proposto"], c["origem_proposto"], c["fonte_id"]) == (
            "razao_social", "EMPRESA XYZ LTDA", "certidao", "r1",
        )
        assert len(out["conflitos"]) == 1

    def test_razao_truncada_pelo_crednet_nao_e_discordancia(self):
        eid = str(uuid4())
        db = _db(empresas=[_empresa(eid, razao_social="EMPRESA XYZ", dados_origem="serasa_crednet")])
        out = feed_parte.alimentar_parte(
            db, ORG, _consulta_pj(eid), "cnd_federal",
            {"code": 200, "data": [{"razao_social": "EMPRESA XYZ COMERCIO LTDA",
                                    "normalizado_cnpj": CNPJ}]},
        )
        assert out["conflitos"] == []
        assert db.table("empresa_campo_conflitos").select("*").execute().data == []

    def test_cnpj_divergente_nao_escreve(self):
        eid = str(uuid4())
        db = _db(empresas=[_empresa(eid)])
        out = feed_parte.alimentar_parte(
            db, ORG, _consulta_pj(eid), "cnd_federal",
            {"code": 200, "data": [{"razao_social": "X", "normalizado_cnpj": "99999999000199"}]},
        )
        assert out["aviso"] == "documento_divergente"
        assert _linha(db, "empresas", eid)["razao_social"] is None


class TestPipelineAlimentaAParte:
    """End to end through `_process_single_certidao`: a successful Receita
    emission lands on the party it is linked to."""

    @pytest.mark.asyncio
    async def test_cnd_federal_com_sucesso_preenche_o_cliente(self):
        cid = str(uuid4())
        consulta = _consulta_row(cliente_id=cid, documento=CPF)
        db = _db(
            clientes=[_cliente(cid)], certidao_consultas=[consulta],
            certidao_resultados=[_resultado()],
        )
        http = _FakeHttp(
            _api_ok(data=[{
                "site_receipt": "https://x/f.pdf", "nome": "FULANO DE TAL",
                "normalizado_cpf": CPF, "emissao_data": "01/10/2026",
            }]),
            file_body=b"%PDF-1.4 real",
        )
        await service._process_single_certidao(
            CONFIG_FEDERAL, consulta, "tok", db, "resultado-001", http, FakeStorageBackend(),
            analyze=_noop_analyze, extract_text=_noop_extract_text,
            core_db=MockSupabaseClient(schema="public"),
        )
        row = _linha(db, "clientes", cid)
        assert row["nome_oficial"] == "FULANO DE TAL" and row["nome_oficial_origem"] == "certidao"
        resultado = _linha(db, "certidao_resultados", "resultado-001")
        assert resultado["status"] == "sucesso" and resultado["emitida_em"] == "2026-10-01"

    @pytest.mark.asyncio
    async def test_falha_no_feed_nunca_derruba_a_certidao(self):
        cid = str(uuid4())
        consulta = _consulta_row(cliente_id=cid, documento=CPF)
        # No `clientes` table at all in the seeded data -> the feed's read has
        # nothing; the certidão must still land `sucesso`.
        db = _db(certidao_consultas=[consulta], certidao_resultados=[_resultado()])
        http = _FakeHttp(
            _api_ok(data=[{"site_receipt": "https://x/f.pdf", "nome": "X Y",
                           "normalizado_cpf": CPF}]),
            file_body=b"%PDF-1.4 real",
        )
        await service._process_single_certidao(
            CONFIG_FEDERAL, consulta, "tok", db, "resultado-001", http, FakeStorageBackend(),
            analyze=_noop_analyze, extract_text=_noop_extract_text,
            core_db=MockSupabaseClient(schema="public"),
        )
        assert _linha(db, "certidao_resultados", "resultado-001")["status"] == "sucesso"
