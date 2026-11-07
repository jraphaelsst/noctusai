"""Certidão emission — the request each tipo sends and how every REAL vendor
answer is handled.

Two layers:

1. Committed, synthetic: the vendor answers below are the VERBATIM prod
   responses the emission watcher recorded (2026-11, `certidao_emissao_
   observacoes`), with the document numbers masked. They pin what the pipeline
   does with each one — retry or not, 2ª via or not, what the operator reads.
2. Real-file (opt-in, never committed data): when the private extraction mirror
   (`~/.noctusai/private/extractions`, or `$NOC_REAL_EXTRACTIONS_DIR`) exists,
   party data (CPF + birth date printed on real RG/CNH documents) is read from
   it IN MEMORY and pushed through the real request builders. Values are never
   asserted-on by literal, never printed, never written anywhere; the test
   skips when the mirror is absent (CI).

httpx is the only thing faked.
"""
from __future__ import annotations

import glob
import json
import os
import re
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from noctusai_lib.integrations.storage import FakeStorageBackend
from noctusai_lib.testing import MockSupabaseClient

from app.modules.certidoes import service
from app.modules.certidoes.registry import (
    CERTIDOES_CONFIG,
    MSG_API_PAUSADA,
    MSG_MUITAS_TENTATIVAS,
    MSG_SEM_SALDO,
    MSG_TOKEN_RECUSADO,
    PARAM_BUILDERS,
    SEGREDOS_DE_PARAMS,
    config_for,
    falha_de_conta_ou_fonte,
    pendencia_pre_chamada,
)
from tests.modules.test_certidoes_service import (
    _consulta_row,
    _db,
    _noop_analyze,
    _noop_extract_text,
    _resultado,
)

_CRED = "app.modules.certidoes.credentials.resolve_api_key"

# ---- verbatim prod answers (masked) ---------------------------------------

R_615_PAUSADA = {
    "code": 615,
    "code_message": "O site ou aplicativo de origem parece estar indisponível.",
    "errors": [
        "A API foi pausada temporariamente. O motivo mais provável para isso ter sido feito "
        "é instabilidade na fonte de origem. Se você notou que a fonte de origem está se "
        "comportando normalmente, entre em contato com o suporte via email."
    ],
}
R_615_FONTE = {
    "code": 615,
    "code_message": "O site ou aplicativo de origem parece estar indisponível.",
    "errors": [],
}
R_603_SALDO = {
    "code": 603,
    "code_message": "O token informado não tem autorização de acesso ao serviço. Verifique se "
    "ele continua ativo e se ele não possui algum limite de uso especificado.",
    "errors": ["A conta está sem saldo. Adicione saldo para conseguir usar a API."],
}
R_603_TOKEN = {**R_603_SALDO, "errors": []}
R_608_TRF = {
    "code": 608,
    "code_message": "Os parâmetros foram recusados pelo site ou aplicativo de origem que "
    "processou esta consulta.",
    "errors": [
        "Os dados enviados foram recusados pelo site do TRF3 devido ao envio de muitas "
        "tentativas em pouco tempo desse mesmo CPF/CNPJ. Tente novamente mais tarde."
    ],
}
R_618 = {
    "code": 618,
    "code_message": "O site ou aplicativo de origem está sobrecarregado. Tente novamente em "
    "alguns instantes.",
    "errors": [],
}
R_611 = {
    "code": 611,
    "code_message": "Os dados estão incompletos no site ou aplicativo de origem e não puderam "
    "ser retornados.",
    "errors": [
        "As informações disponíveis na Receita Federal sobre o contribuinte 000.000.000-00 "
        "são insuficientes para emitir a certidão pela Internet."
    ],
}


class _Http:
    def __init__(self, *respostas: dict):
        self.respostas = list(respostas)
        self.calls: list[dict] = []

    async def get(self, url, **kw):
        self.calls.append({"url": url, **kw})
        r = MagicMock()
        r.json.return_value = self.respostas[min(len(self.calls), len(self.respostas)) - 1]
        return r

    post = get


async def _emitir(tipo: str, http, **consulta):
    cfg = config_for(tipo)
    c = _consulta_row(**consulta)
    db = _db(
        certidao_consultas=[c],
        certidao_resultados=[_resultado(tipo=tipo, id="r-1", status="na_fila")],
    )
    with patch("asyncio.sleep", new=AsyncMock()):
        await service._process_single_certidao(
            cfg, c, "tok", db, "r-1", http, FakeStorageBackend(),
            analyze=_noop_analyze, extract_text=_noop_extract_text,
            core_db=MockSupabaseClient(schema="public"),
        )
    return db.table("certidao_resultados").select("*").eq("id", "r-1").execute().data[0]


