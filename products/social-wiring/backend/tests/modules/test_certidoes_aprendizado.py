"""InfoSimples emission WATCHER (`certidoes/aprendizado.py`, migration 186).

PINS
----
- `normalizar_assinatura`: identical failures group (digits/ids/accents/case
  stripped, the `code` kept);
- the observation row carries NO token / birthdate / name / full document;
- recording never blocks an emission (an insert that raises is logged);
- every call is recorded, with `fallback_de` linking a 2ª via to its trigger;
- the learned trigger: thresholds, margin, and what each class changes in
  `_precisa_segunda_via` / `_fetch_certidao`;
- the per-documento straight-to-2via decision;
- reclassification EVENTS: recorded once, WARNING-logged with a stable marker;
- the Receita PCEN `resultado` is set from the source's own `tipo`, and a
  re-processed row loses the operator's acknowledgment.
"""
from __future__ import annotations

import json
import logging
from datetime import date
from unittest.mock import MagicMock

import pytest
from noctusai_lib.integrations.storage import FakeStorageBackend
from noctusai_lib.testing import MockSupabaseClient

from app.modules.certidoes import aprendizado as ap
from app.modules.certidoes import service
from app.modules.certidoes.registry import config_for
from tests.modules.test_certidoes_service import (
    CONSULTA_CPF,
    _consulta_row,
    _db,
    _noop_analyze,
    _noop_extract_text,
    _resultado,
)

CONFIG = config_for("cnd_federal")
HOJE = date(2026, 10, 1)
PCEN_TIPO = "Positiva com efeitos de negativa"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


class _Seq:
    """httpx stand-in answering each InfoSimples call with the next payload."""

    def __init__(self, *payloads, file_body=b"%PDF-1.4 x"):
        self.payloads = list(payloads)
        self.params: list[dict] = []
        self.file_body = file_body

    async def get(self, url, **kw):
        if url.startswith(service.INFOSIMPLES_BASE_URL):
            self.params.append(dict(kw.get("params") or {}))
            resp = MagicMock(status_code=200)
            resp.json.return_value = self.payloads[min(len(self.params), len(self.payloads)) - 1]
            return resp
        resp = MagicMock(status_code=200, content=self.file_body)
        resp.headers = {"content-type": "application/pdf"}
        return resp

    @property
    def preferencias(self):
        return [p.get("preferencia_emissao") for p in self.params]


def _falha(code=605, msg="Não foi possível emitir a certidão", errors=None):
    return {"code": code, "code_message": "falha", "errors": errors if errors is not None else [msg],
            "header": {"price": "0.24", "billable": True}}


def _pcen_ok(validade="30/11/2026", emissao="02/09/2026"):
    return {"code": 200, "data": [{
        "site_receipt": "https://x/r.pdf", "tipo": PCEN_TIPO, "situacao": "Válida",
        "emissao_data": emissao, "validade": validade, "validade_data": validade,
        "conseguiu_emitir_certidao_negativa": False,
    }], "header": {"price": "0.24", "billable": True}}


def _obs(id_, *, pref="nova", ok=False, ass="605|x|", fb=None, data_tipo=None, t="2026-09-01T10:00:00",
         doc="h1", validade=None, tipo="cnd_federal", org="org"):
    return {"org_id": org, "id": id_, "tipo": tipo, "sucesso": ok, "assinatura": None if ok else ass,
            "preferencia_emissao": pref, "fallback_de": fb, "data_tipo": data_tipo,
            "documento_hash": doc, "created_at": t, "tentativa": 1, "validade": validade}


def _casos_pcen(n, ass="605|x|"):
    out = []
    for i in range(n):
        out += [
            _obs(f"n{i}", ass=ass, t=f"2026-09-0{i + 1}T10:00:00"),
            _obs(f"v{i}", pref="2via", ok=True, fb=f"n{i}", data_tipo=PCEN_TIPO, t=f"2026-09-0{i + 1}T10:00:01"),
        ]
    return out


def _casos_transitorios(n, ass="605|x|"):
    out = []
    for i in range(n):
        out += [
            _obs(f"n{i}", ass=ass, t=f"2026-09-0{i + 1}T10:00:00"),
            _obs(f"v{i}", pref="2via", ok=False, ass="605|y|", fb=f"n{i}", t=f"2026-09-0{i + 1}T10:00:01"),
        ]
    return out


# ---------------------------------------------------------------------------
# signature
# ---------------------------------------------------------------------------


