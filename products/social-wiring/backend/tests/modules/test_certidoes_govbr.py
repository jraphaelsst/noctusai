"""Dívida Ativa SP needs a GOV.BR login (InfoSimples `pge/sp/cndt`, else 606).

Without the org's credential the pipeline must NOT call (and be billed by)
InfoSimples: the cell parks as PENDING with a pt-BR reason and stays uploadable.
With it, the login is sent in the POST body, never in a URL and never stored.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from noctusai_lib.integrations.storage import FakeStorageBackend
from noctusai_lib.testing import MockSupabaseClient

from app.modules.card_hub import certidoes_partes_service as partes
from app.modules.certidoes import aprendizado, credentials, service
from app.modules.certidoes.registry import (
    MSG_REQUER_GOVBR,
    PENDENCIA_CREDENCIAL_GOVBR,
    config_for,
    e_pendencia_de_credencial,
)
from app.services.api_keys_store import MANAGED_API_KEYS, get_spec
from tests.modules.test_certidoes_service import (
    ORG,
    _api_ok,
    _consulta_row,
    _db,
    _noop_analyze,
    _noop_extract_text,
    _resultado,
)

_CRED = "app.modules.certidoes.credentials.resolve_api_key"
CPF, SENHA = "98765432100", "s3nh4-super-secreta"
CFG = config_for("divida_ativa_sp")


def _com_login(name, org_id=None):
    return {"infosimples_govbr_cpf": CPF, "infosimples_govbr_senha": SENHA}.get(name)


def _sem_login(name, org_id=None):
    return None


class _Http:
    """Records GET vs POST — httpx is the only thing faked."""

    def __init__(self):
        self.gets: list[dict] = []
        self.posts: list[dict] = []

    async def post(self, url, **kw):
        self.posts.append({"url": url, **kw})
        r = MagicMock()
        r.json.return_value = {"code": 606, "code_message": "x"}
        return r

    async def get(self, url, **kw):
        self.gets.append({"url": url, **kw})
        r = MagicMock()
        r.json.return_value = {"code": 606, "code_message": "x"}
        return r


def _seed(status="pendente", **over):
    return _db(
        certidao_consultas=[_consulta_row()],
        certidao_resultados=[_resultado(tipo="divida_ativa_sp", id="r-da", ordem=10, status=status, **over)],
    )


def _row(db):
    return db.table("certidao_resultados").select("*").eq("id", "r-da").execute().data[0]


async def _run(db, http):
    await service._process_single_certidao(
        CFG, _consulta_row(), "tok", db, "r-da", http, FakeStorageBackend(),
        analyze=_noop_analyze, extract_text=_noop_extract_text,
        core_db=MockSupabaseClient(schema="public"),
    )


class TestSemCredencial:
    @pytest.mark.asyncio
    async def test_nao_chama_infosimples_e_fica_pendente_com_mensagem(self):
        db, http = _seed(), _Http()
        with patch(_CRED, side_effect=_sem_login):
            await _run(db, http)
        assert http.gets == [] and http.posts == []
        row = _row(db)
        assert row["status"] == "pendente"
        assert row["erro_mensagem"] == MSG_REQUER_GOVBR
        assert "GOV.BR" in MSG_REQUER_GOVBR and "PDF" in MSG_REQUER_GOVBR
        assert e_pendencia_de_credencial(row)

    @pytest.mark.asyncio
    async def test_meia_credencial_nao_conta(self):
        db, http = _seed(), _Http()
        only_cpf = lambda n, o=None: CPF if n == "infosimples_govbr_cpf" else None  # noqa: E731
        with patch(_CRED, side_effect=only_cpf):
            await _run(db, http)
        assert http.posts == [] and _row(db)["erro_mensagem"] == MSG_REQUER_GOVBR

    @pytest.mark.asyncio
    async def test_consulta_nao_fica_processando_para_sempre(self):
        db, http = _seed(), _Http()
        with patch(_CRED, side_effect=_sem_login):
            await _run(db, http)
        c = db.table("certidao_consultas").select("status").eq("id", "consulta-001").execute().data[0]
        assert c["status"] != "processando"

    @pytest.mark.asyncio
    async def test_resultado_travado_por_humano_nao_e_tocado(self):
        db, http = _seed(status="sucesso", resultado_origem="manual", erro_mensagem=None), _Http()
        with patch(_CRED, side_effect=_sem_login):
            await _run(db, http)
        row = _row(db)
        assert row["status"] == "sucesso" and row["erro_mensagem"] is None
        assert http.posts == []

    def test_celula_expoe_pendencia_e_continua_pendente(self):
        from datetime import date

        row = {"id": "r-da", "status": "pendente", "erro_mensagem": MSG_REQUER_GOVBR,
               "tipo": "divida_ativa_sp"}
        cel = partes.montar_celula("divida_ativa_sp", row, date(2026, 10, 1), 30)
        assert cel["status"] == "pendente"
        assert cel["pendencia"] == PENDENCIA_CREDENCIAL_GOVBR
        assert cel["erro_mensagem"] == MSG_REQUER_GOVBR
        assert partes.montar_celula("divida_ativa_sp", None, date(2026, 10, 1), 30)["pendencia"] is None

    def test_erro_real_nao_vira_pendencia(self):
        assert not e_pendencia_de_credencial(
            {"status": "erro", "erro_mensagem": MSG_REQUER_GOVBR}
        )


class TestComCredencial:
    @pytest.mark.asyncio
    async def test_login_vai_no_corpo_do_post_nunca_na_url(self):
        db, http = _seed(), _Http()
        with patch(_CRED, side_effect=_com_login):
            await _run(db, http)
        assert http.gets == []
        sent = http.posts[0]
        assert sent["url"].endswith("pge/sp/cndt")
        assert sent["data"]["login_cpf"] == CPF and sent["data"]["login_senha"] == SENHA
        assert "params" not in sent

    @pytest.mark.asyncio
    async def test_segredo_nunca_persiste_na_observacao_nem_no_resultado(self):
        db, http = _seed(), _Http()
        with patch(_CRED, side_effect=_com_login):
            await _run(db, http)
        gravado = db.table(aprendizado.TABELA).select("*").execute().data
        assert gravado, "the watcher must have observed the call"
        blob = repr(gravado) + repr(_row(db))
        assert SENHA not in blob and CPF not in blob
        # key NAMES are fine, values are not
        assert "login_senha" in gravado[0]["params"]["chaves_enviadas"]


class TestCredencialNaLoja:
    def test_ambas_sao_chaves_gerenciadas_secretas(self):
        for k in (credentials.INFOSIMPLES_GOVBR_CPF, credentials.INFOSIMPLES_GOVBR_SENHA):
            assert k in MANAGED_API_KEYS
            spec = get_spec(k)
            assert spec.is_secret and spec.input_type == "password"

    def test_govbr_login_exige_o_par(self):
        with patch(_CRED, side_effect=_com_login):
            assert credentials.govbr_login(ORG) == (CPF, SENHA)
        with patch(_CRED, side_effect=_sem_login):
            assert credentials.govbr_login(ORG) is None