# ---- 1. the request every tipo sends --------------------------------------

#: tipo -> exact set of params a CPF consulta carries (token included). The
#: endpoints REJECT unknown params, so this is the contract, not a sample.
PARAMS_CPF = {
    "cnd_federal": {"token", "cpf", "birthdate", "preferencia_emissao"},
    "trf3_sp": {"token", "cpf", "tipo", "abrangencia", "nome_social"},
    "trf3": {"token", "cpf", "tipo", "abrangencia", "nome_social"},
    "trt2_digital": {"token", "cpf"},
    "trt2_fisico": {"token", "cpf", "nome"},
    "cnd_trabalhista_tst": {"token", "cpf"},
    "cenprot": {"token", "cpf"},
}
PARAMS_CNPJ = {
    "cnd_federal": {"token", "cnpj", "preferencia_emissao"},
    "trf3_sp": {"token", "cnpj", "tipo", "abrangencia"},
    "trf3": {"token", "cnpj", "tipo", "abrangencia"},
    "trt2_digital": {"token", "cnpj_raiz"},
    "trt2_fisico": {"token", "cnpj", "nome"},
    "cnd_trabalhista_tst": {"token", "cnpj"},
    "cenprot": {"token", "cnpj"},
}


class TestRequisicaoPorTipo:
    @pytest.mark.parametrize("tipo", sorted(PARAMS_CPF))
    def test_cpf(self, tipo):
        cfg = config_for(tipo)
        c = _consulta_row()
        assert pendencia_pre_chamada(cfg, c) is None
        assert set(PARAM_BUILDERS[cfg["params_fn"]](c, "tok")) == PARAMS_CPF[tipo]

    @pytest.mark.parametrize("tipo", sorted(PARAMS_CNPJ))
    def test_cnpj(self, tipo):
        cfg = config_for(tipo)
        c = _consulta_row(
            tipo_documento="cnpj", documento="12345678000190", data_nascimento=None,
            nome="Empresa Sintetica Ltda",
        )
        assert pendencia_pre_chamada(cfg, c) is None
        assert set(PARAM_BUILDERS[cfg["params_fn"]](c, "tok")) == PARAMS_CNPJ[tipo]

    def test_cnd_federal_cpf_sem_nascimento_nao_chama(self):
        # The F113 class: a billed 606 is never bought.
        msg = pendencia_pre_chamada(config_for("cnd_federal"), _consulta_row(data_nascimento=None))
        assert msg and "data de nascimento" in msg

    @pytest.mark.parametrize("tipo", ["cnd_fazenda_sp", "divida_ativa_sp"])
    def test_govbr_sem_login_nao_chama_e_com_login_vai_no_corpo(self, tipo):
        cfg = config_for(tipo)
        with patch(_CRED, return_value=None):
            assert pendencia_pre_chamada(cfg, _consulta_row()) is not None
        creds = {"infosimples_govbr_cpf": "00000000000", "infosimples_govbr_senha": "x"}
        with patch(_CRED, side_effect=lambda n, org_id=None: creds.get(n)):
            c = _consulta_row()
            assert pendencia_pre_chamada(cfg, c) is None
            p = PARAM_BUILDERS[cfg["params_fn"]](c, "tok")
        assert {"login_cpf", "login_senha"} <= set(p) and set(p) & set(SEGREDOS_DE_PARAMS)

    def test_todo_tipo_automatico_esta_coberto(self):
        cobertos = set(PARAMS_CPF) | {"cnd_fazenda_sp", "divida_ativa_sp", "tjsp"}
        assert {c["tipo"] for c in CERTIDOES_CONFIG} == cobertos


# ---- 2. every real vendor answer -------------------------------------------