class TestAssinatura:
    def test_ids_datas_e_acentos_nao_separam_a_mesma_falha(self):
        a = ap.normalizar_assinatura(605, "Falha ao emitir", ["Não foi possível emitir (proto 123456, 01/10/2026)"])
        b = ap.normalizar_assinatura(605, "FALHA AO EMITIR", ["Nao foi possivel emitir (proto 999, 02/11/2026)"])
        assert a == b and a.startswith("605|")

    def test_o_code_separa_falhas_diferentes(self):
        assert ap.normalizar_assinatura(605, "x", []) != ap.normalizar_assinatura(608, "x", [])

    def test_e_deterministica_e_nao_quebra_com_vazios(self):
        assert ap.normalizar_assinatura(None, None, None) == "||"
        assert ap.normalizar_assinatura(600, None, []) == "600||"
        assert ap.normalizar_assinatura(600, "a", ["a", "b"]) == ap.normalizar_assinatura(600, "a", ["a", "b"])

    def test_urls_e_emails_saem(self):
        s = ap.normalizar_assinatura(605, "erro em https://x.com/a?b=1 contato a@b.com", [])
        assert "http" not in s and "@" not in s


# ---------------------------------------------------------------------------
# observation row — LGPD + shape
# ---------------------------------------------------------------------------


class TestObservacao:
    def _montar(self, **over):
        params = {"token": "SEGREDO-TOKEN", "cpf": "12345678901", "birthdate": "1990-01-15",
                  "preferencia_emissao": "nova", "nome": "João da Silva", "tipo": "1"}
        kw = dict(config=CONFIG, consulta=CONSULTA_CPF, params=params, tentativa=1, http_status=200,
                  resposta=_falha(), elapsed_ms=12)
        kw.update(over)
        return ap.montar_observacao(**kw)

    def test_sem_token_nascimento_nome_nem_documento(self):
        blob = json.dumps(self._montar(), default=str)
        for proibido in ("SEGREDO-TOKEN", "12345678901", "1990-01-15", "João", "Silva"):
            assert proibido not in blob

    def test_params_e_allowlist_mais_nomes_de_chave(self):
        obs = self._montar()
        assert obs["params"]["preferencia_emissao"] == "nova" and obs["params"]["tipo"] == "1"
        assert "cpf" in obs["params"]["chaves_enviadas"] and "token" not in obs["params"]["chaves_enviadas"]
        assert "cpf" not in {k for k in obs["params"] if k != "chaves_enviadas"}

    def test_documento_vira_hmac_estavel_e_por_org(self):
        a = self._montar()["documento_hash"]
        assert a == self._montar()["documento_hash"] and len(a) == 32
        outra = ap.chave_documento("outra-org", "12345678901")
        assert outra != a and ap.chave_documento("x", "") is None

    def test_sucesso_pcen_le_os_campos_documentados(self):
        obs = self._montar(resposta=_pcen_ok())
        assert obs["sucesso"] is True and obs["assinatura"] is None
        assert obs["data_tipo"] == PCEN_TIPO and obs["validade"] == "2026-11-30"
        assert obs["emissao_data"] == "2026-09-02" and obs["price_brl"] == "0.24" and obs["billable"] is True
        assert obs["conseguiu_emitir_negativa"] is False

    def test_falha_tem_assinatura_codigo_e_erros(self):
        obs = self._montar()
        assert obs["sucesso"] is False and obs["code"] == 605 and obs["assinatura"].startswith("605|")
        assert obs["errors"] == ["Não foi possível emitir a certidão"]

    def test_excecao_de_rede_e_registrada_sem_http(self):
        obs = self._montar(resposta=None, http_status=None, erro_excecao="ConnectError: down")
        assert obs["http_status"] is None and obs["sucesso"] is False and "connecterror" in obs["assinatura"]

    def test_612_e_sucesso_nada_consta(self):
        assert self._montar(resposta={"code": 612, "errors": ["Nada consta"]})["sucesso"] is True


class TestRegistrar:
    def test_falha_de_gravacao_e_logada_e_nunca_propaga(self, caplog):
        db = MagicMock()
        db.table.return_value.insert.return_value.execute.side_effect = RuntimeError("db down")
        with caplog.at_level(logging.ERROR):
            ap.registrar(db, [{"id": "a", "tipo": "cnd_federal"}], resultado_id="r")
        assert any("could not record" in r.message for r in caplog.records)

    def test_grava_em_ordem_com_o_resultado(self):
        db = MockSupabaseClient(schema="social_wiring")
        ap.registrar(db, [{"id": "a", "tipo": "t"}, {"id": "b", "tipo": "t", "fallback_de": "a"}], resultado_id="r1")
        rows = db.table(ap.TABELA).inserted_payloads
        assert [r["id"] for r in rows] == ["a", "b"] and all(r["resultado_id"] == "r1" for r in rows)


