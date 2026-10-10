"""Certidão readers — gaps found by the live e2e of a real deal (876).

- the generic InfoSimples reader tolerates the shapes the emitted results
  carried (datetime emission, int number, `validade_data`);
- the stored document's own text is the deterministic fallback for `numero` /
  `emitida_em` (TRF3 / TRT2 receipts), fill-missing only, never over a human;
- a Serasa Crednet reaches the `serasa` cell of an AUTOMATIC consulta (which
  has no such row), both when uploaded later and when it was uploaded first;
- a 2ª via blocked for age says so and shows the printed validity.
No personal data: every name / CPF / number below is synthetic.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from uuid import UUID, uuid4

from noctusai_lib.testing import MockSupabaseClient

from app.modules.card_hub import certidoes_partes_service as partes_svc
from app.modules.card_hub.contrato_gerador import certidao_pcen
from app.modules.certidoes import registry, service

ORG = "test-org-876"
CPF = "41295423898"
ORG_UUID = UUID(int=1)


# ── registry reader ─────────────────────────────────────────────────────────


def _parse(item: dict) -> dict:
    return registry.parse_resultado({"parse_fn": "padrao"}, {"raw_response": {"data": [item]}})


class TestLeitorPadrao:
    def test_emissao_com_hora_e_numero_inteiro(self):
        got = _parse({"data_emissao": "10/10/2026 14:30:05", "numero": 123456})
        assert got == {"numero": "123456", "emitida_em": "2026-10-10"}

    def test_validade_data_da_receita(self):
        got = _parse({"emissao_data": "01/08/2026", "validade_data": "28/01/2027"})
        assert got["emitida_em"] == "2026-08-01"
        assert got["validade_ate"] == "2027-01-28"

    def test_chaves_alternativas(self):
        got = _parse({"certidao_numero": "AB-12/2026", "emissao": "02/03/2026"})
        assert got == {"numero": "AB-12/2026", "emitida_em": "2026-03-02"}

    def test_data_invalida_e_booleano_nao_viram_valor(self):
        assert _parse({"numero": True, "data_emissao": "31/02/2026"}) == {}


# ── text fallback ───────────────────────────────────────────────────────────

TEXTO_TRT = (
    "TRIBUNAL REGIONAL DO TRABALHO\nCERTIDÃO DE AÇÃO TRABALHISTA\n"
    "Certidão nº 2026.123456-7\nEmitida em: 05/10/2026 às 10:00\n"
)
TEXTO_TRF = "Certidão Nº 20260001234\nData de emissão: 06/10/2026\n"


class TestTextoDaCertidao:
    def test_numero_rotulado(self):
        assert service._numero_rotulado_do_texto(TEXTO_TRT) == "2026.123456-7"
        assert service._numero_rotulado_do_texto(TEXTO_TRF) == "20260001234"
        assert service._numero_rotulado_do_texto("Número da certidão: sem digitos") is None
        assert service._numero_rotulado_do_texto(None) is None

    def test_emissao_do_texto(self):
        assert service._data_emissao_do_texto([TEXTO_TRT]) == "2026-10-05"
        assert service._data_emissao_do_texto(["Emissão: 07/10/2026"]) == "2026-10-07"

    def _derive(self, **kw):
        async def ia(*_a, **_k):
            return None

        base = dict(
            config={"tipo": "trt2_digital", "parse_fn": "padrao"},
            result={"raw_response": {"data": [{"resultado": "sem campos de numero"}]}},
            texto_para_ia=None, nome_display="x", org_id=ORG, travado=False,
            analyze_estrutura=ia,
        )
        base.update(kw)
        return asyncio.run(service._derive_estrutura(**base))

    def test_preenche_numero_e_emissao_do_texto(self):
        patch = self._derive(paginas_texto=(TEXTO_TRT,))
        assert patch["numero"] == "2026.123456-7"
        assert patch["emitida_em"] == "2026-10-05"

    def test_api_vence_o_texto(self):
        result = {"raw_response": {"data": [{"numero_certidao": "API-1", "data_emissao": "01/10/2026"}]}}
        patch = self._derive(result=result, paginas_texto=(TEXTO_TRT,))
        assert patch["numero"] == "API-1"
        assert patch["emitida_em"] == "2026-10-01"

    def test_travado_nao_escreve_nada(self):
        assert self._derive(travado=True, paginas_texto=(TEXTO_TRT,)) == {}


# ── 2ª via note ─────────────────────────────────────────────────────────────


class TestNotaSegundaVia:
    ASSINATURA = date(2026, 10, 20)

    def test_nao_segunda_via_vazia(self):
        assert certidao_pcen.nota_segunda_via_antiga(
            segunda_via=False, validade_ate=date(2027, 1, 1), assinatura=self.ASSINATURA) == ""

    def test_mostra_validade_vigente(self):
        nota = certidao_pcen.nota_segunda_via_antiga(
            segunda_via=True, validade_ate=date(2027, 1, 28), assinatura=self.ASSINATURA)
        assert "2ª via" in nota and "28/01/2027" in nota and "ainda vigente" in nota

    def test_validade_nao_lida(self):
        nota = certidao_pcen.nota_segunda_via_antiga(
            segunda_via=True, validade_ate=None, assinatura=self.ASSINATURA)
        assert "2ª via" in nota and "não foi lida" in nota


# ── Serasa Crednet -> automatic consulta ────────────────────────────────────

_RECENTE = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0) - timedelta(days=3)


@dataclass(frozen=True)
class _Leitura:
    cpf: Optional[str] = CPF
    protocolo: Optional[str] = "7777777"
    consulta_em: Optional[datetime] = _RECENTE
    _constam: Optional[bool] = False

    def ocorrencias_constam(self) -> Optional[bool]:
        return self._constam


def _consulta(cliente_id: str) -> dict:
    return {
        "id": str(uuid4()), "org_id": ORG, "tipo_documento": "cpf", "documento": CPF,
        "cliente_id": cliente_id, "excluida_em": None, "origem": "automatica",
    }


class TestCrednetEmConsultaAutomatica:
    def test_cria_a_celula_serasa_quando_a_consulta_nao_tem(self):
        cliente_id = str(uuid4())
        consulta = _consulta(cliente_id)
        client = MockSupabaseClient(schema="social_wiring")
        client.set_table_data("certidao_consultas", [consulta])
        client.set_table_data("certidao_resultados", [])
        doc = {"id": str(uuid4()), "storage_path": f"{ORG}/clientes/c/doc"}

        n = service.registrar_serasa_de_crednet(client, ORG, cliente_id, doc, _Leitura())

        assert n == 1
        rows = client.table("certidao_resultados").select("*").eq("consulta_id", consulta["id"]).execute().data
        assert len(rows) == 1 and rows[0]["tipo"] == "serasa"
        assert rows[0]["status"] == "sucesso"
        assert rows[0]["numero"] == "7777777"
        assert rows[0]["emitida_em"] == _RECENTE.date().isoformat()
        assert rows[0]["resultado"] == "negativa"
        assert rows[0]["fonte_cliente_documento_id"] == doc["id"]

    def test_emissao_automatica_aplica_crednet_ja_enviado(self):
        cliente_id = str(uuid4())
        client = MockSupabaseClient(schema="social_wiring")
        client.set_table_data("certidao_consultas", [])
        client.set_table_data("certidao_resultados", [])
        client.set_table_data("cliente_documentos", [{
            "id": str(uuid4()), "org_id": str(ORG_UUID), "cliente_id": cliente_id,
            "tipo_documento": "serasa_crednet", "extracao_status": "ok", "deleted_at": None,
            "storage_path": f"{ORG}/clientes/c/doc",
            "extracao_crednet": {
                "cpf": CPF, "protocolo": "5555555",
                "consulta_em": _RECENTE.isoformat(), "ocorrencias_constam": False,
            },
        }])
        parte = {
            "tipo_pessoa": "PF", "nome": "Fulana de Teste", "documento": CPF,
            "cliente_id": cliente_id, "empresa_id": None, "parte_id": None,
        }
        client.set_table_data("clientes", [{"id": cliente_id, "org_id": ORG}])

        out = partes_svc._criar_consulta_automatica(
            client, ORG_UUID, "user-1", parte,
            [registry.CONFIG_BY_TIPO["cnd_federal"]],
        )

        rows = client.table("certidao_resultados").select("*").eq("consulta_id", out["consulta_id"]).execute().data
        serasa = [r for r in rows if r["tipo"] == "serasa"]
        assert len(serasa) == 1 and serasa[0]["numero"] == "5555555"


# ── real response shapes (synthetic values) ─────────────────────────────────

HEADER = {"requested_at": "2026-10-10T08:16:49.000-03:00", "price": 0.2, "billable": True}
TRF3 = {
    "header": HEADER,
    "data": [{
        "nome": "FULANA DE TESTE", "cpf_cnpj": "000.000.000-00", "mensagem": "texto",
        "nada_consta": True, "nome_social": None, "site_receipt": "https://x/r.html",
        "numero_certidao": "2026/000000000001",
        "dados_solicitacao": {"data_socilitacao": None, "hora": None},
        "codigo_verificacao": "AAAA.BBBB", "normalizado_cpf_cnpj": "00000000000",
    }],
}
TRT2 = {
    "header": HEADER,
    "data": [{
        "certidao": "Certifico, para os devidos fins, que ... texto longo ...",
        "codigo_autenticidade": "000.000.000.001", "codigo_verificacao": "000.000.000.001",
        "expedicao_datahora": "10/10/2026 08:20:00",
    }],
}
CND = {
    "header": HEADER,
    "noctus_segunda_via": True,
    "data": [{
        "tipo": "Positiva com efeitos de negativa", "situacao": "regular",
        "emissao_data": "11/08/2026", "validade_data": "07/02/2027",
        "certidao_codigo": "0AAA.0000.B6D3.CFF6",
        "conseguiu_emitir_certidao_negativa": False,
    }],
}


class TestFormasReaisDeProd:
    def test_trf3_numero_e_emissao_pela_consulta(self):
        assert _parse(TRF3["data"][0]) == {"numero": "2026/000000000001"}
        est = service._estrutura_do_api_response("trf3", TRF3)
        assert est["numero"] == "2026/000000000001"
        assert est["emitida_em"] == "2026-10-10"

    def test_trf3_texto_do_recibo_vence_a_consulta(self):
        async def ia(*_a, **_k):
            return None

        patch = asyncio.run(service._derive_estrutura(
            config=registry.CONFIG_BY_TIPO["trf3"], result={"raw_response": TRF3},
            texto_para_ia=None, nome_display="x", org_id=ORG, travado=False,
            analyze_estrutura=ia, paginas_texto=("Emitida em: 09/10/2026",),
        ))
        assert patch["emitida_em"] == "2026-10-09"
        sem_texto = asyncio.run(service._derive_estrutura(
            config=registry.CONFIG_BY_TIPO["trf3"], result={"raw_response": TRF3},
            texto_para_ia=None, nome_display="x", org_id=ORG, travado=False,
            analyze_estrutura=ia,
        ))
        assert sem_texto["emitida_em"] == "2026-10-10"

    def test_trt2_numero_vem_do_codigo_de_autenticidade(self):
        got = _parse(TRT2["data"][0])
        assert got["numero"] == "000.000.000.001"
        assert got["emitida_em"] == "2026-10-10"

    def test_cnd_federal_pcen_com_validade(self):
        got = _parse(CND["data"][0])
        assert got == {"numero": "0AAA.0000.B6D3.CFF6", "emitida_em": "2026-08-11",
                       "validade_ate": "2027-02-07"}
        est = service._estrutura_do_api_response("cnd_federal", CND)
        assert est["resultado"] == "positiva_com_efeito_de_negativa"
        assert certidao_pcen.excecao_aplica(
            resultado=est["resultado"], segunda_via=certidao_pcen.e_segunda_via(CND),
            validade_ate=date.fromisoformat(est["validade_ate"]),
        )

    def test_cnd_federal_veredito_via_situacao_quando_nao_ha_tipo(self):
        raw = {"data": [{"situacao": "Positiva com efeitos de negativa"}]}
        assert service._estrutura_do_api_response("cnd_federal", raw)["resultado"] == (
            "positiva_com_efeito_de_negativa"
        )

    def test_reler_rederiva_do_api_response_sem_chamar_a_api(self):
        rid = str(uuid4())
        client = MockSupabaseClient(schema="social_wiring")
        client.set_table_data("certidao_resultados", [{
            "id": rid, "org_id": ORG, "tipo": "trt2_digital", "numero": None,
            "emitida_em": None, "validade_ate": None, "resultado": None,
            "resultado_origem": None, "confirmado_por": None, "api_response": TRT2,
        }])

        async def extract(*_a, **_k):
            return service.ExtractedPdfText(para_ia=None)

        asyncio.run(service._reler_emissao(
            pdf_bytes=b"x", resultado_id=rid, consulta_id="c", nome_display="x",
            org_id=ORG, db=client, tipo="trt2_digital", extract_text=extract,
        ))
        row = client.table("certidao_resultados").select("*").eq("id", rid).execute().data[0]
        assert row["numero"] == "000.000.000.001"
        assert row["emitida_em"] == "2026-10-10"