class TestRespostasReaisDoFornecedor:
    @pytest.mark.parametrize(
        "resposta,mensagem",
        [
            (R_615_PAUSADA, MSG_API_PAUSADA),
            (R_603_SALDO, MSG_SEM_SALDO),
            (R_603_TOKEN, MSG_TOKEN_RECUSADO),
            (R_608_TRF, MSG_MUITAS_TENTATIVAS),
        ],
    )
    @pytest.mark.asyncio
    async def test_recusa_de_conta_ou_fonte_nao_retenta_e_explica(self, resposta, mensagem):
        http = _Http(resposta)
        row = await _emitir("cenprot", http)
        assert len(http.calls) == 1, "retrying cannot change an account/vendor refusal"
        assert row["status"] == "erro"
        assert row["erro_mensagem"] == mensagem
        assert row["api_response"]["code"] == resposta["code"], "raw vendor answer stays for support"

    @pytest.mark.asyncio
    async def test_cnd_federal_sem_saldo_nao_pede_segunda_via(self):
        http = _Http(R_603_SALDO)
        row = await _emitir("cnd_federal", http)
        assert len(http.calls) == 1 and row["erro_mensagem"] == MSG_SEM_SALDO

    @pytest.mark.asyncio
    async def test_615_da_fonte_sem_pausa_continua_retentando(self):
        http = _Http(R_615_FONTE)
        row = await _emitir("cenprot", http)
        assert len(http.calls) == service.MAX_RETRIES
        assert row["status"] == "erro"

    @pytest.mark.asyncio
    async def test_618_sobrecarga_retenta_e_se_recupera(self):
        ok = {"code": 200, "data": [{"site_receipt": "https://x/y.pdf"}], "header": {"price": 0.1}}
        http = _Http(R_618, ok)
        cfg = config_for("trf3")
        with patch("asyncio.sleep", new=AsyncMock()):
            r = await service._fetch_certidao(cfg, _consulta_row(), "tok", http)
        assert r["success"] and len(http.calls) == 2

    @pytest.mark.asyncio
    async def test_611_receita_insuficiente_e_erro_com_motivo_da_receita(self):
        http = _Http(R_611)
        row = await _emitir("cnd_federal", http)
        assert row["status"] == "erro" and "insuficientes" in row["erro_mensagem"]

    def test_reconhecimento(self):
        assert falha_de_conta_ou_fonte(R_618) is None
        assert falha_de_conta_ou_fonte(R_611) is None
        assert falha_de_conta_ou_fonte(None) is None
        assert falha_de_conta_ou_fonte({"code": 200}) is None


# ---- 3. real files (opt-in; nothing leaves memory) --------------------------

_DIR = os.environ.get("NOC_REAL_EXTRACTIONS_DIR") or os.path.expanduser(
    "~/.noctusai/private/extractions"
)
_CPF = re.compile(r"\b(\d{3})\.?(\d{3})\.?(\d{3})-?(\d{2})\b")
_NASC = re.compile(r"(?:NASC\w*|NASCIMENTO)\D{0,40}?(\d{2})/(\d{2})/(\d{4})", re.I)


def _cpf_valido(d: str) -> bool:
    if len(set(d)) == 1:
        return False
    for n in (9, 10):
        s = sum(int(d[i]) * (n + 1 - i) for i in range(n))
        if (s * 10 % 11) % 10 != int(d[n]):
            return False
    return True


def _partes_reais(limite: int = 25) -> list[dict]:
    out: list[dict] = []
    for f in sorted(glob.glob(os.path.join(_DIR, "*.json"))):
        try:
            txt = (json.load(open(f, encoding="utf-8")).get("text") or "")[:6000]
        except (OSError, ValueError):
            continue
        if not re.search(r"IDENTIDADE|HABILITA|REGISTRO GERAL", txt, re.I):
            continue
        m, n = _CPF.search(txt), _NASC.search(txt)
        if not (m and n):
            continue
        cpf = "".join(m.groups())
        if not _cpf_valido(cpf):
            continue
        try:
            nasc = date(int(n.group(3)), int(n.group(2)), int(n.group(1)))
        except ValueError:
            continue
        if not (1920 <= nasc.year <= 2008):
            continue
        out.append({"cpf": cpf, "nasc": nasc.isoformat()})
        if len(out) >= limite:
            break
    return out


@pytest.mark.skipif(not os.path.isdir(_DIR), reason="private real-document mirror not present")
class TestArquivosReais:
    def test_partes_reais_geram_requisicao_completa_para_todo_tipo(self):
        partes = _partes_reais()
        assert partes, "the mirror holds no RG/CNH with CPF + birth date — nothing to prove"
        for p in partes:
            c = _consulta_row(documento=p["cpf"], data_nascimento=p["nasc"])
            for cfg in CERTIDOES_CONFIG:
                if cfg["tipo"] in ("tjsp", "cnd_fazenda_sp", "divida_ativa_sp"):
                    continue
                assert pendencia_pre_chamada(cfg, c) is None
                params = PARAM_BUILDERS[cfg["params_fn"]](c, "tok")
                assert set(params) == PARAMS_CPF[cfg["tipo"]]
                assert params["cpf"] == p["cpf"] and len(params["cpf"]) == 11
            fed = PARAM_BUILDERS["cnd_federal"](c, "tok")
            assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", fed["birthdate"]), "InfoSimples wants aaaa-mm-dd"
            assert fed["birthdate"] == p["nasc"]

    def test_mesma_parte_sem_nascimento_fica_pendente_nao_chama(self):
        for p in _partes_reais(5):
            c = _consulta_row(documento=p["cpf"], data_nascimento=None)
            assert pendencia_pre_chamada(config_for("cnd_federal"), c)