# ---------------------------------------------------------------------------
# learned trigger
# ---------------------------------------------------------------------------


class TestClassificacao:
    def test_tres_casos_pcen_confirmam(self):
        assert ap.classificar_assinaturas(_casos_pcen(3)) == {"605|x|": ap.CLASSE_PCEN}

    def test_dois_nao_bastam(self):
        assert ap.classificar_assinaturas(_casos_pcen(2)) == {"605|x|": ap.CLASSE_DESCONHECIDA}

    def test_tres_transitorios_confirmam(self):
        assert ap.classificar_assinaturas(_casos_transitorios(3)) == {"605|x|": ap.CLASSE_TRANSITORIA}

    def test_nova_que_voltou_a_funcionar_conta_como_transitoria(self):
        obs = []
        for i in range(3):
            obs += [_obs(f"n{i}", t=f"2026-09-0{i + 1}T10:00:00", doc=f"d{i}"),
                    _obs(f"ok{i}", ok=True, t=f"2026-09-0{i + 1}T11:00:00", doc=f"d{i}")]
        assert ap.classificar_assinaturas(obs)["605|x|"] == ap.CLASSE_TRANSITORIA

    def test_sinal_misto_nao_e_confirmado(self):
        # 3 PCEN vs 2 transitórios: PCEN lacks the 3x margin ⇒ unknown.
        misto = _casos_pcen(3) + [
            {**o, "id": o["id"] + "z", "fallback_de": (o["fallback_de"] + "z") if o["fallback_de"] else None}
            for o in _casos_transitorios(2)
        ]
        assert ap.classificar_assinaturas(misto)["605|x|"] == ap.CLASSE_DESCONHECIDA

    def test_2via_que_devolve_negativa_comum_e_apenas_informativa(self):
        obs = [_obs("n", t="2026-09-01T10:00:00"),
               _obs("v", pref="2via", ok=True, fb="n", data_tipo="Negativa", t="2026-09-01T10:00:01")]
        d = ap.desfechos_por_assinatura(obs)["605|x|"]
        assert d["via2_outro"] == 1 and d["pcen"] == 0 and d["transitoria"] == 0

    def test_decisao_do_retry(self):
        assert ap.decidir_retry_2via("a", {"a": ap.CLASSE_TRANSITORIA}) is False
        assert ap.decidir_retry_2via("a", {"a": ap.CLASSE_PCEN}) is True
        assert ap.decidir_retry_2via("a", {"a": ap.CLASSE_DESCONHECIDA}) is True
        assert ap.decidir_retry_2via("a", {}) is True and ap.decidir_retry_2via(None, None) is True

    def test_limiares_sao_constantes_nomeadas(self):
        assert ap.LIMIAR_CONFIRMACAO == 3 and ap.MARGEM_CONFIRMACAO == 3

    def test_precisa_segunda_via_respeita_o_aprendizado(self):
        params = {"preferencia_emissao": "nova"}
        assert service._precisa_segunda_via(CONFIG, params, 605) is True
        assert service._precisa_segunda_via(
            CONFIG, params, 605, assinatura="a", classificacoes={"a": ap.CLASSE_TRANSITORIA}) is False
        assert service._precisa_segunda_via(
            CONFIG, params, 605, assinatura="a", classificacoes={"a": ap.CLASSE_PCEN}) is True


class TestPreferenciaInicial:
    def _hist(self, validade, data_tipo=PCEN_TIPO, pref="2via"):
        return [_obs("v", pref=pref, ok=True, data_tipo=data_tipo, validade=validade)]

    def test_pcen_ainda_valida_vai_direto_para_2via(self):
        assert ap.preferencia_inicial(self._hist("2026-11-30"), HOJE) == "2via"

    def test_validade_hoje_ainda_conta(self):
        assert ap.preferencia_inicial(self._hist("2026-10-01"), HOJE) == "2via"

    def test_vencida_volta_para_nova(self):
        assert ap.preferencia_inicial(self._hist("2026-09-30"), HOJE) == "nova"

    def test_sem_historico_ou_nao_pcen_ou_nova_e_nova(self):
        assert ap.preferencia_inicial([], HOJE) == "nova"
        assert ap.preferencia_inicial(self._hist("2026-11-30", data_tipo="Negativa"), HOJE) == "nova"
        assert ap.preferencia_inicial(self._hist("2026-11-30", pref="nova"), HOJE) == "nova"

    def test_a_ultima_emissao_bem_sucedida_decide(self):
        obs = self._hist("2026-11-30") + [
            _obs("n", pref="nova", ok=True, data_tipo="Negativa", t="2026-09-20T10:00:00", validade="2027-03-01")]
        assert ap.preferencia_inicial(obs, HOJE) == "nova"


