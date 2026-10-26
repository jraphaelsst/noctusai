"""F113 — a tipo's declared requirements are checked BEFORE the paid call.

`cnd_federal` (Receita `receita-federal/pgfn`) refuses a CPF lookup without
`birthdate` (606) — billed, then retried as 2ª via, billed again. The pipeline
must not call InfoSimples when the consulta lacks a field the tipo declares
(`requer_campos`): the cell parks as a `dados_parte` pendência with a pt-BR
message naming the field. A provider "obrigatório" error on a tipo that does
NOT declare it is the same pendência (never `erro`) plus a WARNING.

Real paths only; httpx is the one thing faked. Synthetic data only.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from noctusai_lib.integrations.storage import FakeStorageBackend
from noctusai_lib.testing import MockSupabaseClient

from app.modules.card_hub import certidoes_partes_service as partes
from app.modules.certidoes import service
from app.modules.certidoes.registry import (
    MSG_REQUER_GOVBR,
    PENDENCIA_CREDENCIAL_GOVBR,
    PENDENCIA_DADOS_PARTE,
    campos_do_erro,
    config_for,
    e_erro_login_govbr,
    e_erro_parametro_obrigatorio,
    e_pendencia,
    msg_falta_dados,
    pendencia_pre_chamada,
    tipo_de_pendencia,
)
from tests.modules.test_certidoes_service import (
    _consulta_row,
    _db,
    _noop_analyze,
    _noop_extract_text,
    _resultado,
)

NOME = "Pessoa Sintetica Teste"
MSG_BIRTHDATE = (
    "O parâmetro 'birthdate' é obrigatório para a consulta por CPF. "
    "Deve estar no formato 'aaaa-mm-dd'."
)
MSG_TRF3 = (
    "São necessários os seguintes parâmetros adicionais para solicitar esta "
    "certidão: 'nome_mae', 'birthdate', 'tipo_documento' e 'documento'."
)


def _resposta_606(erro: str) -> dict:
    return {
        "code": 606,
        "code_message": "Parâmetros obrigatórios não foram enviados. Por favor, "
        "verifique a documentação de uso do serviço.",
        "errors": [erro],
        "header": {"price": 0.3},
    }


class _Http:
    """httpx at the boundary: records every request, answers `resposta`."""

    def __init__(self, resposta: dict):
        self.resposta = resposta
        self.calls: list[dict] = []

    async def get(self, url, **kw):
        self.calls.append({"url": url, **kw})
        r = MagicMock()
        r.json.return_value = self.resposta
        return r

    post = get


def _seed(tipo="cnd_federal", rid="r-1", **consulta):
    c = _consulta_row(nome=NOME, **consulta)
    return c, _db(
        certidao_consultas=[c],
        certidao_resultados=[_resultado(tipo=tipo, id=rid, status="na_fila")],
    )


def _row(db, rid="r-1"):
    return db.table("certidao_resultados").select("*").eq("id", rid).execute().data[0]


async def _run(cfg, consulta, db, http, rid="r-1"):
    await service._process_single_certidao(
        cfg, consulta, "tok", db, rid, http, FakeStorageBackend(),
        analyze=_noop_analyze, extract_text=_noop_extract_text,
        core_db=MockSupabaseClient(schema="public"),
    )


class TestDeclaracao:
    def test_cnd_federal_declara_data_de_nascimento_so_para_cpf(self):
        assert config_for("cnd_federal")["requer_campos"] == {"cpf": ("data_nascimento",)}

    def test_cnpj_nao_precisa_de_data_de_nascimento(self):
        consulta = {"tipo_documento": "cnpj", "org_id": "o", "nome": NOME}
        assert pendencia_pre_chamada(config_for("cnd_federal"), consulta) is None

    def test_mensagem_nomeia_o_campo_e_a_pessoa(self):
        msg = pendencia_pre_chamada(
            config_for("cnd_federal"), {"tipo_documento": "cpf", "org_id": "o", "nome": NOME},
        )
        assert msg == (
            f"Falta data de nascimento de {NOME} — preencha no cadastro ou envie um documento"
        )


class TestSemDataDeNascimento:
    @pytest.mark.asyncio
    async def test_nao_chama_infosimples_e_fica_pendente(self):
        consulta, db = _seed(data_nascimento=None)
        http = _Http(_resposta_606(MSG_BIRTHDATE))
        await _run(config_for("cnd_federal"), consulta, db, http)
        assert http.calls == []
        row = _row(db)
        assert row["status"] == "pendente"
        assert "data de nascimento" in row["erro_mensagem"] and NOME in row["erro_mensagem"]
        assert tipo_de_pendencia(row) == PENDENCIA_DADOS_PARTE
        c = db.table("certidao_consultas").select("status").eq("id", "consulta-001").execute().data[0]
        assert c["status"] != "processando"

    def test_celula_expoe_a_pendencia(self):
        from datetime import date

        row = {"id": "r-1", "status": "pendente", "tipo": "cnd_federal",
               "erro_mensagem": msg_falta_dados(["data_nascimento"], NOME)}
        cel = partes.montar_celula("cnd_federal", row, date(2026, 10, 26), 30)
        assert cel["pendencia"] == PENDENCIA_DADOS_PARTE
        assert cel["erro_mensagem"] == row["erro_mensagem"]


class TestComDataDeNascimento:
    @pytest.mark.asyncio
    async def test_chama_com_birthdate(self):
        consulta, db = _seed(data_nascimento="1985-04-12")
        # A definitive 4xx ends the fetch after one call; the call itself is the point.
        http = _Http({"code": 401, "code_message": "x", "errors": []})
        await _run(config_for("cnd_federal"), consulta, db, http)
        assert len(http.calls) == 1
        assert http.calls[0]["params"]["birthdate"] == "1985-04-12"
        assert not e_pendencia(_row(db))


class TestClassGuardObrigatorio:
    @pytest.mark.asyncio
    async def test_obrigatorio_nao_declarado_vira_pendencia_e_loga(self, caplog):
        consulta, db = _seed(tipo="trf3")
        http = _Http(_resposta_606(MSG_TRF3))
        with caplog.at_level("WARNING"):
            await _run(config_for("trf3"), consulta, db, http)
        # A missing parameter never appears on a retry: ONE billed call.
        assert len(http.calls) == 1
        row = _row(db)
        assert row["status"] == "pendente" and tipo_de_pendencia(row) == PENDENCIA_DADOS_PARTE
        assert "nome da mãe" in row["erro_mensagem"] and "data de nascimento" in row["erro_mensagem"]
        assert "undeclared in requer_campos" in caplog.text
        assert "nome_mae" in caplog.text and "data_nascimento" in caplog.text

    @pytest.mark.asyncio
    async def test_606_nao_pede_segunda_via(self):
        # Declared field present but the source still refuses (bad format):
        # pendência, and no 2ª-via / retry rebilling.
        consulta, db = _seed(data_nascimento="15/01/1990")
        http = _Http(_resposta_606(MSG_BIRTHDATE))
        await _run(config_for("cnd_federal"), consulta, db, http)
        assert len(http.calls) == 1
        assert tipo_de_pendencia(_row(db)) == PENDENCIA_DADOS_PARTE

    def test_reconhecimento(self):
        assert e_erro_parametro_obrigatorio(_resposta_606(MSG_BIRTHDATE))
        assert not e_erro_parametro_obrigatorio({"code": 618, "code_message": "sobrecarregado"})
        assert not e_erro_parametro_obrigatorio(None)
        assert campos_do_erro(_resposta_606(MSG_BIRTHDATE)) == ["data_nascimento"]
        assert campos_do_erro(_resposta_606(MSG_TRF3)) == [
            "nome_mae", "data_nascimento", "documento_identificacao",
        ]

    def test_govbr_604_tambem_e_login(self):
        assert e_erro_login_govbr({
            "code": 604,
            "code_message": "A consulta não foi validada antes de pesquisar a fonte de origem.",
            "errors": ["Passe a informar os parâmetros 'login_cpf' e 'login_senha'."],
        })


class TestReconhecimentoDePendencia:
    def test_erro_nao_e_pendencia(self):
        assert tipo_de_pendencia(
            {"status": "erro", "erro_mensagem": msg_falta_dados(["data_nascimento"], NOME)}
        ) is None

    def test_govbr_continua(self):
        assert tipo_de_pendencia(
            {"status": "pendente", "erro_mensagem": MSG_REQUER_GOVBR}
        ) == PENDENCIA_CREDENCIAL_GOVBR

    def test_mensagem_qualquer_nao_e_pendencia(self):
        assert tipo_de_pendencia({"status": "pendente", "erro_mensagem": "Falta algo"}) is None