# ---------------------------------------------------------------------------
# _fetch_certidao — every call recorded; learning changes the calls
# ---------------------------------------------------------------------------


class TestFetchObserva:
    @pytest.mark.asyncio
    async def test_nova_recusada_e_2via_ok_geram_duas_observacoes_ligadas(self):
        http = _Seq(_falha(), _pcen_ok())
        r = await service._fetch_certidao(CONFIG, CONSULTA_CPF, "tok", http)
        assert r["success"] and r["segunda_via"] and http.preferencias == ["nova", "2via"]
        a, b = r["observacoes"]
        assert (a["sucesso"], b["sucesso"]) == (False, True)
        assert a["fallback_de"] is None and b["fallback_de"] == a["id"]
        assert b["data_tipo"] == PCEN_TIPO and [o["tentativa"] for o in r["observacoes"]] == [1, 2]
        assert "tok" not in json.dumps(r["observacoes"], default=str)

    @pytest.mark.asyncio
    async def test_sucesso_direto_tambem_e_registrado(self):
        r = await service._fetch_certidao(CONFIG, CONSULTA_CPF, "tok", _Seq(_pcen_ok()))
        assert len(r["observacoes"]) == 1 and r["observacoes"][0]["sucesso"]

    @pytest.mark.asyncio
    async def test_outros_tipos_tambem_sao_registrados(self):
        r = await service._fetch_certidao(
            config_for("trf3_sp"), CONSULTA_CPF, "tok", _Seq({"code": 200, "data": [{"site_receipt": "u"}]}))
        assert r["observacoes"][0]["tipo"] == "trf3_sp"

    @pytest.mark.asyncio
    async def test_assinatura_transitoria_confirmada_economiza_a_chamada(self, monkeypatch):
        sleeps = []

        async def _sleep(s):
            sleeps.append(s)
        monkeypatch.setattr("asyncio.sleep", _sleep)
        http = _Seq(_falha())
        ass = ap.normalizar_assinatura(605, "falha", ["Não foi possível emitir a certidão"])
        r = await service._fetch_certidao(
            CONFIG, CONSULTA_CPF, "tok", http, classificacoes={ass: ap.CLASSE_TRANSITORIA})
        assert r["success"] is False and set(http.preferencias) == {"nova"}

    @pytest.mark.asyncio
    async def test_assinatura_desconhecida_mantem_o_comportamento_atual(self):
        http = _Seq(_falha(), _pcen_ok())
        await service._fetch_certidao(CONFIG, CONSULTA_CPF, "tok", http, classificacoes={})
        assert http.preferencias == ["nova", "2via"]

    @pytest.mark.asyncio
    async def test_preferencia_inicial_2via_pula_a_nova_que_falharia(self):
        http = _Seq(_pcen_ok())
        r = await service._fetch_certidao(CONFIG, CONSULTA_CPF, "tok", http, preferencia_inicial="2via")
        assert http.preferencias == ["2via"] and r["segunda_via"] is True

    @pytest.mark.asyncio
    async def test_2via_inicial_recusada_cai_para_nova_uma_vez(self):
        http = _Seq(_falha(), {"code": 200, "data": [{"site_receipt": "u", "tipo": "Negativa"}]})
        r = await service._fetch_certidao(CONFIG, CONSULTA_CPF, "tok", http, preferencia_inicial="2via")
        assert http.preferencias == ["2via", "nova"] and r["success"] and r["segunda_via"] is False
        assert r["observacoes"][1]["fallback_de"] == r["observacoes"][0]["id"]

    @pytest.mark.asyncio
    async def test_preferencia_inicial_nao_afeta_outros_tipos(self):
        http = _Seq({"code": 200, "data": [{"site_receipt": "u"}]})
        await service._fetch_certidao(config_for("trf3_sp"), CONSULTA_CPF, "tok", http, preferencia_inicial="2via")
        assert "preferencia_emissao" not in http.params[0]


# ---------------------------------------------------------------------------
# learning events
# ---------------------------------------------------------------------------


class TestEventos:
    def test_mudanca_de_classe_gera_evento_uma_vez(self):
        ev = ap.eventos_de_aprendizado(_casos_pcen(3), {})
        assert len(ev) == 1
        e = ev[0]
        assert (e["classe"], e["classe_anterior"], e["assinatura"]) == (ap.CLASSE_PCEN, "desconhecida", "605|x|")
        assert e["evidencia"]["pcen"] == 3 and e["primeira_obs_em"] < e["ultima_obs_em"]
        # idempotent: once stored, the same evidence is not an event again
        assert ap.eventos_de_aprendizado(_casos_pcen(3), {"605|x|": {"classe": ap.CLASSE_PCEN}}) == []

    def test_desconhecida_inicial_nao_e_evento(self):
        assert ap.eventos_de_aprendizado(_casos_pcen(2), {}) == []

    def test_reclassificacao_pcen_para_transitoria(self):
        ev = ap.eventos_de_aprendizado(_casos_transitorios(3), {"605|x|": {"classe": ap.CLASSE_PCEN}})
        assert ev[0]["classe"] == ap.CLASSE_TRANSITORIA and ev[0]["classe_anterior"] == ap.CLASSE_PCEN

    def test_aprender_persiste_e_loga_com_marcador_estavel(self, caplog):
        db = _db(**{ap.TABELA: _casos_pcen(3), ap.TABELA_APRENDIZADOS: []})
        with caplog.at_level(logging.WARNING):
            eventos = ap.aprender(db, "org", "cnd_federal")
        assert len(eventos) == 1
        (gravado,) = db.table(ap.TABELA_APRENDIZADOS).inserted_payloads
        assert gravado["org_id"] == "org" and gravado["classe"] == ap.CLASSE_PCEN
        assert any(r.levelno == logging.WARNING and ap.MARCADOR_LOG in r.message for r in caplog.records)

    def test_aprender_com_evento_ja_gravado_nao_repete(self):
        db = _db(**{ap.TABELA: _casos_pcen(3), ap.TABELA_APRENDIZADOS: [
            {"org_id": "org", "tipo": "cnd_federal", "assinatura": "605|x|", "classe": ap.CLASSE_PCEN,
             "decidido_em": "2026-09-05T00:00:00"}]})
        assert ap.aprender(db, "org", "cnd_federal") == []
        assert db.table(ap.TABELA_APRENDIZADOS).inserted_payloads == []

    def test_aprender_nunca_propaga(self, caplog):
        db = MagicMock()
        db.table.side_effect = RuntimeError("down")
        assert ap.aprender(db, "org", "cnd_federal") == []

    def test_carregar_classificacoes_pega_o_ultimo_evento(self):
        db = _db(**{ap.TABELA_APRENDIZADOS: [
            {"org_id": "org", "tipo": "cnd_federal", "assinatura": "a", "classe": ap.CLASSE_PCEN,
             "decidido_em": "2026-09-01"},
            {"org_id": "org", "tipo": "cnd_federal", "assinatura": "a", "classe": ap.CLASSE_TRANSITORIA,
             "decidido_em": "2026-09-09"}]})
        assert ap.carregar_classificacoes(db, "org", "cnd_federal") == {"a": ap.CLASSE_TRANSITORIA}

    def test_carregar_classificacoes_falha_vira_vazio(self):
        db = MagicMock()
        db.table.side_effect = RuntimeError("down")
        assert ap.carregar_classificacoes(db, "org", "cnd_federal") == {}


# ---------------------------------------------------------------------------
# through the pipeline
# ---------------------------------------------------------------------------


class TestPipeline:
    async def _rodar(self, db, http, resultado_id="resultado-001"):
        await service._process_single_certidao(
            CONFIG, _consulta_row(), "tok", db, resultado_id, http, FakeStorageBackend(),
            analyze=_noop_analyze, extract_text=_noop_extract_text,
            core_db=MockSupabaseClient(schema="public"),
        )

    @pytest.mark.asyncio
    async def test_toda_chamada_e_gravada_o_resultado_e_pcen_e_a_ciencia_antiga_cai(self):
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[_resultado(
                pcen_ciente_em="2026-09-01T00:00:00+00:00", pcen_ciente_por="u1",
                pcen_ciente_validade="2026-10-30")],
            **{ap.TABELA: [], ap.TABELA_APRENDIZADOS: []},
        )
        await self._rodar(db, _Seq(_falha(), _pcen_ok()))
        obs = db.table(ap.TABELA).inserted_payloads
        assert len(obs) == 2 and obs[1]["fallback_de"] == obs[0]["id"]
        assert all(o["resultado_id"] == "resultado-001" and o["org_id"] for o in obs)
        assert "tok" not in json.dumps(obs, default=str) and "12345678901" not in json.dumps(obs, default=str)
        row = db.table("certidao_resultados").select("*").eq("id", "resultado-001").execute().data[0]
        assert row["status"] == "sucesso"
        assert row["resultado"] == "positiva_com_efeito_de_negativa" and row["resultado_origem"] == "api"
        assert row["api_response"][service.MARCA_SEGUNDA_VIA]
        assert row["pcen_ciente_em"] is None and row["pcen_ciente_validade"] is None

    @pytest.mark.asyncio
    async def test_a_ciencia_tambem_cai_quando_o_reprocessamento_falha(self):
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[_resultado(pcen_ciente_em="2026-09-01T00:00:00+00:00")],
            **{ap.TABELA: [], ap.TABELA_APRENDIZADOS: []},
        )
        await self._rodar(db, _Seq({"code": 400, "errors": ["CPF inválido"]}))
        row = db.table("certidao_resultados").select("*").eq("id", "resultado-001").execute().data[0]
        assert row["status"] == "erro" and row["pcen_ciente_em"] is None

    @pytest.mark.asyncio
    async def test_gravar_observacao_que_falha_nao_derruba_a_emissao(self, caplog):
        class _Quebra(MockSupabaseClient):
            def table(self, name):
                if name == ap.TABELA:
                    raise RuntimeError("tabela indisponível")
                return super().table(name)

        db = _Quebra(schema="social_wiring")
        db.set_table_data("certidao_consultas", [_consulta_row()])
        db.set_table_data("certidao_resultados", [_resultado()])
        db.set_table_data(ap.TABELA_APRENDIZADOS, [])
        with caplog.at_level(logging.ERROR):
            await self._rodar(db, _Seq(_pcen_ok()))
        row = db.table("certidao_resultados").select("*").eq("id", "resultado-001").execute().data[0]
        assert row["status"] == "sucesso"

    @pytest.mark.asyncio
    async def test_historico_do_documento_manda_direto_para_2via(self):
        chave = ap.chave_documento(_consulta_row()["org_id"], _consulta_row()["documento"])
        hist = [_obs("v", pref="2via", ok=True, data_tipo=PCEN_TIPO, doc=chave, org=CONSULTA_CPF["org_id"],
                     validade=date.today().replace(year=date.today().year + 1).isoformat())]
        db = _db(
            certidao_consultas=[_consulta_row()], certidao_resultados=[_resultado()],
            **{ap.TABELA: hist, ap.TABELA_APRENDIZADOS: []},
        )
        http = _Seq(_pcen_ok())
        await self._rodar(db, http)
        assert http.preferencias == ["2via"]


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------


class TestRelatorio:
    def test_resume_por_tipo_com_classe_exemplos_mascarados_e_custo(self):
        obs = _casos_pcen(3) + [
            _obs("ok1", ok=True, tipo="trf3_sp", t="2026-09-09T10:00:00"),
        ]
        for o in obs:
            o["price_brl"], o["billable"] = "0.24", True
            o["code_message"], o["errors"], o["code"] = "falha 123456789", ["cpf 12345678901 inválido"], 605
        rel = ap.relatorio(obs)
        fed = rel["tipos"]["cnd_federal"]
        assert fed["chamadas"] == 6 and fed["sucessos"] == 3 and fed["taxa_sucesso"] == 0.5
        sig = fed["assinaturas_de_falha"][0]
        assert sig["classe"] == ap.CLASSE_PCEN and sig["ocorrencias"] == 3
        assert "12345678901" not in json.dumps(sig) and "#" in sig["exemplos"][0]["code_message"]
        assert fed["retries_2via"] == 3 and fed["custo_retries_brl"] == "0.72"
        assert fed["emissoes_pcen"] == 3
        assert rel["tipos"]["trf3_sp"]["taxa_sucesso"] == 1.0
        assert any("PCEN confirmada" in s for s in rel["sugestoes"])

    def test_vazio(self):
        assert ap.relatorio([])["tipos"] == {}
