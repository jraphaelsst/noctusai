"""Certidões Negativas — service-layer tests.

Ports the coverage of
`products/erp-imobiliario/backend/tests/services/test_certidoes_service.py` and
adds the cases this port's own divergences created: the storage seam (keys, not
public URLs), the delete path that replaced ERP's raw-supabase workaround, and
the org scoping migration 091 introduced.

`MockSupabaseClient` (not a hand-rolled chain stub) because it validates column
names against the migration-derived schema — so a typo'd column in a query
under test fails here rather than in production — and because it propagates
writes into subsequent reads, which is what the status-recalculation and
recovery tests actually assert on.
"""
from __future__ import annotations

import asyncio
import http.server
import logging
import threading
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from noctusai_lib.integrations.documents.formatting import FormatRange
from noctusai_lib.integrations.storage import FakeStorageBackend
from noctusai_lib.testing import MockSupabaseClient

from app.modules.certidoes import service
from app.modules.certidoes.registry import (
    CERTIDOES_CONFIG,
    MANUAL_TIPOS_CONFIG,
    PARAM_BUILDERS,
    PARSE_BUILDERS,
    RESULTADO_VALUES,
    TJSP_COOLDOWN_SECONDS,
    TJSP_TIPO,
    _build_params_cnd_federal,
    _build_params_simples,
    _build_params_tjsp,
    _build_params_trf3,
    _build_params_trf3_sp,
    _build_params_trt2_digital,
    _build_params_trt2_fisico,
    _cenprot_protocolo_date,
    config_for,
    get_certidoes_tipos,
    get_manual_tipos,
    manual_config_for,
    parse_resultado,
)

#: The module's single credential-resolution point. Substituting HERE (not
#: `noctusai_lib`'s `resolve_credential`) is the point of
#: `credentials.resolve_key`: the store behind it moved to the product-local
#: encrypted one and these tests did not have to follow it into two tiers.
_CRED = "app.modules.certidoes.credentials.resolve_api_key"
_REGISTRY_RESOLVE = "app.modules.certidoes.registry.resolve_key"

ORG = "11111111-1111-4111-8111-111111111111"
OTHER_ORG = "22222222-2222-4222-8222-222222222222"

CONSULTA_CPF = {
    "id": "consulta-001",
    "org_id": ORG,
    "tipo_documento": "cpf",
    "documento": "12345678901",
    "nome": "João da Silva",
    "data_nascimento": "1990-01-15",
    "genero": "M",
    "rg": "123456789",
    "nome_mae": "Maria da Silva",
    "nome_pai": "José da Silva",
}

CONSULTA_CNPJ = {
    "id": "consulta-002",
    "org_id": ORG,
    "tipo_documento": "cnpj",
    "documento": "12345678000190",
    "nome": "Empresa XPTO",
    "data_nascimento": None,
    "genero": None,
    "rg": None,
    "nome_mae": None,
    "nome_pai": None,
}

CONSULTA_MINIMAL = {
    "id": "consulta-003",
    "org_id": ORG,
    "tipo_documento": "cpf",
    "documento": "99988877766",
    "nome": "Teste",
}


def _db(**tables) -> MockSupabaseClient:
    """A `social_wiring`-scoped mock client seeded per table."""
    client = MockSupabaseClient(schema="social_wiring")
    for name, rows in tables.items():
        client.set_table_data(name, rows)
    return client


def _resultado(**overrides) -> dict:
    row = {
        "id": "resultado-001",
        "consulta_id": "consulta-001",
        "org_id": ORG,
        "tipo": "cnd_federal",
        "nome_display": "CND Federal (Receita)",
        "ordem": 1,
        "status": "pendente",
        "analise_ia": None,
        "arquivo_url": None,
        "arquivo_nome": None,
        "api_response": None,
        "erro_mensagem": None,
        "api_requested_at": None,
        "numero": None,
        "emitida_em": None,
        "validade_ate": None,
        "resultado": None,
        "resultado_origem": None,
        "confirmado_por": None,
        "confirmado_em": None,
        # Migration 155
        "estrutura_erro": None,
        "estrutura_tentativas": 0,
        "created_at": "2026-03-05T10:00:00+00:00",
        "updated_at": "2026-03-05T10:00:00+00:00",
    }
    row.update(overrides)
    return row


def _consulta_row(**overrides) -> dict:
    row = {
        **CONSULTA_CPF,
        "created_by": "user-1",
        "status": "pendente",
        "total_certidoes": 10,
        "concluidas": 0,
        "created_at": "2026-03-05T10:00:00+00:00",
        "updated_at": "2026-03-05T10:00:00+00:00",
    }
    row.update(overrides)
    return row


# ---------------------------------------------------------------------------
# CERTIDOES_CONFIG — the contract with ten third-party endpoints
# ---------------------------------------------------------------------------


class TestCertidoesConfig:
    def test_tem_10_tipos(self):
        assert len(CERTIDOES_CONFIG) == 10

    def test_ordens_sequenciais(self):
        assert [c["ordem"] for c in CERTIDOES_CONFIG] == list(range(1, 11))

    def test_todos_tem_campos_obrigatorios(self):
        for config in CERTIDOES_CONFIG:
            for field in (
                "tipo", "nome", "endpoint", "ordem", "params_fn", "response_format"
            ):
                assert field in config, f"{config.get('tipo')} missing {field}"

    def test_params_fn_validos(self):
        for config in CERTIDOES_CONFIG:
            assert config["params_fn"] in PARAM_BUILDERS

    def test_response_format_validos(self):
        for config in CERTIDOES_CONFIG:
            assert config["response_format"] in ("pdf", "html")

    def test_tipos_e_ordem_identicos_ao_erp(self):
        """🔴 The whole registry, pinned.

        A dropped or reordered certificate type is a certificate a user
        silently stops receiving — no error, no failed row, just one fewer item
        on a checklist nobody re-counts. The per-field tests above would all
        still pass with the TJSP entry deleted. This one would not.
        """
        assert [(c["tipo"], c["ordem"]) for c in CERTIDOES_CONFIG] == [
            ("cnd_federal", 1),
            ("trf3_sp", 2),
            ("trf3", 3),
            ("trt2_digital", 4),
            ("trt2_fisico", 5),
            ("cnd_trabalhista_tst", 6),
            ("tjsp", 7),
            ("cenprot", 8),
            ("cnd_fazenda_sp", 9),
            ("divida_ativa_sp", 10),
        ]

    def test_endpoints_identicos_ao_erp(self):
        assert {c["tipo"]: c["endpoint"] for c in CERTIDOES_CONFIG} == {
            "cnd_federal": "receita-federal/pgfn",
            "trf3_sp": "tribunal/trf3/certidao-distr",
            "trf3": "tribunal/trf3/certidao-distr",
            "trt2_digital": "tribunal/trt2/ceat-digital",
            "trt2_fisico": "tribunal/trt2/ceat",
            "cnd_trabalhista_tst": "tst/cndt",
            "tjsp": "tribunal/tjsp/pedido-certidao",
            "cenprot": "cenprot-sp/protestos",
            "cnd_fazenda_sp": "sefaz/sp/certidao-debitos",
            "divida_ativa_sp": "pge/sp/cndt",
        }

    def test_config_for_desconhecido_retorna_none(self):
        assert config_for("nao_existe") is None
        assert config_for(TJSP_TIPO)["ordem"] == 7


class TestGetCertidoesTipos:
    def test_retorna_lista(self):
        assert len(get_certidoes_tipos()) == 10

    def test_cada_item_tem_tipo_nome_ordem(self):
        for item in get_certidoes_tipos():
            assert set(item) == {"tipo", "nome", "ordem"}

    def test_nao_expoe_campos_internos(self):
        """The endpoint path and the builder name are ours, not the browser's."""
        for item in get_certidoes_tipos():
            assert "endpoint" not in item
            assert "params_fn" not in item


# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------


class TestCheckRequiredCredentials:
    def test_sem_infosimples_retorna_mensagem(self):
        with patch(_CRED, return_value=None):
            missing = service.check_required_credentials(ORG)
        assert len(missing) == 1
        assert "InfoSimples" in missing[0]

    def test_com_infosimples_retorna_vazio(self):
        with patch(_CRED, return_value="tok-123"):
            assert service.check_required_credentials(ORG) == []

    def test_resolve_passa_pelo_seam_do_modulo(self):
        """Every key in this module goes through `credentials.resolve_key`,
        which now resolves through the product's own encrypted key store.

        A call site that had reached for `resolve_credential` directly would
        still be reading the platform chain ONLY — skipping the encrypted rows
        the operator writes in Settings → Chaves de API — and nothing would say
        so: the platform tier still answers for a pre-existing key, so the miss
        would surface only for an org that had re-entered its token in the new
        UI. This asserts the routing, not just the return value.
        """
        with patch(_CRED, return_value="tok") as m:
            service.check_required_credentials(ORG)
        m.assert_called_once_with("infosimples_token", ORG)

    def test_credenciais_resolvem_pelo_key_store_do_produto(self):
        """The import is the contract: `credentials.resolve_key` delegates to
        `api_keys_store.resolve_api_key` (local encrypted tier → platform
        chain), not to `resolve_credential` (platform chain only)."""
        from app.modules.certidoes import credentials
        from app.services.api_keys_store import resolve_api_key

        assert credentials.resolve_api_key is resolve_api_key
        # All three names this module needs are operator-settable in the UI.
        from app.services.api_keys_store import MANAGED_API_KEYS

        assert {
            credentials.INFOSIMPLES_TOKEN,
            credentials.INFOSIMPLES_EMAIL_ENVIO,
            credentials.OPENAI_API_KEY,
        } <= set(MANAGED_API_KEYS)


# ---------------------------------------------------------------------------
# Parameter builders — the exact per-endpoint parameter sets
# ---------------------------------------------------------------------------


class TestBuildParamsCndFederal:
    def test_cpf_com_birthdate(self):
        params = _build_params_cnd_federal(CONSULTA_CPF, "tok")
        assert params["cpf"] == "12345678901"
        assert params["birthdate"] == "1990-01-15"
        assert params["preferencia_emissao"] == "2via"
        assert params["token"] == "tok"

    def test_cnpj(self):
        params = _build_params_cnd_federal(CONSULTA_CNPJ, "tok")
        assert params["cnpj"] == "12345678000190"
        assert "cpf" not in params

    def test_sem_data_nascimento(self):
        params = _build_params_cnd_federal(CONSULTA_MINIMAL, "tok")
        assert "birthdate" not in params


class TestBuildParamsTrf3:
    """2ª instância — Cível at the Tribunal Regional Federal da 3ª Região
    (InfoSimples `tipo=1`, `abrangencia=3`)."""

    def test_cpf_payload_exato(self):
        assert _build_params_trf3(CONSULTA_CPF, "tok") == {
            "token": "tok",
            "cpf": "12345678901",
            "tipo": "1",
            "abrangencia": "3",
            "nome_social": "João da Silva",
        }

    def test_cnpj_so_documento_sem_nome_social(self):
        """`nome_social` is CPF-only per the endpoint docs."""
        assert _build_params_trf3(CONSULTA_CNPJ, "tok") == {
            "token": "tok",
            "cnpj": "12345678000190",
            "tipo": "1",
            "abrangencia": "3",
        }


class TestBuildParamsTrf3Sp:
    """1ª instância — Cível at the Seção Judiciária e JEF de São Paulo
    (InfoSimples `tipo=1`, `abrangencia=2`)."""

    def test_cpf_payload_exato(self):
        assert _build_params_trf3_sp(CONSULTA_CPF, "tok") == {
            "token": "tok",
            "cpf": "12345678901",
            "tipo": "1",
            "abrangencia": "2",
            "nome_social": "João da Silva",
        }

    def test_cnpj_so_documento_sem_nome_social(self):
        assert _build_params_trf3_sp(CONSULTA_CNPJ, "tok") == {
            "token": "tok",
            "cnpj": "12345678000190",
            "tipo": "1",
            "abrangencia": "2",
        }

    def test_mesmo_endpoint_do_regional_difere_so_na_abrangencia(self):
        """The two TRF3 entries share an endpoint and are both Cível —
        `abrangencia` (1ª vs 2ª instância) is the whole difference, which is
        why dropping one looks harmless and is not."""
        sp = _build_params_trf3_sp(CONSULTA_CPF, "tok")
        regional = _build_params_trf3(CONSULTA_CPF, "tok")
        assert sp["abrangencia"] != regional["abrangencia"]
        assert {k: v for k, v in sp.items() if k != "abrangencia"} == {
            k: v for k, v in regional.items() if k != "abrangencia"
        }

    def test_nomes_identificam_regiao_e_instancia(self):
        nomes = {c["tipo"]: c["nome"] for c in CERTIDOES_CONFIG}
        assert "São Paulo" in nomes["trf3_sp"] and "1ª instância" in nomes["trf3_sp"]
        assert "Tribunal Regional" in nomes["trf3"] and "2ª instância" in nomes["trf3"]


class TestBuildParamsTrt2Digital:
    def test_cpf_simples(self):
        params = _build_params_trt2_digital(CONSULTA_CPF, "tok")
        assert params == {"token": "tok", "cpf": "12345678901"}

    def test_cnpj_usa_cnpj_raiz(self):
        params = _build_params_trt2_digital(CONSULTA_CNPJ, "tok")
        assert params == {"token": "tok", "cnpj_raiz": "12345678000190"}


class TestBuildParamsTrt2Fisico:
    def test_inclui_nome(self):
        params = _build_params_trt2_fisico(CONSULTA_CPF, "tok")
        assert params["nome"] == "João da Silva"
        assert params["cpf"] == "12345678901"


class TestBuildParamsSimples:
    def test_apenas_token_e_doc(self):
        assert _build_params_simples(CONSULTA_CPF, "tok") == {
            "token": "tok", "cpf": "12345678901"
        }


class TestBuildParamsTjsp:
    def test_inclui_modelo(self):
        with patch(_REGISTRY_RESOLVE, return_value=None):
            assert _build_params_tjsp(CONSULTA_CPF, "tok")["modelo"] == "4"

    def test_cpf_usa_nome_completo(self):
        with patch(_REGISTRY_RESOLVE, return_value=None):
            params = _build_params_tjsp(CONSULTA_CPF, "tok")
        assert params["nome_completo"] == "João da Silva"
        assert "razao_social" not in params

    def test_cnpj_usa_razao_social(self):
        with patch(_REGISTRY_RESOLVE, return_value=None):
            params = _build_params_tjsp(CONSULTA_CNPJ, "tok")
        assert params["razao_social"] == "Empresa XPTO"
        assert "nome_completo" not in params

    def test_inclui_email_envio_quando_configurado(self):
        with patch(_REGISTRY_RESOLVE, return_value="fila@noctus.com"):
            params = _build_params_tjsp(CONSULTA_CPF, "tok")
        assert params["email_envio"] == "fila@noctus.com"

    def test_omite_email_envio_quando_nao_configurado(self):
        with patch(_REGISTRY_RESOLVE, return_value=None):
            assert "email_envio" not in _build_params_tjsp(CONSULTA_CPF, "tok")

    def test_inclui_campos_opcionais_quando_presentes(self):
        with patch(_REGISTRY_RESOLVE, return_value=None):
            params = _build_params_tjsp(CONSULTA_CPF, "tok")
        assert params["rg"] == "123456789"
        assert params["genero"] == "M"
        assert params["nome_mae"] == "Maria da Silva"
        assert params["nome_pai"] == "José da Silva"

    def test_omite_campos_opcionais_quando_ausentes(self):
        with patch(_REGISTRY_RESOLVE, return_value=None):
            params = _build_params_tjsp(CONSULTA_MINIMAL, "tok")
        for field in ("rg", "genero", "nome_mae", "nome_pai", "birthdate"):
            assert field not in params

    def test_email_resolve_pelo_seam_do_modulo(self):
        with patch(_CRED, return_value="fila@noctus.com") as m:
            _build_params_tjsp(CONSULTA_CPF, "tok")
        m.assert_called_once_with("infosimples_email_envio", ORG)


# ---------------------------------------------------------------------------
# _fetch_certidao
# ---------------------------------------------------------------------------


def _http(response_payloads):
    """An httpx client stub whose GET returns each payload in turn."""
    client = MagicMock()
    responses = []
    for payload in response_payloads:
        resp = MagicMock()
        resp.json.return_value = payload
        responses.append(resp)
    client.get = AsyncMock(side_effect=responses)
    return client


CONFIG_FEDERAL = config_for("cnd_federal")


class TestFetchCertidao:
    @pytest.mark.asyncio
    async def test_sucesso_le_site_receipt(self):
        client = _http([{
            "code": 200,
            "data": [{"site_receipt": "https://x/recibo.pdf", "situacao": "Regular"}],
        }])
        result = await service._fetch_certidao(
            CONFIG_FEDERAL, CONSULTA_CPF, "tok", client
        )
        assert result["success"] is True
        assert result["file_url"] == "https://x/recibo.pdf"
        assert result["error"] is None

    @pytest.mark.asyncio
    async def test_cenprot_le_site_receipts_da_raiz(self):
        """CENPROT puts the file URL at the ROOT, not inside data[0]."""
        client = _http([{
            "code": 200,
            "data": [{"protestos": []}],
            "site_receipts": ["https://x/cenprot.html"],
        }])
        result = await service._fetch_certidao(
            config_for("cenprot"), CONSULTA_CPF, "tok", client
        )
        assert result["file_url"] == "https://x/cenprot.html"

    @pytest.mark.asyncio
    async def test_612_e_sucesso_nada_consta(self):
        """612 is 'no data at source' — for a certidão that IS the good news."""
        client = _http([{"code": 612, "errors": ["Nada consta"]}])
        result = await service._fetch_certidao(
            CONFIG_FEDERAL, CONSULTA_CPF, "tok", client
        )
        assert result["success"] is True
        assert result["nada_consta"] == "Nada consta"
        assert result["file_url"] is None

    @pytest.mark.asyncio
    async def test_612_sem_errors_usa_default(self):
        client = _http([{"code": 612}])
        result = await service._fetch_certidao(
            CONFIG_FEDERAL, CONSULTA_CPF, "tok", client
        )
        assert result["nada_consta"] == "Nada consta"

    @pytest.mark.asyncio
    async def test_erro_4xx_nao_retenta(self):
        client = _http([{"code": 400, "errors": ["CPF inválido"]}] * 3)
        result = await service._fetch_certidao(
            CONFIG_FEDERAL, CONSULTA_CPF, "tok", client
        )
        assert result["success"] is False
        assert "CPF inválido" in result["error"]
        assert client.get.await_count == 1

    @pytest.mark.asyncio
    async def test_erro_5xx_retenta_ate_max(self):
        client = _http([{"code": 500, "message": "boom"}] * service.MAX_RETRIES)
        with patch("asyncio.sleep", new=AsyncMock()):
            result = await service._fetch_certidao(
                CONFIG_FEDERAL, CONSULTA_CPF, "tok", client
            )
        assert result["success"] is False
        assert client.get.await_count == service.MAX_RETRIES

    @pytest.mark.asyncio
    async def test_erro_especifico_e_generico_combinados(self):
        client = _http([{"code": 400, "errors": ["Sem RG"], "message": "params"}])
        result = await service._fetch_certidao(
            CONFIG_FEDERAL, CONSULTA_CPF, "tok", client
        )
        assert result["error"] == "Sem RG (params)"

    @pytest.mark.asyncio
    async def test_excecao_de_rede_vira_erro_reportado(self):
        client = MagicMock()
        client.get = AsyncMock(side_effect=httpx.ConnectError("down"))
        with patch("asyncio.sleep", new=AsyncMock()):
            result = await service._fetch_certidao(
                CONFIG_FEDERAL, CONSULTA_CPF, "tok", client
            )
        assert result["success"] is False
        assert "down" in result["error"]
        assert result["raw_response"] is None


# ---------------------------------------------------------------------------
# _download_file / _convert_html_to_pdf
# ---------------------------------------------------------------------------


class TestDownloadFile:
    @pytest.mark.asyncio
    async def test_200_retorna_bytes_e_content_type(self):
        resp = MagicMock(status_code=200, content=b"%PDF-1.4 x")
        resp.headers = {"content-type": "application/pdf"}
        client = MagicMock(get=AsyncMock(return_value=resp))
        assert await service._download_file("https://x/f.pdf", client) == (
            b"%PDF-1.4 x", "application/pdf"
        )

    @pytest.mark.asyncio
    async def test_404_retorna_none(self):
        resp = MagicMock(status_code=404, content=b"")
        resp.headers = {}
        client = MagicMock(get=AsyncMock(return_value=resp))
        assert await service._download_file("https://x/f.pdf", client) is None

    @pytest.mark.asyncio
    async def test_excecao_retorna_none(self):
        client = MagicMock(get=AsyncMock(side_effect=httpx.ReadTimeout("t")))
        assert await service._download_file("https://x/f.pdf", client) is None


class TestConvertHtmlToPdf:
    def test_converte_html_simples(self):
        pdf = service._convert_html_to_pdf(b"<html><body><p>oi</p></body></html>")
        assert pdf is not None
        assert pdf[:5] == b"%PDF-"

    def test_html_vazio_ainda_produz_pdf(self):
        pdf = service._convert_html_to_pdf(b"")
        assert pdf is None or pdf[:5] == b"%PDF-"

    def test_html_invalido_nao_crasheia(self):
        assert service._convert_html_to_pdf(b"<<<>>> nao e html") is not None


class TestConvertHtmlToPdfNeverFetches:
    """The real `_convert_html_to_pdf` renders from the given bytes only.

    2026-09-15: fetching a TRF3 receipt's stylesheets and images made one
    conversion take 92 s and froze prod. A local HTTP server stands in for
    the receipt's origin; the page points every kind of reference at it
    (`<base href>`, root-relative and absolute stylesheet and image), and the
    server must see zero requests."""

    @staticmethod
    def _start_server(hits: list[str]) -> http.server.HTTPServer:
        class _Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 — stdlib method name
                hits.append(self.path)
                self.send_response(200)
                self.send_header("Content-Type", "text/css")
                self.end_headers()
                self.wfile.write(b"p { color: red }")

            def log_message(self, *args) -> None:
                pass  # keep test output quiet

        server = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        return server

    def test_nenhum_recurso_referenciado_e_buscado(self):
        hits: list[str] = []
        server = self._start_server(hits)
        try:
            host, port = server.server_address
            origin = f"http://{host}:{port}"
            html_bytes = (
                f'<html><head><base href="{origin}/certidao/recibo">'
                f'<link rel="stylesheet" href="/css/site.css">'
                f'<link rel="stylesheet" href="{origin}/css/abs.css">'
                f'</head><body><img src="/imagens/logo.png">'
                f'<img src="{origin}/imagens/brasao.png">'
                f"<p>conteudo</p></body></html>"
            ).encode()
            pdf = service._convert_html_to_pdf(html_bytes)
        finally:
            server.shutdown()
        assert pdf is not None
        assert pdf[:5] == b"%PDF-"
        assert hits == []

    def test_imagem_data_uri_ainda_renderiza(self):
        png_1x1 = (
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8Dw"
            "HwAFBQIAX8jx0gAAAABJRU5ErkJggg=="
        )
        html_bytes = (
            f'<html><body><img src="data:image/png;base64,{png_1x1}">'
            f"<p>conteudo</p></body></html>"
        ).encode()
        pdf = service._convert_html_to_pdf(html_bytes)
        assert pdf is not None
        assert pdf[:5] == b"%PDF-"
        assert b"/Subtype /Image" in pdf


class TestCenprotProtocoloConsulta:
    def test_extrai_do_data_0(self):
        raw = {"code": 200, "data": [{"protocolo_consulta": "26091412345"}]}
        assert service._cenprot_protocolo_consulta(raw) == "26091412345"

    def test_612_sem_protocolo_retorna_none(self):
        """A 612 has `data: []` — no `protocolo_consulta` anywhere, per
        InfoSimples docs (read 2026-09-14)."""
        raw = {"code": 612, "data": [], "errors": ["Nada consta"]}
        assert service._cenprot_protocolo_consulta(raw) is None

    def test_none_ou_vazio_retorna_none(self):
        assert service._cenprot_protocolo_consulta(None) is None
        assert service._cenprot_protocolo_consulta({}) is None
        assert service._cenprot_protocolo_consulta({"data": [{}]}) is None
        assert service._cenprot_protocolo_consulta(
            {"data": [{"protocolo_consulta": ""}]}
        ) is None


class TestWithProtocoloStamp:
    def test_insere_apos_body(self):
        out = service._with_protocolo_stamp(
            b"<html><body><h1>Receipt</h1></body></html>", "26091412345"
        )
        assert out.startswith(b"<html><body>")
        assert b"Protocolo da consulta:</b> 26091412345" in out
        assert out.index(b"Protocolo da consulta") < out.index(b"<h1>Receipt</h1>")

    def test_insere_apos_body_com_atributos(self):
        out = service._with_protocolo_stamp(
            b'<html><body class="x"><h1>Receipt</h1></body></html>', "999"
        )
        assert b'<body class="x"><p><b>Protocolo' in out

    def test_html_escapa_o_valor(self):
        out = service._with_protocolo_stamp(
            b"<html><body></body></html>", "<script>alert(1)</script>"
        )
        assert b"<script>alert(1)</script>" not in out
        assert b"&lt;script&gt;" in out

    def test_sem_body_prepende(self):
        out = service._with_protocolo_stamp(b"<p>sem body aqui</p>", "42")
        assert out.startswith(b"<p><b>Protocolo")
        assert b"<p>sem body aqui</p>" in out


# ---------------------------------------------------------------------------
# AI analysis
# ---------------------------------------------------------------------------


#: The analysis provider is an INPUT to `_analyze_with_ai`, so every test
#: states it — PASSED through the `resolve_provider` DI seam, never
#: monkeypatched onto `api_keys_store`.
#:
#: Both halves of that are load-bearing. Leaving it ambient made three tests
#: pass locally (where a root `.env` configures Supabase) and fail in CI
#: (where nothing does, and the read raised `supabase_url is required`) — a
#: false green only the pipeline could see. And patching our own module
#: attribute instead would trade that for a worse one: the test would assert
#: against the patch rather than the seam, which the compliance keeper flags
#: high and this codebase forbids outright.
def _provider(valor):
    """A `resolve_provider` stub declaring what this org chose."""
    return lambda _org_id: valor


def _provider_raising(exc):
    """A `resolve_provider` stub whose read fails, as an unconfigured
    Supabase does in CI."""
    def _boom(_org_id):
        raise exc
    return _boom


class TestAnalyzeWithAi:
    @pytest.mark.asyncio
    async def test_sem_chave_retorna_marcador_em_portugues(self):
        """Not None: an empty column reads as a broken feature. The marker says
        WHICH setting is missing, in the language the operator reads."""
        with patch(_CRED, return_value=None):
            out = await service._analyze_with_ai(
                "texto", ORG, resolve_provider=_provider("openai")
            )
        assert "Análise IA não disponível" in out
        assert "OpenAI API Key" in out

    @pytest.mark.asyncio
    async def test_com_chave_chama_seed_chat_completion(self):
        with patch(_CRED, return_value="sk-x"), patch(
            "app.modules.certidoes.service.chat_completion",
            new=AsyncMock(return_value="Tudo regular."),
        ) as chat:
            out = await service._analyze_with_ai(
                "texto", ORG, resolve_provider=_provider("openai")
            )
        assert out == "Tudo regular."
        kwargs = chat.await_args.kwargs
        assert kwargs["org_id"] == ORG
        assert kwargs["model"] == "gpt-4.1-mini"

    @pytest.mark.asyncio
    async def test_o_provedor_selecionado_roteia_chamada_e_modelo(self):
        """🔴 The provider and the model move together or not at all.

        `gpt-4.1-mini` sent to Anthropic is a 404, and the operator who just
        flipped the switch would read that as a broken key. This asserts the
        pair, not just the provider.
        """
        with patch(_CRED, return_value="sk-ant-x"), patch(
            "app.modules.certidoes.service.chat_completion",
            new=AsyncMock(return_value="Consta débito."),
        ) as chat:
            out = await service._analyze_with_ai(
                "texto", ORG, resolve_provider=_provider("anthropic")
            )
        assert out == "Consta débito."
        kwargs = chat.await_args.kwargs
        assert kwargs["provider"] == "anthropic"
        # The measured document-analysis pin (seed `documents.providers`).
        assert kwargs["model"] == "claude-haiku-4-5"

    @pytest.mark.asyncio
    async def test_a_chave_conferida_e_a_do_provedor_escolhido(self):
        """An org running on Anthropic must not be told its OpenAI key is
        missing. Checking OpenAI's key regardless of the selection refuses
        work the configured vendor can do — and trains the operator to
        ignore the one message that panel exists to show.
        """
        with patch(_CRED, return_value=None) as cred:
            out = await service._analyze_with_ai(
                "texto", ORG, resolve_provider=_provider("anthropic")
            )
        assert cred.call_args.args[0] == "anthropic_api_key"
        assert "Anthropic" in out
        assert "OpenAI" not in out

    @pytest.mark.asyncio
    async def test_setting_ilegivel_nao_derruba_o_job_nem_escolhe_vendor(self):
        """🔴 The regression CI caught, pinned.

        `resolve_api_key_detail` catches only `EncryptionNotConfigured`, so an
        unconfigured Supabase raises `supabase_url is required` right through
        it. This runs detached from a request, so that exception surfaced
        nowhere and left the certidão with no analysis and no reason.

        Two assertions, and the second is the one with teeth: it must not
        crash, AND it must not quietly fall back to a vendor. Defaulting to
        OpenAI here would run an org that chose Anthropic on the other vendor
        with nothing said — the silent switch the whole design forbids.
        """
        with patch(
            "app.modules.certidoes.service.chat_completion", new=AsyncMock()
        ) as chat:
            out = await service._analyze_with_ai(
                "texto",
                ORG,
                resolve_provider=_provider_raising(
                    RuntimeError("supabase_url is required")
                ),
            )
        assert "Análise IA não disponível" in out
        chat.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_falha_do_provedor_vira_none_nao_excecao_nem_texto_de_erro(
        self, caplog
    ):
        """🔴 The regression this pins: a vendor error must never land in
        `analise_ia` (prod showed the raw `AsyncMessages.create() got an
        unexpected keyword argument 'temperature'` as if it were the
        analysis, 2026-09-10 onward). NULL + a logged error, not a marker
        string — the column is a due-diligence read surface, not an error
        channel."""
        with patch(_CRED, return_value="sk-x"), patch(
            "app.modules.certidoes.service.chat_completion",
            new=AsyncMock(side_effect=RuntimeError("429")),
        ), caplog.at_level(logging.ERROR):
            out = await service._analyze_with_ai(
                "texto", ORG, resolve_provider=_provider("openai")
            )
        assert out is None
        assert any(
            "AI analysis failed" in r.getMessage() and ORG in r.getMessage()
            for r in caplog.records
        )


# ---------------------------------------------------------------------------
# Storage — the one real rewrite from the ERP
# ---------------------------------------------------------------------------


class TestStorageKey:
    def test_org_id_e_o_primeiro_segmento(self):
        """🔴 The bucket's object-RLS policies match on the FIRST path segment.
        A key shaped any other way is readable across orgs."""
        key = service.storage_key(ORG, "consulta-001", "tjsp")
        assert key.startswith(f"{ORG}/certidoes/consulta-001/tjsp_")
        assert key.endswith(".pdf")

    def test_sufixo_aleatorio_nao_sobrescreve_reemissao(self):
        a = service.storage_key(ORG, "c1", "tjsp")
        b = service.storage_key(ORG, "c1", "tjsp")
        assert a != b

    def test_is_storage_key_distingue_url_de_chave(self):
        assert service.is_storage_key(f"{ORG}/certidoes/c1/tjsp_ab.pdf") is True
        assert service.is_storage_key("https://infosimples/x.pdf") is False
        assert service.is_storage_key(None) is False
        assert service.is_storage_key("") is False


class TestPersistPdf:
    @pytest.mark.asyncio
    async def test_grava_no_bucket_e_devolve_a_chave(self):
        storage = FakeStorageBackend()
        key = await service._persist_pdf(
            b"%PDF-1.4", storage, ORG, "consulta-001", "cnd_federal"
        )
        assert key is not None
        blob = await storage.get(bucket=service.BUCKET, key=key)
        assert blob is not None and blob.data == b"%PDF-1.4"

    @pytest.mark.asyncio
    async def test_sem_org_id_nao_grava_e_devolve_none(self):
        storage = FakeStorageBackend()
        assert await service._persist_pdf(
            b"%PDF-", storage, None, "consulta-001", "tjsp"
        ) is None
        assert await storage.list_keys(bucket=service.BUCKET) == []

    @pytest.mark.asyncio
    async def test_falha_do_backend_devolve_none_sem_propagar(self):
        """A storage outage must not lose the certidão: the caller keeps the
        upstream URL, so the file is still reachable."""
        storage = MagicMock()
        storage.put = AsyncMock(side_effect=RuntimeError("bucket down"))
        assert await service._persist_pdf(
            b"%PDF-", storage, ORG, "c1", "tjsp"
        ) is None


class TestReadCertidaoBytes:
    @pytest.mark.asyncio
    async def test_chave_le_pelo_seam_sem_http(self):
        storage = FakeStorageBackend()
        key = f"{ORG}/certidoes/c1/tjsp_ab.pdf"
        await storage.put(bucket=service.BUCKET, key=key, data=b"%PDF-x")
        http = MagicMock(get=AsyncMock(side_effect=AssertionError("must not HTTP")))
        assert await service.read_certidao_bytes(key, storage, http) == b"%PDF-x"

    @pytest.mark.asyncio
    async def test_url_externa_cai_no_proxy_http(self):
        resp = MagicMock(status_code=200, content=b"%PDF-remote")
        resp.headers = {"content-type": "application/pdf"}
        http = MagicMock(get=AsyncMock(return_value=resp))
        out = await service.read_certidao_bytes(
            "https://infosimples/x.pdf", FakeStorageBackend(), http
        )
        assert out == b"%PDF-remote"

    @pytest.mark.asyncio
    async def test_chave_ausente_devolve_none(self):
        http = MagicMock(get=AsyncMock())
        assert await service.read_certidao_bytes(
            f"{ORG}/certidoes/c1/sumiu.pdf", FakeStorageBackend(), http
        ) is None


class TestDeleteStorageFiles:
    @pytest.mark.asyncio
    async def test_apaga_de_verdade_pelo_seam(self):
        """ERP bypassed its own StorageService here because that service fell
        back to a silent dry-run. The seam deletes; nothing to work around."""
        storage = FakeStorageBackend()
        key = f"{ORG}/certidoes/c1/tjsp_ab.pdf"
        await storage.put(bucket=service.BUCKET, key=key, data=b"x")
        deleted = await service.delete_storage_files([{"arquivo_url": key}], storage)
        assert deleted == 1
        assert await storage.exists(bucket=service.BUCKET, key=key) is False

    @pytest.mark.asyncio
    async def test_ignora_urls_externas(self):
        storage = FakeStorageBackend()
        assert await service.delete_storage_files(
            [{"arquivo_url": "https://infosimples/x.pdf"}, {"arquivo_url": None}],
            storage,
        ) == 0

    @pytest.mark.asyncio
    async def test_falha_em_um_arquivo_nao_impede_os_outros(self):
        storage = MagicMock()
        storage.delete = AsyncMock(side_effect=[RuntimeError("nope"), True])
        deleted = await service.delete_storage_files(
            [{"arquivo_url": "a/certidoes/c/1.pdf"}, {"arquivo_url": "a/certidoes/c/2.pdf"}],
            storage,
        )
        assert deleted == 1


# ---------------------------------------------------------------------------
# _process_single_certidao
# ---------------------------------------------------------------------------


class _FakeHttp:
    """An `httpx.AsyncClient` stand-in answering BOTH calls the pipeline makes.

    🔴 THIS REPLACED A `patch.object(service, "_fetch_certidao", ...)`.

    Both the InfoSimples API call and the file download that follows it go
    through the SAME client, so a double has to route on the URL. Doing that
    rather than swapping our own `_fetch_certidao` out means the real retry
    ladder, the 612 / "nada consta" branch, the CENPROT `site_receipts`
    fallback and the error-extraction precedence all actually RUN — which is
    the behaviour the ERP port had to preserve exactly, and which a stubbed
    `_fetch_certidao` asserted nothing about.

    `httpx` is the external boundary here; it is the only thing being faked.
    """

    def __init__(
        self,
        api_payload: dict,
        *,
        file_body: bytes = b"%PDF-1.4 real",
        file_content_type: str = "application/pdf",
        file_status: int = 200,
    ):
        self.api_payload = api_payload
        self.file_body = file_body
        self.file_content_type = file_content_type
        self.file_status = file_status
        self.api_calls: list[dict] = []
        self.downloaded: list[str] = []

    async def get(self, url, **kwargs):
        if url.startswith(service.INFOSIMPLES_BASE_URL):
            self.api_calls.append(kwargs.get("params") or {})
            resp = MagicMock()
            resp.json.return_value = self.api_payload
            return resp
        self.downloaded.append(url)
        resp = MagicMock(status_code=self.file_status, content=self.file_body)
        resp.headers = {"content-type": self.file_content_type}
        return resp


def _api_ok(file_url="https://x/f.pdf", data=None) -> dict:
    """A real InfoSimples 200 envelope, as the API returns it."""
    return {
        "code": 200,
        "data": data or [{"site_receipt": file_url, "situacao": "Regular"}],
    }


class _Recorder:
    """An awaitable stand-in for `_process_single_certidao`, recording what the
    fan-out decided to run.

    Injected through `processar_consulta(process_one=...)` rather than patched
    over the module attribute: what these tests assert is the DISPATCH decision
    (which resultados run now, which are queued, which are skipped), and that is
    exactly what stays observable when the collaborator is a parameter.
    """

    def __init__(self):
        self.calls: list[tuple] = []

    @property
    def count(self) -> int:
        return len(self.calls)

    @property
    def resultado_ids(self) -> list[str]:
        return [c[4] for c in self.calls]

    async def __call__(self, *args, **kwargs):
        self.calls.append(args)


class _SyncRecorder:
    """`_Recorder`'s synchronous twin — `schedule_tjsp_for_org` is a plain
    function, and awaiting a recorder that is not awaitable would be a
    different bug than the one under test."""

    def __init__(self):
        self.calls: list[tuple] = []

    @property
    def count(self) -> int:
        return len(self.calls)

    def __call__(self, *args, **kwargs):
        self.calls.append(args)


async def _noop_analyze(text, org_id=None):
    """The `analyze=` DI seam's stand-in. The AI call is a separate concern
    with its own tests (`TestAnalyzeWithAi`); here it must simply not fire."""
    return "ok"


async def _noop_extract_text(pdf_bytes, nome_display, org_id=None):
    """The `extract_text=` DI seam's stand-in — mirrors `_noop_analyze`'s
    role. Migration 113's transcription leg is a separate concern with its
    own tests (`TestExtractPdfText`, `TestProcessSingleCertidaoTranscricao`);
    a test not about it must not pay for a real seed transcriber call
    against a garbage/converted PDF."""
    return service.ExtractedPdfText(para_ia=None)


class TestProcessSingleCertidao:
    @pytest.mark.asyncio
    async def test_pdf_vai_para_o_bucket_e_arquivo_url_guarda_a_chave(self):
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[_resultado()],
        )
        storage = FakeStorageBackend()
        http = _FakeHttp(_api_ok(), file_body=b"%PDF-1.4 real")

        await service._process_single_certidao(
            CONFIG_FEDERAL, _consulta_row(), "tok", db,
            "resultado-001", http, storage,
            analyze=_noop_analyze, extract_text=_noop_extract_text,
            core_db=MockSupabaseClient(schema="public"),
        )

        row = db.table("certidao_resultados").select("*").eq(
            "id", "resultado-001"
        ).execute().data[0]
        assert row["status"] == "sucesso"
        assert service.is_storage_key(row["arquivo_url"])
        assert row["arquivo_url"].startswith(f"{ORG}/certidoes/consulta-001/")
        assert row["arquivo_nome"] == "cnd_federal.pdf"
        blob = await storage.get(bucket=service.BUCKET, key=row["arquivo_url"])
        assert blob.data == b"%PDF-1.4 real"
        # The REAL param builder ran, against the real endpoint URL.
        assert http.api_calls[0]["cpf"] == "12345678901"
        assert http.downloaded == ["https://x/f.pdf"]

    @pytest.mark.asyncio
    async def test_html_e_convertido_antes_de_gravar(self):
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[_resultado(tipo="cenprot", id="r-html")],
        )
        storage = FakeStorageBackend()
        http = _FakeHttp(
            _api_ok(),
            file_body=b"<html><body>oi</body></html>",
            file_content_type="text/html",
        )

        await service._process_single_certidao(
            config_for("cenprot"), _consulta_row(), "tok", db,
            "r-html", http, storage,
            analyze=_noop_analyze, extract_text=_noop_extract_text,
            core_db=MockSupabaseClient(schema="public"),
        )

        row = db.table("certidao_resultados").select("*").eq(
            "id", "r-html"
        ).execute().data[0]
        blob = await storage.get(bucket=service.BUCKET, key=row["arquivo_url"])
        assert blob.data[:5] == b"%PDF-"

    @pytest.mark.asyncio
    async def test_cenprot_le_o_site_receipts_da_raiz(self):
        """CENPROT puts the file URL at the ROOT, not in `data[0]`. Reachable
        now that the real `_fetch_certidao` runs in this path."""
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[_resultado(tipo="cenprot", id="r-cenprot")],
        )
        http = _FakeHttp(
            {
                "code": 200,
                "data": [{"protestos": []}],
                "site_receipts": ["https://x/cenprot.html"],
            },
            file_body=b"<html>ok</html>",
            file_content_type="text/html",
        )
        await service._process_single_certidao(
            config_for("cenprot"), _consulta_row(), "tok", db,
            "r-cenprot", http, FakeStorageBackend(),
            analyze=_noop_analyze, extract_text=_noop_extract_text,
            core_db=MockSupabaseClient(schema="public"),
        )
        assert http.downloaded == ["https://x/cenprot.html"]

    @pytest.mark.asyncio
    async def test_cenprot_200_com_protocolo_e_gravado_no_pdf(self):
        """A CENPROT 200 ("protests found") response carries
        `data[0].protocolo_consulta` — the receipt itself never prints it, so
        it must land in the stored PDF's text, not just the API response
        JSON."""
        import fitz

        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[_resultado(tipo="cenprot", id="r-protocolo")],
        )
        storage = FakeStorageBackend()
        http = _FakeHttp(
            {
                "code": 200,
                "data": [{
                    "protocolo_consulta": "26091412345678",
                    "documento_pesquisado": "12345678901",
                    "quantidade_titulos": 0,
                }],
                "site_receipts": ["https://x/cenprot.html"],
            },
            file_body=b"<html><body><h1>Receipt</h1></body></html>",
            file_content_type="text/html",
        )

        await service._process_single_certidao(
            config_for("cenprot"), _consulta_row(), "tok", db,
            "r-protocolo", http, storage,
            analyze=_noop_analyze, extract_text=_noop_extract_text,
            core_db=MockSupabaseClient(schema="public"),
        )

        row = db.table("certidao_resultados").select("*").eq(
            "id", "r-protocolo"
        ).execute().data[0]
        blob = await storage.get(bucket=service.BUCKET, key=row["arquivo_url"])
        doc = fitz.open(stream=blob.data, filetype="pdf")
        texto = doc[0].get_text()
        doc.close()
        assert "Protocolo da consulta: 26091412345678" in texto

    @pytest.mark.asyncio
    async def test_cenprot_612_nada_consta_nao_grava_protocolo(self):
        """612 ("nada consta") has no `protocolo_consulta` anywhere — the
        stamp must not be inserted for it."""
        import fitz

        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[_resultado(tipo="cenprot", id="r-612")],
        )
        storage = FakeStorageBackend()
        http = _FakeHttp(
            {
                "code": 612,
                "data": [],
                "errors": ["Nada consta"],
                "site_receipts": ["https://x/cenprot-612.html"],
            },
            file_body=b"<html><body><h1>Nada consta</h1></body></html>",
            file_content_type="text/html",
        )

        await service._process_single_certidao(
            config_for("cenprot"), _consulta_row(), "tok", db,
            "r-612", http, storage,
            analyze=_noop_analyze, extract_text=_noop_extract_text,
            core_db=MockSupabaseClient(schema="public"),
        )

        row = db.table("certidao_resultados").select("*").eq(
            "id", "r-612"
        ).execute().data[0]
        blob = await storage.get(bucket=service.BUCKET, key=row["arquivo_url"])
        doc = fitz.open(stream=blob.data, filetype="pdf")
        texto = doc[0].get_text()
        doc.close()
        assert "Protocolo da consulta" not in texto

    @pytest.mark.asyncio
    async def test_content_type_desconhecido_mantem_a_url_de_origem(self):
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[_resultado()],
        )
        storage = FakeStorageBackend()
        http = _FakeHttp(
            _api_ok(), file_body=b"\x89PNG\r\n", file_content_type="image/png"
        )

        await service._process_single_certidao(
            CONFIG_FEDERAL, _consulta_row(), "tok", db,
            "resultado-001", http, storage,
            analyze=_noop_analyze, extract_text=_noop_extract_text,
            core_db=MockSupabaseClient(schema="public"),
        )

        row = db.table("certidao_resultados").select("*").eq(
            "id", "resultado-001"
        ).execute().data[0]
        assert row["arquivo_url"] == "https://x/f.pdf"
        assert await storage.list_keys(bucket=service.BUCKET) == []

    @pytest.mark.asyncio
    async def test_nada_consta_sem_recibo_e_sucesso_sem_arquivo(self):
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[_resultado()],
        )
        http = _FakeHttp({"code": 612, "errors": ["Nada consta"]})
        await service._process_single_certidao(
            CONFIG_FEDERAL, _consulta_row(), "tok", db,
            "resultado-001", http, FakeStorageBackend(),
            analyze=_noop_analyze, extract_text=_noop_extract_text,
            core_db=MockSupabaseClient(schema="public"),
        )
        row = db.table("certidao_resultados").select("*").eq(
            "id", "resultado-001"
        ).execute().data[0]
        assert row["status"] == "sucesso"
        assert row["analise_ia"] == "Nada consta"
        assert row["arquivo_url"] is None
        assert http.downloaded == []

    @pytest.mark.asyncio
    async def test_nada_consta_com_recibo_grava_o_recibo(self):
        """CENPROT answers a clean search with 612 + a synthesized receipt at
        the ROOT `site_receipts` — the only document the lookup has. It must
        land in our bucket (as PDF) so the row can be viewed and downloaded;
        before, the row was `sucesso` with no file and no icons."""
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[_resultado(tipo="cenprot", id="r-cenprot")],
        )
        storage = FakeStorageBackend()
        http = _FakeHttp(
            {
                "code": 612,
                "errors": ["Não constam protestos"],
                "data": [],
                "site_receipts": ["https://x/cenprot.html"],
            },
            file_body=b"<html><body>Nao constam protestos</body></html>",
            file_content_type="text/html",
        )
        await service._process_single_certidao(
            config_for("cenprot"), _consulta_row(), "tok", db,
            "r-cenprot", http, storage,
            analyze=_noop_analyze, extract_text=_noop_extract_text,
            core_db=MockSupabaseClient(schema="public"),
        )
        row = db.table("certidao_resultados").select("*").eq(
            "id", "r-cenprot"
        ).execute().data[0]
        assert row["status"] == "sucesso"
        assert row["analise_ia"] == "Não constam protestos"
        assert http.downloaded == ["https://x/cenprot.html"]
        assert service.is_storage_key(row["arquivo_url"])
        assert row["arquivo_nome"] == "cenprot.pdf"
        blob = await storage.get(bucket=service.BUCKET, key=row["arquivo_url"])
        assert blob.data[:5] == b"%PDF-"

    @pytest.mark.asyncio
    async def test_falha_grava_erro_e_mensagem(self):
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[_resultado()],
        )
        http = _FakeHttp({"code": 400, "errors": ["CPF inválido"]})
        await service._process_single_certidao(
            CONFIG_FEDERAL, _consulta_row(), "tok", db,
            "resultado-001", http, FakeStorageBackend(),
            analyze=_noop_analyze, extract_text=_noop_extract_text,
            core_db=MockSupabaseClient(schema="public"),
        )
        row = db.table("certidao_resultados").select("*").eq(
            "id", "resultado-001"
        ).execute().data[0]
        assert row["status"] == "erro"
        assert row["erro_mensagem"] == "CPF inválido"

    @pytest.mark.asyncio
    async def test_api_requested_at_e_gravado_antes_da_chamada(self):
        """🔴 The TJSP cooldown reads this column and nothing else. If it were
        only written on success, a failed request — which still consumed the
        30-minute window at TJSP — would look like no request at all."""
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[_resultado(tipo=TJSP_TIPO)],
        )
        with patch(_REGISTRY_RESOLVE, return_value=None):
            await service._process_single_certidao(
                config_for(TJSP_TIPO), _consulta_row(), "tok", db,
                "resultado-001", _FakeHttp({"code": 400, "errors": ["x"]}),
                FakeStorageBackend(),
                analyze=_noop_analyze, extract_text=_noop_extract_text,
                core_db=MockSupabaseClient(schema="public"),
            )
        row = db.table("certidao_resultados").select("*").eq(
            "id", "resultado-001"
        ).execute().data[0]
        assert row["status"] == "erro"
        assert row["api_requested_at"] is not None

    @pytest.mark.asyncio
    async def test_infosimples_spend_is_booked_to_cost_ledger(self):
        """Custos-page slice: a successful call with a `header.price` books
        one `public.cost_ledger` row via the injected `core_db` seam
        (DIFFERENT client from `db`, which stays social_wiring-scoped)."""
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[_resultado()],
        )
        core_db = MockSupabaseClient(schema="public")
        http = _FakeHttp(
            {**_api_ok(), "header": {"price": "1.23"}},
            file_body=b"%PDF-1.4 real",
        )

        await service._process_single_certidao(
            CONFIG_FEDERAL, _consulta_row(), "tok", db,
            "resultado-001", http, FakeStorageBackend(),
            analyze=_noop_analyze, extract_text=_noop_extract_text,
            core_db=core_db,
        )

        rows = core_db.table("cost_ledger").select("*").execute().data
        assert len(rows) == 1
        assert rows[0]["org_id"] == ORG
        assert rows[0]["category"] == "infosimples"
        assert rows[0]["step"] == "certidoes.cnd_federal"
        assert rows[0]["reference_id"] == "resultado-001"
        assert rows[0]["amount_native"] == "1.23"

    @pytest.mark.asyncio
    async def test_no_header_price_never_invents_a_cost_row(self):
        """`_api_ok()` (the real InfoSimples 200 envelope this suite ports
        from) carries no `header` — confirms the honest-skip path, not a
        guessed price."""
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[_resultado(id="resultado-noheader")],
        )
        core_db = MockSupabaseClient(schema="public")
        http = _FakeHttp(_api_ok(), file_body=b"%PDF-1.4 real")

        await service._process_single_certidao(
            CONFIG_FEDERAL, _consulta_row(), "tok", db,
            "resultado-noheader", http, FakeStorageBackend(),
            analyze=_noop_analyze, extract_text=_noop_extract_text,
            core_db=core_db,
        )

        assert core_db.table("cost_ledger").select("*").execute().data == []


# ---------------------------------------------------------------------------
# _atualizar_status_consulta
# ---------------------------------------------------------------------------


def _status_db(statuses: list[str]) -> MockSupabaseClient:
    return _db(
        certidao_consultas=[_consulta_row()],
        certidao_resultados=[
            _resultado(id=f"r{i}", status=s, ordem=i + 1)
            for i, s in enumerate(statuses)
        ],
    )


class TestAtualizarStatusConsulta:
    def _consulta(self, db):
        return db.table("certidao_consultas").select("*").eq(
            "id", "consulta-001"
        ).execute().data[0]

    def test_todos_sucesso_vira_concluida(self):
        db = _status_db(["sucesso", "sucesso"])
        service._atualizar_status_consulta("consulta-001", ORG, db)
        row = self._consulta(db)
        assert row["status"] == "concluida"
        assert row["concluidas"] == 2

    def test_todos_erro_vira_erro(self):
        db = _status_db(["erro", "erro"])
        service._atualizar_status_consulta("consulta-001", ORG, db)
        assert self._consulta(db)["status"] == "erro"

    def test_um_na_fila_mantem_processando(self):
        db = _status_db(["sucesso", "na_fila"])
        service._atualizar_status_consulta("consulta-001", ORG, db)
        assert self._consulta(db)["status"] == "processando"

    def test_misto_sucesso_e_erro_vira_concluida(self):
        """One failure does not make the consulta a failure — nine certidões
        that DID come back are still nine certidões."""
        db = _status_db(["sucesso", "erro"])
        service._atualizar_status_consulta("consulta-001", ORG, db)
        row = self._consulta(db)
        assert row["status"] == "concluida"
        assert row["concluidas"] == 1

    def test_conta_apenas_resultados_da_propria_org(self):
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[
                _resultado(id="mine", status="sucesso"),
                _resultado(id="theirs", status="sucesso", org_id=OTHER_ORG),
            ],
        )
        service._atualizar_status_consulta("consulta-001", ORG, db)
        assert self._consulta(db)["concluidas"] == 1


# ---------------------------------------------------------------------------
# processar_consulta
# ---------------------------------------------------------------------------


class TestProcessarConsulta:
    @pytest.mark.asyncio
    async def test_sem_token_marca_tudo_erro_com_mensagem_acionavel(self):
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[_resultado(id="r1"), _resultado(id="r2", ordem=2)],
        )
        with patch(_CRED, return_value=None):
            await service.processar_consulta("consulta-001", db, FakeStorageBackend())

        rows = db.table("certidao_resultados").select("*").execute().data
        assert all(r["status"] == "erro" for r in rows)
        assert "Token InfoSimples não configurado" in rows[0]["erro_mensagem"]
        consulta = db.table("certidao_consultas").select("*").execute().data[0]
        assert consulta["status"] == "erro"

    @pytest.mark.asyncio
    async def test_tjsp_em_cooldown_vai_para_na_fila_e_agenda(self):
        recent = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[
                _resultado(id="r-tjsp", tipo=TJSP_TIPO, ordem=7,
                           api_requested_at=recent),
            ],
        )
        scheduled: list[tuple] = []
        with patch(_CRED, return_value="tok"):
            await service.processar_consulta(
                "consulta-001", db, FakeStorageBackend(),
                schedule_tjsp=lambda *a: scheduled.append(a),
            )

        row = db.table("certidao_resultados").select("*").eq(
            "id", "r-tjsp"
        ).execute().data[0]
        assert row["status"] == "na_fila"
        assert len(scheduled) == 1 and scheduled[0][0] == ORG

    @pytest.mark.asyncio
    async def test_tjsp_sem_historico_roda_imediatamente(self):
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[_resultado(id="r-tjsp", tipo=TJSP_TIPO, ordem=7)],
        )
        processed = _Recorder()
        with patch(_CRED, return_value="tok"):
            await service.processar_consulta(
                "consulta-001", db, FakeStorageBackend(), process_one=processed,
            )
        assert processed.count == 1

    @pytest.mark.asyncio
    async def test_tipo_fora_do_registro_e_pulado_com_log_nao_derruba_o_resto(self):
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[
                _resultado(id="r-ok"),
                _resultado(id="r-orfao", tipo="tipo_removido", ordem=99),
            ],
        )
        processed = _Recorder()
        with patch(_CRED, return_value="tok"):
            await service.processar_consulta(
                "consulta-001", db, FakeStorageBackend(), process_one=processed,
            )
        assert processed.count == 1
        # The orphan tipo is skipped, not crashed on — and the real one ran.
        assert processed.resultado_ids == ["r-ok"]

    @pytest.mark.asyncio
    async def test_consulta_inexistente_nao_estoura(self):
        db = _db(certidao_consultas=[], certidao_resultados=[])
        await service.processar_consulta("nao-existe", db, FakeStorageBackend())


# ---------------------------------------------------------------------------
# TJSP cooldown
# ---------------------------------------------------------------------------


class TestTjspCooldown:
    def test_sem_requests_anteriores_retorna_none(self):
        db = _db(certidao_resultados=[])
        assert service._get_tjsp_last_request_at(ORG, db) is None

    def test_le_o_api_requested_at_mais_recente(self):
        ts = "2026-03-05T10:00:00+00:00"
        db = _db(certidao_resultados=[
            _resultado(id="r1", tipo=TJSP_TIPO, api_requested_at=ts),
        ])
        assert service._get_tjsp_last_request_at(ORG, db) == datetime.fromisoformat(ts)

    def test_timestamp_ilegivel_e_pulado_e_nao_estoura(self):
        db = _db(certidao_resultados=[
            _resultado(id="r1", tipo=TJSP_TIPO, api_requested_at="lixo",
                       created_at="2026-03-05T12:00:00+00:00"),
            _resultado(id="r2", tipo=TJSP_TIPO,
                       api_requested_at="2026-03-05T10:00:00+00:00",
                       created_at="2026-03-05T09:00:00+00:00"),
        ])
        assert service._get_tjsp_last_request_at(ORG, db) is not None

    def test_sobrevive_ao_reset_de_status_no_reprocessamento(self):
        """🔴 The whole reason this column exists. A resultado reset from
        `erro` to `na_fila` still consumed TJSP's 30-minute window."""
        ts = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        db = _db(certidao_resultados=[
            _resultado(id="r1", tipo=TJSP_TIPO, status="na_fila",
                       api_requested_at=ts),
        ])
        remaining = service._get_tjsp_remaining_cooldown(ORG, db)
        assert remaining > 0

    def test_cooldown_expirado_retorna_zero(self):
        ts = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        db = _db(certidao_resultados=[
            _resultado(id="r1", tipo=TJSP_TIPO, api_requested_at=ts),
        ])
        assert service._get_tjsp_remaining_cooldown(ORG, db) == 0.0

    def test_cooldown_de_outra_org_nao_conta(self):
        ts = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        db = _db(certidao_resultados=[
            _resultado(id="r1", tipo=TJSP_TIPO, org_id=OTHER_ORG,
                       api_requested_at=ts),
        ])
        assert service._get_tjsp_last_request_at(ORG, db) is None

    def test_status_para_o_frontend_sem_historico(self):
        assert service.tjsp_cooldown_status(ORG, _db(certidao_resultados=[])) == {
            "ativo": False
        }

    def test_status_para_o_frontend_em_cooldown(self):
        ts = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        db = _db(certidao_resultados=[
            _resultado(id="r1", tipo=TJSP_TIPO, api_requested_at=ts),
        ])
        out = service.tjsp_cooldown_status(ORG, db)
        assert out["ativo"] is True
        assert 0 < out["segundos_restantes"] <= TJSP_COOLDOWN_SECONDS


# ---------------------------------------------------------------------------
# TJSP scheduler
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_tjsp_tasks():
    service._tjsp_scheduled_tasks.clear()
    yield
    service._tjsp_scheduled_tasks.clear()


class TestScheduleTjspForOrg:
    @pytest.mark.asyncio
    async def test_sem_itens_na_fila_nao_agenda(self):
        db = _db(certidao_resultados=[])
        service.schedule_tjsp_for_org(ORG, db, FakeStorageBackend())
        assert ORG not in service._tjsp_scheduled_tasks

    @pytest.mark.asyncio
    async def test_cria_task_para_item_na_fila(self):
        db = _db(certidao_resultados=[
            _resultado(id="r-tjsp", tipo=TJSP_TIPO, status="na_fila"),
        ])
        delayed = _Recorder()
        service.schedule_tjsp_for_org(ORG, db, FakeStorageBackend(), delayed=delayed)
        task = service._tjsp_scheduled_tasks.get(ORG)
        assert task is not None
        await asyncio.sleep(0)
        # It scheduled the QUEUED item, with the cooldown delay it computed.
        assert delayed.count == 1
        assert delayed.calls[0][1]["id"] == "r-tjsp"
        task.cancel()

    @pytest.mark.asyncio
    async def test_idempotente_enquanto_a_task_esta_em_voo(self):
        db = _db(certidao_resultados=[
            _resultado(id="r-tjsp", tipo=TJSP_TIPO, status="na_fila"),
        ])

        async def _never():
            await asyncio.sleep(3600)

        in_flight = asyncio.get_running_loop().create_task(_never())
        service._tjsp_scheduled_tasks[ORG] = in_flight
        delayed = _Recorder()
        service.schedule_tjsp_for_org(ORG, db, FakeStorageBackend(), delayed=delayed)
        assert service._tjsp_scheduled_tasks[ORG] is in_flight
        assert delayed.count == 0, "a second task was scheduled for the same org"
        in_flight.cancel()

    @pytest.mark.asyncio
    async def test_agenda_uma_task_por_org(self):
        db = _db(certidao_resultados=[
            _resultado(id="a", tipo=TJSP_TIPO, status="na_fila"),
            _resultado(id="b", tipo=TJSP_TIPO, status="na_fila",
                       org_id=OTHER_ORG, consulta_id="consulta-002"),
        ])
        scheduled: list[str] = []
        service.schedule_all_pending_tjsp(
            db, FakeStorageBackend(),
            schedule_one=lambda oid, *_a, **_k: scheduled.append(oid),
        )
        assert set(scheduled) == {ORG, OTHER_ORG}

    @pytest.mark.asyncio
    async def test_sem_fila_nenhuma_task(self):
        scheduled: list[str] = []
        service.schedule_all_pending_tjsp(
            _db(certidao_resultados=[]), FakeStorageBackend(),
            schedule_one=lambda oid, *_a, **_k: scheduled.append(oid),
        )
        assert scheduled == []
        assert service._tjsp_scheduled_tasks == {}


class TestDelayedTjspProcess:
    @pytest.mark.asyncio
    async def test_item_que_saiu_da_fila_e_ignorado(self):
        db = _db(certidao_resultados=[
            _resultado(id="r-tjsp", tipo=TJSP_TIPO, status="sucesso"),
        ])
        # `reschedule` is SYNC (`schedule_tjsp_for_org` is a plain function);
        # handing it an async recorder produced a never-awaited-coroutine
        # warning rather than a failure — a quiet way to test the wrong shape.
        proc, resched = _Recorder(), _SyncRecorder()
        await service._delayed_tjsp_process(
            0, {"id": "r-tjsp", "consulta_id": "consulta-001", "org_id": ORG},
            ORG, db, FakeStorageBackend(),
            process_item=proc, reschedule=resched,
        )
        assert proc.count == 0
        # It DOES still chain: the item left the queue, it was not a failure.
        assert resched.count == 1

    @pytest.mark.asyncio
    async def test_item_na_fila_e_processado_e_encadeia_o_proximo(self):
        db = _db(certidao_resultados=[
            _resultado(id="r-tjsp", tipo=TJSP_TIPO, status="na_fila"),
        ])
        proc, resched = _Recorder(), _SyncRecorder()
        await service._delayed_tjsp_process(
            0, {"id": "r-tjsp", "consulta_id": "consulta-001", "org_id": ORG},
            ORG, db, FakeStorageBackend(),
            process_item=proc, reschedule=resched,
        )
        assert proc.count == 1
        assert resched.count == 1

    @pytest.mark.asyncio
    async def test_falha_marca_erro_e_ainda_encadeia(self):
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[
                _resultado(id="r-tjsp", tipo=TJSP_TIPO, status="na_fila"),
            ],
        )
        async def _boom(*_a, **_k):
            raise RuntimeError("boom")

        resched = _SyncRecorder()
        await service._delayed_tjsp_process(
            0, {"id": "r-tjsp", "consulta_id": "consulta-001", "org_id": ORG},
            ORG, db, FakeStorageBackend(),
            process_item=_boom, reschedule=resched,
        )
        row = db.table("certidao_resultados").select("*").eq(
            "id", "r-tjsp"
        ).execute().data[0]
        assert row["status"] == "erro"
        assert "boom" in row["erro_mensagem"]
        assert resched.count == 1

    @pytest.mark.asyncio
    async def test_cancelamento_nao_reagenda(self):
        """A cancelled task means the process is going away. Rescheduling here
        would race the new process's own recovery."""
        db = _db(certidao_resultados=[
            _resultado(id="r-tjsp", tipo=TJSP_TIPO, status="na_fila"),
        ])
        resched = _SyncRecorder()
        # `asyncio.sleep` is stdlib — an EXTERNAL boundary, the one kind of
        # patch the rule allows (seam 3).
        with patch("asyncio.sleep", new=AsyncMock(side_effect=asyncio.CancelledError)):
            with pytest.raises(asyncio.CancelledError):
                await service._delayed_tjsp_process(
                    10, {"id": "r-tjsp", "consulta_id": "consulta-001", "org_id": ORG},
                    ORG, db, FakeStorageBackend(), reschedule=resched,
                )
        assert resched.count == 0


class TestProcessSingleTjspItem:
    @pytest.mark.asyncio
    async def test_consulta_ausente_marca_erro(self):
        db = _db(certidao_consultas=[], certidao_resultados=[
            _resultado(id="r-tjsp", tipo=TJSP_TIPO, status="na_fila"),
        ])
        await service._process_single_tjsp_item(
            {"id": "r-tjsp", "consulta_id": "sumiu", "org_id": ORG},
            db, FakeStorageBackend(),
        )
        row = db.table("certidao_resultados").select("*").eq(
            "id", "r-tjsp"
        ).execute().data[0]
        assert row["status"] == "erro"
        assert row["erro_mensagem"] == "Consulta não encontrada"

    @pytest.mark.asyncio
    async def test_sem_token_marca_erro(self):
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[
                _resultado(id="r-tjsp", tipo=TJSP_TIPO, status="na_fila"),
            ],
        )
        with patch(_CRED, return_value=None):
            await service._process_single_tjsp_item(
                {"id": "r-tjsp", "consulta_id": "consulta-001", "org_id": ORG},
                db, FakeStorageBackend(),
            )
        row = db.table("certidao_resultados").select("*").eq(
            "id", "r-tjsp"
        ).execute().data[0]
        assert row["status"] == "erro"


# ---------------------------------------------------------------------------
# Recovery
# ---------------------------------------------------------------------------


class TestRecoverStuckProcessando:
    def test_sem_itens_e_no_op(self):
        db = _db(certidao_resultados=[])
        service.recover_stuck_processando(db)

    def test_nao_tjsp_volta_para_pendente(self):
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[_resultado(id="r1", status="processando")],
        )
        service.recover_stuck_processando(db)
        assert db.table("certidao_resultados").select("*").eq(
            "id", "r1"
        ).execute().data[0]["status"] == "pendente"

    def test_tjsp_volta_para_na_fila(self):
        """Not `pendente`: that would make the next run fire immediately, and a
        premature TJSP request RESETS their counter."""
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[
                _resultado(id="r1", tipo=TJSP_TIPO, status="processando"),
            ],
        )
        service.recover_stuck_processando(db)
        assert db.table("certidao_resultados").select("*").eq(
            "id", "r1"
        ).execute().data[0]["status"] == "na_fila"

    def test_mistura_de_tipos_e_recuperada_em_dois_lotes(self):
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[
                _resultado(id="r1", status="processando"),
                _resultado(id="r2", tipo=TJSP_TIPO, status="processando", ordem=7),
            ],
        )
        service.recover_stuck_processando(db)
        rows = {
            r["id"]: r["status"]
            for r in db.table("certidao_resultados").select("*").execute().data
        }
        assert rows == {"r1": "pendente", "r2": "na_fila"}


class TestRecoverStaleProcessando:
    def test_item_recente_nao_e_tocado(self):
        """The 15-minute floor is what makes this safe to run at any moment —
        the slowest legitimate run is ~12 minutes."""
        recent = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
        db = _db(certidao_resultados=[
            _resultado(id="r1", status="processando", api_requested_at=recent),
        ])
        assert service.recover_stale_processando(db) == 0
        assert db.table("certidao_resultados").select("*").eq(
            "id", "r1"
        ).execute().data[0]["status"] == "processando"

    def test_item_antigo_vira_erro_com_mensagem_acionavel(self):
        old = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[
                _resultado(id="r1", status="processando", api_requested_at=old),
            ],
        )
        assert service.recover_stale_processando(db) == 1
        row = db.table("certidao_resultados").select("*").eq(
            "id", "r1"
        ).execute().data[0]
        assert row["status"] == "erro"
        assert "reprocessar" in row["erro_mensagem"]

    def test_sem_api_requested_at_nao_e_considerado_stale(self):
        """Those are waiting to START, not stuck mid-call. Resetting them here
        would fight `recover_stuck_processando` over the same rows."""
        db = _db(certidao_resultados=[
            _resultado(id="r1", status="processando", api_requested_at=None),
        ])
        assert service.recover_stale_processando(db) == 0


class TestRecoverStaleProcessandoRetryManual:
    """D3 (KB roadmap `sw-extraction-contract-gate-2026-09.md`): a stale
    MANUAL upload — a file already in storage, only its extraction leg
    stalled — gets retried instead of closed out, up to
    `MAX_ESTRUTURA_TENTATIVAS`. `storage=None` (every test above) is the
    pre-D3 behaviour, unchanged."""

    def _stale_manual_row(self, **overrides) -> dict:
        old = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        row = dict(
            id="r1", status="processando", api_requested_at=old,
            arquivo_url=f"{ORG}/certidoes/consulta-001/serasa.pdf",
            estrutura_tentativas=1,
        )
        row.update(overrides)
        return _resultado(**row)

    def test_com_arquivo_e_retentativas_disponiveis_e_retomado_nao_fechado(self):
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[self._stale_manual_row()],
        )
        scheduled: list[str] = []

        def _fake_schedule(coro, **kwargs):
            coro.close()  # never actually run — this test is not async
            scheduled.append(kwargs.get("name"))

        recovered = service.recover_stale_processando(
            db, FakeStorageBackend(), schedule=_fake_schedule,
        )
        assert recovered == 1
        assert scheduled == ["certidao_extracao_manual_retry_r1"]
        row = db.table("certidao_resultados").select("*").eq(
            "id", "r1"
        ).execute().data[0]
        # Untouched by the retry branch itself — the (never-run) retry
        # coroutine is what would eventually update it.
        assert row["status"] == "processando"

    def test_esgotado_fecha_como_erro_igual_ao_fluxo_automatico(self):
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[self._stale_manual_row(
                estrutura_tentativas=service.MAX_ESTRUTURA_TENTATIVAS,
            )],
        )
        recovered = service.recover_stale_processando(db, FakeStorageBackend())
        assert recovered == 1
        row = db.table("certidao_resultados").select("*").eq(
            "id", "r1"
        ).execute().data[0]
        assert row["status"] == "erro"

    def test_fluxo_automatico_sem_arquivo_continua_indo_direto_para_erro(self):
        """No `arquivo_url` (the automated flow never writes one before
        `sucesso`) — passing `storage` changes nothing for it."""
        old = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[
                _resultado(id="r1", status="processando", api_requested_at=old),
            ],
        )
        recovered = service.recover_stale_processando(db, FakeStorageBackend())
        assert recovered == 1
        row = db.table("certidao_resultados").select("*").eq(
            "id", "r1"
        ).execute().data[0]
        assert row["status"] == "erro"


class TestRetomarExtracaoManual:
    @pytest.mark.asyncio
    async def test_le_do_storage_e_reexecuta_a_extracao(self):
        storage = FakeStorageBackend()
        key = f"{ORG}/certidoes/consulta-001/serasa.pdf"
        await storage.put(
            bucket=service.BUCKET, key=key, data=b"%PDF-1.4",
            content_type="application/pdf",
        )
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[_resultado(
                id="r1", tipo="serasa", nome_display="Serasa",
                status="processando", arquivo_url=key, estrutura_tentativas=1,
            )],
        )
        async with httpx.AsyncClient() as http_client:
            await service._retomar_extracao_manual(
                db=db, storage=storage, http_client=http_client,
                resultado_id="r1", consulta_id="consulta-001", org_id=ORG,
                nome_display="Serasa", arquivo_url=key, tentativa=2,
            )
        row = db.table("certidao_resultados").select("*").eq(
            "id", "r1"
        ).execute().data[0]
        # `b"%PDF-1.4"` is not a real, openable PDF — deterministically
        # `no_pages`, no credential/network call needed. The point is that
        # the row MOVED (the attempt was recorded), not that this particular
        # bare PDF ever succeeds.
        assert row["estrutura_tentativas"] == 2
        assert row["estrutura_erro"]
        assert row["status"] == "processando"

    @pytest.mark.asyncio
    async def test_arquivo_ausente_no_storage_nao_levanta(self):
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[_resultado(id="r1", status="processando")],
        )
        async with httpx.AsyncClient() as http_client:
            await service._retomar_extracao_manual(
                db=db, storage=FakeStorageBackend(), http_client=http_client,
                resultado_id="r1", consulta_id="consulta-001", org_id=ORG,
                nome_display="Serasa", arquivo_url=f"{ORG}/certidoes/x/sumiu.pdf",
                tentativa=2,
            )
        # Never raised, and never touched the row it could not read bytes for.
        row = db.table("certidao_resultados").select("*").eq(
            "id", "r1"
        ).execute().data[0]
        assert row["status"] == "processando"
        assert row["estrutura_tentativas"] == 0


# ---------------------------------------------------------------------------
# cancelar_processamento
# ---------------------------------------------------------------------------


class TestCancelarProcessamento:
    def test_sem_itens_em_andamento_retorna_zero(self):
        db = _db(certidao_resultados=[_resultado(id="r1", status="sucesso")])
        assert service.cancelar_processamento("consulta-001", ORG, db) == {
            "cancelados": 0
        }

    def test_cancela_pendente_processando_e_na_fila(self):
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[
                _resultado(id="r1", status="pendente"),
                _resultado(id="r2", status="processando", ordem=2),
                _resultado(id="r3", status="na_fila", tipo=TJSP_TIPO, ordem=7),
                _resultado(id="r4", status="sucesso", ordem=4),
            ],
        )
        assert service.cancelar_processamento("consulta-001", ORG, db) == {
            "cancelados": 3
        }
        rows = {
            r["id"]: r["status"]
            for r in db.table("certidao_resultados").select("*").execute().data
        }
        assert rows["r4"] == "sucesso"
        assert rows["r1"] == rows["r2"] == rows["r3"] == "erro"

    @pytest.mark.asyncio
    async def test_cancela_a_task_tjsp_agendada(self):
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[
                _resultado(id="r3", status="na_fila", tipo=TJSP_TIPO, ordem=7),
            ],
        )

        async def _never():
            await asyncio.sleep(3600)

        task = asyncio.get_running_loop().create_task(_never())
        service._tjsp_scheduled_tasks[ORG] = task
        service.cancelar_processamento("consulta-001", ORG, db)
        await asyncio.sleep(0)
        assert task.cancelled() or task.cancelling()
        assert ORG not in service._tjsp_scheduled_tasks

    def test_nao_cancela_resultados_de_outra_org(self):
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[
                _resultado(id="mine", status="pendente"),
                _resultado(id="theirs", status="pendente", org_id=OTHER_ORG),
            ],
        )
        assert service.cancelar_processamento("consulta-001", ORG, db) == {
            "cancelados": 1
        }


# ---------------------------------------------------------------------------
# status_counts_por_consulta — the row-cap fix
# ---------------------------------------------------------------------------


class TestStatusCountsPorConsulta:
    def test_conta_sucessos_e_erros_por_consulta(self):
        db = _db(certidao_resultados=[
            _resultado(id="a1", consulta_id="c1", status="sucesso"),
            _resultado(id="a2", consulta_id="c1", status="sucesso", ordem=2),
            _resultado(id="a3", consulta_id="c1", status="erro", ordem=3),
            _resultado(id="b1", consulta_id="c2", status="erro"),
            _resultado(id="p1", consulta_id="c1", status="pendente", ordem=4),
        ])
        sucessos, erros = service.status_counts_por_consulta(["c1", "c2"], ORG, db)
        assert sucessos == {"c1": 2}
        assert erros == {"c1": 1, "c2": 1}

    def test_ignora_resultados_de_outra_org(self):
        db = _db(certidao_resultados=[
            _resultado(id="mine", consulta_id="c1", status="sucesso"),
            _resultado(id="theirs", consulta_id="c1", status="sucesso",
                       org_id=OTHER_ORG, ordem=2),
        ])
        sucessos, _ = service.status_counts_por_consulta(["c1"], ORG, db)
        assert sucessos == {"c1": 1}

    def test_lista_vazia_nao_consulta_o_banco(self):
        db = _db(certidao_resultados=[_resultado(id="a1", status="sucesso")])
        assert service.status_counts_por_consulta([], ORG, db) == ({}, {})

    def test_pagina_alem_do_teto_de_1000_linhas_do_postgrest(self):
        """🔴 REGRESSION. A full page is 200 consultas, each fanning out to one
        resultado per registry type — 2 000 rows against PostgREST's 1 000-row
        cap, which it applies SILENTLY and reports as success.

        The un-paged version of this read did not fail; it returned
        `concluidas: 0` for the back half of the page, indistinguishable from a
        consulta that genuinely had not started. `MockSupabaseClient` enforces
        the same cap, which is what makes this assertable at all.
        """
        rows = []
        for c in range(200):
            for i in range(10):
                rows.append(_resultado(
                    id=f"r{c}-{i}", consulta_id=f"c{c}", status="sucesso", ordem=i + 1,
                ))
        assert len(rows) == 2000
        db = _db(certidao_resultados=rows)

        sucessos, _ = service.status_counts_por_consulta(
            [f"c{c}" for c in range(200)], ORG, db
        )
        # Every consulta must be counted, and counted fully — not just the
        # first 100 that fit under the cap.
        assert len(sucessos) == 200
        assert set(sucessos.values()) == {10}


# ---------------------------------------------------------------------------
# queued_tjsp_for_org
# ---------------------------------------------------------------------------


class TestQueuedTjspForOrg:
    def test_traz_so_na_fila_do_tipo_tjsp_e_da_propria_org(self):
        """The queue is per-ORG because the rate limit is: one InfoSimples
        email per org. Another org's queued item is not in this line.

        ⚠️ Deliberately asserts the SET, not the order. `MockSelectBuilder.order`
        validates the column name and returns `self` — it does not sort — so an
        `== ["a", "b"]` assertion here would be testing the fixture's insertion
        order dressed up as an ORDER BY. The real ordering is `created_at` and
        is what `idx_sw_certidao_resultados_fila_tjsp` (migration 091) indexes;
        proving it needs a live Postgres, not this double.
        """
        db = _db(certidao_resultados=[
            _resultado(id="b", tipo=TJSP_TIPO, status="na_fila",
                       created_at="2026-03-05T11:00:00+00:00"),
            _resultado(id="a", tipo=TJSP_TIPO, status="na_fila",
                       created_at="2026-03-05T10:00:00+00:00"),
            _resultado(id="outro", tipo=TJSP_TIPO, status="na_fila",
                       org_id=OTHER_ORG),
            _resultado(id="pronto", tipo=TJSP_TIPO, status="sucesso"),
            _resultado(id="nao_tjsp", status="na_fila"),
        ])
        assert {r["id"] for r in service.queued_tjsp_for_org(ORG, db)} == {"a", "b"}


# ---------------------------------------------------------------------------
# The stranded-work sweep (scheduler seam)
# ---------------------------------------------------------------------------


class TestScheduler:
    """The stranded-work sweep.

    🔴 THESE ASSERT BEHAVIOUR, NOT CALL-ROUTING. They used to patch
    `service.recover_stale_processando` / `recover_stuck_processando` and assert
    which one the sweep called — which is both a self-monkeypatch and a weaker
    claim: it proves a name was invoked, not that a live request survived. The
    `clients=` DI seam lets the REAL recovery run against a mock DB, so each
    test can assert the thing that actually matters — which rows moved.
    """

    def test_configure_registra_o_job_no_scheduler_do_seed(self):
        from noctusai_lib.api import scheduler as seed_scheduler

        from app.modules.certidoes import scheduler

        scheduler.configure()
        assert any(
            job.id == scheduler.JOB_ID for job in seed_scheduler.scheduler.get_jobs()
        ) or scheduler.JOB_ID in {
            j.id for j in getattr(seed_scheduler.scheduler, "_pending_jobs", [])
        }

    @pytest.mark.asyncio
    async def test_sweep_nunca_levanta(self):
        """🔴 A scheduler job that throws is, in some runtimes, a job that stops
        being scheduled — which removes the safety net this IS."""
        from app.modules.certidoes import scheduler

        def _explode():
            raise RuntimeError("db gone")

        await scheduler.sweep_stranded(clients=_explode)

    @pytest.mark.asyncio
    async def test_sweep_sem_admin_client_e_no_op(self):
        """`_clients` answers `(None, None)` when there is no admin client; the
        sweep must return without touching anything."""
        from app.modules.certidoes import scheduler

        db = _db(certidao_resultados=[
            _resultado(id="r1", status="processando",
                       api_requested_at="2020-01-01T00:00:00+00:00"),
        ])
        await scheduler.sweep_stranded(clients=lambda: (None, None))
        # Ancient row, and still untouched — the sweep genuinely did nothing.
        assert db.table("certidao_resultados").select("*").eq(
            "id", "r1"
        ).execute().data[0]["status"] == "processando"

    @pytest.mark.asyncio
    async def test_sweep_nao_derruba_requisicao_viva(self):
        """🔴 THE reason the recurring job uses the STALE variant.

        A row that started 2 minutes ago belongs to a request that is very
        likely still in flight (the slowest legitimate run is ~12 min). The
        unconditional `recover_stuck_processando` would reset it out from under
        the live task; the stale variant, with its 15-minute floor, must not.
        """
        from app.modules.certidoes import scheduler

        fresh = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[
                _resultado(id="viva", status="processando", api_requested_at=fresh),
            ],
        )
        await scheduler.sweep_stranded(
            clients=lambda: (db, FakeStorageBackend())
        )
        assert db.table("certidao_resultados").select("*").eq(
            "id", "viva"
        ).execute().data[0]["status"] == "processando"

    @pytest.mark.asyncio
    async def test_sweep_recupera_o_que_encalhou_de_verdade(self):
        """The other half: a genuinely abandoned row DOES get recovered, so the
        test above cannot pass by the sweep simply doing nothing."""
        from app.modules.certidoes import scheduler

        old = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[
                _resultado(id="encalhado", status="processando",
                           api_requested_at=old),
            ],
        )
        await scheduler.sweep_stranded(
            clients=lambda: (db, FakeStorageBackend())
        )
        row = db.table("certidao_resultados").select("*").eq(
            "id", "encalhado"
        ).execute().data[0]
        assert row["status"] == "erro"
        assert "reprocessar" in row["erro_mensagem"]

    def test_startup_recovery_reseta_incondicionalmente(self):
        """At process start nothing of OURS is running, so the unconditional
        reset is correct there — and it is what makes a row abandoned by the
        PREVIOUS process recoverable immediately rather than in 15 minutes."""
        from app.modules.certidoes import scheduler

        fresh = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[
                _resultado(id="orfao", status="processando", api_requested_at=fresh),
                _resultado(id="orfao-tjsp", tipo=TJSP_TIPO, ordem=7,
                           status="processando", api_requested_at=fresh),
            ],
        )
        scheduler.run_startup_recovery(clients=lambda: (db, FakeStorageBackend()))
        rows = {
            r["id"]: r["status"]
            for r in db.table("certidao_resultados").select("*").execute().data
        }
        # Same 2-minute-old rows the sweep above deliberately leaves alone.
        assert rows == {"orfao": "pendente", "orfao-tjsp": "na_fila"}

    def test_startup_recovery_nao_e_fatal(self):
        """A lifespan hook is a SIDE EFFECT, never a precondition for serving.
        → KB § PATTERNS/backend/startup-hook-must-not-be-fatal.md"""
        from app.modules.certidoes import scheduler

        def _explode():
            raise RuntimeError("x")

        scheduler.run_startup_recovery(clients=_explode)

    def test_configure_registra_o_job_de_purge_no_scheduler_do_seed(self):
        from noctusai_lib.api import scheduler as seed_scheduler

        from app.modules.certidoes import scheduler

        scheduler.configure()
        assert any(
            job.id == scheduler.PURGE_JOB_ID
            for job in seed_scheduler.scheduler.get_jobs()
        ) or scheduler.PURGE_JOB_ID in {
            j.id for j in getattr(seed_scheduler.scheduler, "_pending_jobs", [])
        }

    @pytest.mark.asyncio
    async def test_purge_job_nunca_levanta(self):
        from app.modules.certidoes import scheduler

        def _explode():
            raise RuntimeError("db gone")

        await scheduler.purge_excluidas(clients=_explode)

    @pytest.mark.asyncio
    async def test_purge_job_sem_admin_client_e_no_op(self):
        from app.modules.certidoes import scheduler

        db = _db(certidao_consultas=[_consulta_row(
            excluida_em="2020-01-01T00:00:00+00:00", excluida_por="user-1",
        )])
        await scheduler.purge_excluidas(clients=lambda: (None, None))
        # Old excluded row, still untouched — the job genuinely did nothing.
        assert len(db.table("certidao_consultas").select("*").execute().data) == 1

    @pytest.mark.asyncio
    async def test_purge_job_purga_o_que_passou_da_janela(self):
        from app.modules.certidoes import scheduler

        antiga = (datetime.now(timezone.utc) - timedelta(days=45)).isoformat()
        db = _db(certidao_consultas=[_consulta_row(
            excluida_em=antiga, excluida_por="user-1",
        )])
        await scheduler.purge_excluidas(
            clients=lambda: (db, FakeStorageBackend())
        )
        assert db.table("certidao_consultas").select("*").execute().data == []


# ---------------------------------------------------------------------------
# Registry — structured-field vocabulary + manual-only types (migration 107)
# ---------------------------------------------------------------------------


class TestRegistryEstruturado:
    def test_todos_os_dez_tipos_tem_parse_fn(self):
        for config in CERTIDOES_CONFIG:
            assert config["parse_fn"] in PARSE_BUILDERS, config["tipo"]

    def test_resultado_values_bate_com_o_check_das_migracoes_107_e_116(self):
        assert RESULTADO_VALUES == {
            "negativa", "positiva", "positiva_com_efeito_de_negativa",
            "nao_emitida", "negativa_com_homonimos",
        }

    def test_manual_tipos_tem_tres_itens_sem_endpoint(self):
        assert len(MANUAL_TIPOS_CONFIG) == 3
        assert {c["tipo"] for c in MANUAL_TIPOS_CONFIG} == {
            "serasa", "tjsp_esaj", "tjsp_eproc",
        }
        for config in MANUAL_TIPOS_CONFIG:
            assert "endpoint" not in config
            assert "params_fn" not in config

    def test_manual_tipos_nao_aparecem_em_get_certidoes_tipos(self):
        """🔴 `criar_consulta`'s fan-out iterates `CERTIDOES_CONFIG` — the ten
        automated types stay pinned at ten, unaffected by this migration."""
        tipos = {c["tipo"] for c in get_certidoes_tipos()}
        assert tipos.isdisjoint({"serasa", "tjsp_esaj", "tjsp_eproc"})
        assert len(get_certidoes_tipos()) == 10

    def test_get_manual_tipos_retorna_tipo_nome_ordem(self):
        for item in get_manual_tipos():
            assert set(item) == {"tipo", "nome", "ordem"}
        assert [c["ordem"] for c in get_manual_tipos()] == [11, 12, 13]

    def test_manual_config_for_desconhecido_retorna_none(self):
        assert manual_config_for("nao_existe") is None
        assert manual_config_for("serasa")["nome"] == "Serasa"

    def test_config_for_nao_enxerga_tipos_manuais(self):
        """`config_for` answers "is there an API call to make" — a manual
        type correctly has none."""
        assert config_for("serasa") is None


# ---------------------------------------------------------------------------
# parse_resultado — structured fields straight off the API response
# ---------------------------------------------------------------------------


class TestParseResultado:
    def test_nada_consta_e_sempre_negativa(self):
        assert parse_resultado(CONFIG_FEDERAL, {"nada_consta": "Nada consta"}) == {
            "resultado": "negativa",
        }

    def test_sem_data_no_raw_response_nao_extrai_nada(self):
        assert parse_resultado(CONFIG_FEDERAL, {"raw_response": {}}) == {}
        assert parse_resultado(CONFIG_FEDERAL, {"raw_response": None}) == {}

    def test_le_numero_e_datas_do_data_zero(self):
        fetch_result = {
            "raw_response": {
                "data": [{
                    "numero_controle": "ABC.123",
                    "data_emissao": "10/03/2026",
                    "data_validade": "10/09/2026",
                }],
            },
        }
        campos = parse_resultado(CONFIG_FEDERAL, fetch_result)
        assert campos == {
            "numero": "ABC.123",
            "emitida_em": "2026-03-10",
            "validade_ate": "2026-09-10",
        }

    def test_nao_adivinha_resultado_a_partir_do_code_200(self):
        """🔴 A code=200 PDF can be negativa OR positiva — the parser has no
        verified field mapping to tell them apart, so it must not guess."""
        fetch_result = {
            "raw_response": {"data": [{"numero_controle": "X"}]},
        }
        assert "resultado" not in parse_resultado(CONFIG_FEDERAL, fetch_result)

    def test_tipo_sem_parse_fn_retorna_vazio(self):
        assert parse_resultado({"parse_fn": "nao_existe"}, {
            "raw_response": {"data": [{"numero": "1"}]},
        }) == {}

    def test_data_em_formato_invalido_e_ignorada_nao_derruba(self):
        fetch_result = {
            "raw_response": {"data": [{"data_emissao": "não é uma data"}]},
        }
        assert parse_resultado(CONFIG_FEDERAL, fetch_result) == {}


# ---------------------------------------------------------------------------
# CENPROT's date fallback (migration 116) — protocolo_consulta, not
# data_emissao/data_consulta, which this endpoint never carries.
# ---------------------------------------------------------------------------


CONFIG_CENPROT = config_for("cenprot")


class TestCenprotProtocoloDate:
    def test_seis_primeiros_digitos_viram_a_data(self):
        assert _cenprot_protocolo_date("26091412345678") == "2026-09-14"

    def test_protocolo_curto_demais_retorna_none(self):
        assert _cenprot_protocolo_date("2609") is None

    def test_protocolo_nao_numerico_retorna_none(self):
        assert _cenprot_protocolo_date("ab091412345678") is None

    def test_data_invalida_no_prefixo_retorna_none(self):
        assert _cenprot_protocolo_date("99991412345678") is None

    def test_none_e_nao_string_retornam_none(self):
        assert _cenprot_protocolo_date(None) is None
        assert _cenprot_protocolo_date(12345) is None


class TestParseResultadoCenprot:
    def test_deriva_emitida_em_do_protocolo_quando_sem_data(self):
        fetch_result = {
            "raw_response": {"data": [{"protocolo_consulta": "26091412345678"}]},
        }
        assert parse_resultado(CONFIG_CENPROT, fetch_result) == {
            "emitida_em": "2026-09-14",
        }

    def test_nao_sobrescreve_uma_data_emissao_real(self):
        """If a future CENPROT payload DOES carry `data_emissao`, the
        generic reader wins — the protocol-derived date is a fallback, not
        an override."""
        fetch_result = {
            "raw_response": {"data": [{
                "protocolo_consulta": "26091412345678",
                "data_emissao": "01/01/2026",
            }]},
        }
        assert parse_resultado(CONFIG_CENPROT, fetch_result) == {
            "emitida_em": "2026-01-01",
        }

    def test_sem_protocolo_nao_deriva_nada(self):
        fetch_result = {"raw_response": {"data": [{"quantidade_titulos": 0}]}}
        assert parse_resultado(CONFIG_CENPROT, fetch_result) == {}

    def test_nada_consta_nao_chama_o_parser_de_protocolo(self):
        """612 short-circuits to `{"resultado": "negativa"}` before any
        `parse_fn` runs — consistent with `_cenprot_protocolo_consulta`
        never finding a protocol on a 612 either."""
        assert parse_resultado(
            CONFIG_CENPROT, {"nada_consta": "Nada consta"}
        ) == {"resultado": "negativa"}


# ---------------------------------------------------------------------------
# _analyze_estrutura_with_ai — the structured AI fallback
# ---------------------------------------------------------------------------


class TestAnalyzeEstruturaWithAi:
    @pytest.mark.asyncio
    async def test_sem_chave_retorna_none_nao_marcador(self):
        """🔴 Unlike `_analyze_with_ai`'s PT-BR marker (meant to be READ in a
        text column), a failure here has no honest column to sit in — the
        caller's fields simply stay whatever they already were."""
        with patch(_CRED, return_value=None):
            out = await service._analyze_estrutura_with_ai(
                "texto", "CND Federal", ORG, resolve_provider=_provider("openai")
            )
        assert out is None

    @pytest.mark.asyncio
    async def test_provider_ilegivel_nao_derruba_o_job(self):
        out = await service._analyze_estrutura_with_ai(
            "texto", "CND Federal", ORG,
            resolve_provider=_provider_raising(RuntimeError("supabase_url is required")),
        )
        assert out is None

    @pytest.mark.asyncio
    async def test_json_limpo_e_extraido(self):
        with patch(_CRED, return_value="sk-x"), patch(
            "app.modules.certidoes.service.chat_completion",
            new=AsyncMock(return_value=(
                '{"numero": "123", "emitida_em": "2026-01-10", '
                '"validade_ate": "2026-07-10", "resultado": "negativa"}'
            )),
        ):
            out = await service._analyze_estrutura_with_ai(
                "texto", "CND Federal", ORG, resolve_provider=_provider("openai")
            )
        assert out == {
            "numero": "123",
            "emitida_em": "2026-01-10",
            "validade_ate": "2026-07-10",
            "resultado": "negativa",
        }

    @pytest.mark.asyncio
    async def test_json_cercado_por_markdown_fence_e_aceito(self):
        with patch(_CRED, return_value="sk-x"), patch(
            "app.modules.certidoes.service.chat_completion",
            new=AsyncMock(return_value='```json\n{"resultado": "positiva"}\n```'),
        ):
            out = await service._analyze_estrutura_with_ai(
                "texto", "CND Federal", ORG, resolve_provider=_provider("openai")
            )
        assert out == {"resultado": "positiva"}

    @pytest.mark.asyncio
    async def test_negativa_com_homonimos_e_aceita_migracao_116(self):
        """The fifth `resultado` value (migration 116) must round-trip
        through the SAME vocabulary check as the original four — it is not
        special-cased, just added to `RESULTADO_VALUES`."""
        with patch(_CRED, return_value="sk-x"), patch(
            "app.modules.certidoes.service.chat_completion",
            new=AsyncMock(return_value='{"resultado": "negativa_com_homonimos"}'),
        ):
            out = await service._analyze_estrutura_with_ai(
                "texto", "CND Federal", ORG, resolve_provider=_provider("openai")
            )
        assert out == {"resultado": "negativa_com_homonimos"}

    @pytest.mark.asyncio
    async def test_prompt_pede_homonimos_e_data_da_consulta_como_fallback(self):
        """Migration 116: the shared extraction prompt (used by BOTH the
        automated flow and every manual upload, including Serasa) must ask
        the model to (a) recognize a homônimos caveat and (b) fall back to
        the consulta date when a document has no explicit emission date."""
        mock_chat = AsyncMock(return_value='{"resultado": "negativa"}')
        with patch(_CRED, return_value="sk-x"), patch(
            "app.modules.certidoes.service.chat_completion", new=mock_chat,
        ):
            await service._analyze_estrutura_with_ai(
                "texto", "CND Federal", ORG, resolve_provider=_provider("openai")
            )
        system_msg = mock_chat.call_args.kwargs["messages"][0]["content"]
        assert "negativa_com_homonimos" in system_msg
        assert "homônimos" in system_msg
        assert "data da consulta" in system_msg

    @pytest.mark.asyncio
    async def test_resultado_fora_do_vocabulario_e_descartado(self):
        """A model that ignores the instruction and answers a free-text
        verdict must not write outside the CHECK-constrained vocabulary."""
        with patch(_CRED, return_value="sk-x"), patch(
            "app.modules.certidoes.service.chat_completion",
            new=AsyncMock(return_value='{"resultado": "provavelmente ok"}'),
        ):
            out = await service._analyze_estrutura_with_ai(
                "texto", "CND Federal", ORG, resolve_provider=_provider("openai")
            )
        assert out is None

    @pytest.mark.asyncio
    async def test_json_invalido_retorna_none(self):
        with patch(_CRED, return_value="sk-x"), patch(
            "app.modules.certidoes.service.chat_completion",
            new=AsyncMock(return_value="isto não é json"),
        ):
            out = await service._analyze_estrutura_with_ai(
                "texto", "CND Federal", ORG, resolve_provider=_provider("openai")
            )
        assert out is None

    @pytest.mark.asyncio
    async def test_data_fora_do_formato_iso_e_descartada(self):
        with patch(_CRED, return_value="sk-x"), patch(
            "app.modules.certidoes.service.chat_completion",
            new=AsyncMock(return_value=(
                '{"emitida_em": "10 de março", "resultado": "negativa"}'
            )),
        ):
            out = await service._analyze_estrutura_with_ai(
                "texto", "CND Federal", ORG, resolve_provider=_provider("openai")
            )
        assert out == {"resultado": "negativa"}

    @pytest.mark.asyncio
    async def test_falha_do_provedor_retorna_none(self):
        with patch(_CRED, return_value="sk-x"), patch(
            "app.modules.certidoes.service.chat_completion",
            new=AsyncMock(side_effect=RuntimeError("429")),
        ):
            out = await service._analyze_estrutura_with_ai(
                "texto", "CND Federal", ORG, resolve_provider=_provider("openai")
            )
        assert out is None

    @pytest.mark.asyncio
    async def test_resposta_vazia_de_json_retorna_none(self):
        """Every field either absent or invalid → `_parse_json_resultado`
        collapses the dict to empty and this returns `None`, not `{}`."""
        with patch(_CRED, return_value="sk-x"), patch(
            "app.modules.certidoes.service.chat_completion",
            new=AsyncMock(return_value='{"numero": null, "resultado": null}'),
        ):
            out = await service._analyze_estrutura_with_ai(
                "texto", "CND Federal", ORG, resolve_provider=_provider("openai")
            )
        assert out is None


# ---------------------------------------------------------------------------
# _derive_estrutura — the orchestration: API first, AI fallback, human lock
# ---------------------------------------------------------------------------


class TestDerivaEstrutura:
    @pytest.mark.asyncio
    async def test_travado_nao_chama_nada(self):
        estrutura_ia = AsyncMock()
        patch_out = await service._derive_estrutura(
            config=CONFIG_FEDERAL,
            result={"raw_response": {"data": [{"numero_controle": "X"}]}},
            texto_para_ia="texto",
            nome_display="CND Federal",
            org_id=ORG,
            travado=True,
            analyze_estrutura=estrutura_ia,
        )
        assert patch_out == {}
        estrutura_ia.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_nada_consta_nao_precisa_de_ia(self):
        estrutura_ia = AsyncMock()
        patch_out = await service._derive_estrutura(
            config=CONFIG_FEDERAL,
            result={"nada_consta": "Nada consta"},
            texto_para_ia=None,
            nome_display="CND Federal",
            org_id=ORG,
            travado=False,
            analyze_estrutura=estrutura_ia,
        )
        assert patch_out == {"resultado": "negativa", "resultado_origem": "api"}
        estrutura_ia.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_api_ambigua_cai_para_ia(self):
        estrutura_ia = AsyncMock(return_value={"resultado": "positiva"})
        patch_out = await service._derive_estrutura(
            config=CONFIG_FEDERAL,
            result={"raw_response": {"data": [{"numero_controle": "X"}]}},
            texto_para_ia="texto",
            nome_display="CND Federal",
            org_id=ORG,
            travado=False,
            analyze_estrutura=estrutura_ia,
        )
        assert patch_out == {
            "numero": "X", "resultado": "positiva", "resultado_origem": "ia",
        }
        estrutura_ia.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_ia_nunca_sobrescreve_o_que_a_api_ja_disse(self):
        """`setdefault` — the AI leg only FILLS GAPS, never overwrites a field
        the API-response parse already produced."""
        estrutura_ia = AsyncMock(
            return_value={"numero": "IA-WRONG", "resultado": "positiva"}
        )
        patch_out = await service._derive_estrutura(
            config=CONFIG_FEDERAL,
            result={"raw_response": {"data": [{"numero_controle": "API-RIGHT"}]}},
            texto_para_ia="texto",
            nome_display="CND Federal",
            org_id=ORG,
            travado=False,
            analyze_estrutura=estrutura_ia,
        )
        assert patch_out["numero"] == "API-RIGHT"

    @pytest.mark.asyncio
    async def test_sem_texto_nem_config_e_sem_resultado_da_api_fica_vazio(self):
        estrutura_ia = AsyncMock()
        patch_out = await service._derive_estrutura(
            config=None, result=None, texto_para_ia=None,
            nome_display="CND Federal", org_id=ORG, travado=False,
            analyze_estrutura=estrutura_ia,
        )
        assert patch_out == {}
        estrutura_ia.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_ia_sem_resposta_nao_seta_origem(self):
        estrutura_ia = AsyncMock(return_value=None)
        patch_out = await service._derive_estrutura(
            config=CONFIG_FEDERAL,
            result={"raw_response": {"data": [{}]}},
            texto_para_ia="texto",
            nome_display="CND Federal",
            org_id=ORG,
            travado=False,
            analyze_estrutura=estrutura_ia,
        )
        assert patch_out == {}


# ---------------------------------------------------------------------------
# _process_single_certidao — structured fields wired end-to-end
# ---------------------------------------------------------------------------


class TestProcessSingleCertidaoEstruturado:
    @pytest.mark.asyncio
    async def test_nada_consta_grava_negativa_e_origem_api(self):
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[_resultado()],
        )
        http = _FakeHttp({"code": 612, "errors": ["Nada consta"]})
        await service._process_single_certidao(
            CONFIG_FEDERAL, _consulta_row(), "tok", db,
            "resultado-001", http, FakeStorageBackend(),
            analyze=_noop_analyze, extract_text=_noop_extract_text,
            core_db=MockSupabaseClient(schema="public"),
        )
        row = db.table("certidao_resultados").select("*").eq(
            "id", "resultado-001"
        ).execute().data[0]
        assert row["resultado"] == "negativa"
        assert row["resultado_origem"] == "api"

    @pytest.mark.asyncio
    async def test_resultado_ja_confirmado_manualmente_nao_e_sobrescrito(self):
        """🔴 The enforcement side of migration 107's header: a reprocess must
        never silently overwrite a human's confirmed value."""
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[_resultado(
                resultado="positiva", resultado_origem="manual",
                confirmado_por="user-1",
            )],
        )
        http = _FakeHttp({"code": 612, "errors": ["Nada consta"]})
        await service._process_single_certidao(
            CONFIG_FEDERAL, _consulta_row(), "tok", db,
            "resultado-001", http, FakeStorageBackend(),
            analyze=_noop_analyze, extract_text=_noop_extract_text,
            core_db=MockSupabaseClient(schema="public"),
        )
        row = db.table("certidao_resultados").select("*").eq(
            "id", "resultado-001"
        ).execute().data[0]
        # The API said "nada_consta" (negativa) but the human's "positiva"
        # (a real debt the certidão missed, corrected by hand) must stand.
        assert row["resultado"] == "positiva"
        assert row["resultado_origem"] == "manual"

    @pytest.mark.asyncio
    async def test_sucesso_com_pdf_deriva_campos_via_ia_quando_api_e_ambigua(self):
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[_resultado()],
        )
        http = _FakeHttp(_api_ok(), file_body=b"%PDF-1.4 real")
        estrutura_ia = AsyncMock(return_value={"resultado": "negativa"})
        await service._process_single_certidao(
            CONFIG_FEDERAL, _consulta_row(), "tok", db,
            "resultado-001", http, FakeStorageBackend(),

            analyze=_noop_analyze, extract_text=_noop_extract_text,
            analyze_estrutura=estrutura_ia,
            core_db=MockSupabaseClient(schema="public"),
        )
        row = db.table("certidao_resultados").select("*").eq(
            "id", "resultado-001"
        ).execute().data[0]
        assert row["resultado"] == "negativa"
        assert row["resultado_origem"] == "ia"
        estrutura_ia.assert_awaited_once()


# ---------------------------------------------------------------------------
# process_manual_upload — structured fields, AI-only on this path
# ---------------------------------------------------------------------------


class TestProcessManualUploadEstruturado:
    @pytest.mark.asyncio
    async def test_deriva_campos_via_ia_quando_nao_travado(self):
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[_resultado(tipo="serasa", nome_display="Serasa")],
        )
        estrutura_ia = AsyncMock(return_value={"resultado": "negativa"})
        update_data = await service.process_manual_extraction(
            pdf_bytes=b"%PDF-1.4",
            resultado_id="resultado-001",
            consulta_id="consulta-001",
            nome_display="Serasa",
            org_id=ORG,
            db=db,
            extract_text=AsyncMock(
                return_value=service.ExtractedPdfText(para_ia="texto extraído")
            ),
            analyze=AsyncMock(return_value="resumo"),
            analyze_estrutura=estrutura_ia,
        )
        assert update_data["resultado"] == "negativa"
        assert update_data["resultado_origem"] == "ia"
        assert update_data["status"] == "sucesso"
        estrutura_ia.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_travado_por_confirmado_por_nao_chama_ia(self):
        estrutura_ia = AsyncMock()
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[_resultado(
                tipo="serasa", resultado_origem="api", confirmado_por="user-1",
            )],
        )
        update_data = await service.process_manual_extraction(
            pdf_bytes=b"%PDF-1.4",
            resultado_id="resultado-001",
            consulta_id="consulta-001",
            nome_display="Serasa",
            org_id=ORG,
            db=db,
            resultado_origem_atual="api",
            confirmado_por_atual="user-1",
            extract_text=AsyncMock(
                return_value=service.ExtractedPdfText(para_ia="texto extraído")
            ),
            analyze=AsyncMock(return_value="resumo"),
            analyze_estrutura=estrutura_ia,
        )
        assert "resultado" not in update_data
        estrutura_ia.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_travado_por_origem_manual_nao_chama_ia(self):
        estrutura_ia = AsyncMock()
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[_resultado(
                tipo="tjsp_esaj", resultado_origem="manual",
            )],
        )
        await service.process_manual_extraction(
            pdf_bytes=b"%PDF-1.4",
            resultado_id="resultado-001",
            consulta_id="consulta-001",
            nome_display="TJSP e-SAJ",
            org_id=ORG,
            db=db,
            resultado_origem_atual="manual",
            extract_text=AsyncMock(
                return_value=service.ExtractedPdfText(para_ia="texto extraído")
            ),
            analyze=AsyncMock(return_value="resumo"),
            analyze_estrutura=estrutura_ia,
        )
        estrutura_ia.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_sem_texto_extraido_nao_chama_ia(self):
        estrutura_ia = AsyncMock()
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[_resultado(tipo="serasa")],
        )
        await service.process_manual_extraction(
            pdf_bytes=b"%PDF-1.4",
            resultado_id="resultado-001",
            consulta_id="consulta-001",
            nome_display="Serasa",
            org_id=ORG,
            db=db,
            extract_text=AsyncMock(return_value=service.ExtractedPdfText(para_ia=None)),
            analyze_estrutura=estrutura_ia,
        )
        estrutura_ia.assert_not_awaited()


class TestProcessManualExtractionEstruturaErro:
    """The scanned-manual-upload leg: bounded vision, surfaced failures, and
    the D3 retry cap. KB roadmap `sw-extraction-contract-gate-2026-09.md`."""

    @pytest.mark.asyncio
    async def test_falha_abaixo_do_limite_mantem_processando_e_agenda_retry(self):
        """A failed extraction below `MAX_ESTRUTURA_TENTATIVAS` does NOT flip
        `status` — `recover_stale_processando` is what retries it once the
        row goes stale, not this call itself."""
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[_resultado(tipo="serasa", status="processando")],
        )
        analyze = AsyncMock()
        analyze_estrutura = AsyncMock()
        update_data = await service.process_manual_extraction(
            pdf_bytes=b"%PDF-1.4",
            resultado_id="resultado-001",
            consulta_id="consulta-001",
            nome_display="Serasa",
            org_id=ORG,
            db=db,
            tentativa=1,
            extract_text=AsyncMock(
                return_value=service.ExtractedPdfText(
                    para_ia=None, erro="Cota do provedor de IA esgotada. ...",
                )
            ),
            analyze=analyze,
            analyze_estrutura=analyze_estrutura,
        )
        assert update_data["estrutura_tentativas"] == 1
        assert update_data["estrutura_erro"]
        assert "status" not in update_data
        analyze.assert_not_awaited()
        analyze_estrutura.assert_not_awaited()

        row = db.table("certidao_resultados").select("*").eq(
            "id", "resultado-001"
        ).execute().data[0]
        assert row["status"] == "processando"
        assert row["estrutura_tentativas"] == 1
        assert row["estrutura_erro"]

    @pytest.mark.asyncio
    async def test_esgotado_fecha_como_sucesso_com_erro_terminal(self):
        """D3: the THIRD attempt (2 retries used) closes the resultado out —
        the certidão itself is still valid (`status='sucesso'`), only the
        structured read gave up, and `estrutura_erro` says so."""
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[_resultado(tipo="serasa", status="processando")],
        )
        update_data = await service.process_manual_extraction(
            pdf_bytes=b"%PDF-1.4",
            resultado_id="resultado-001",
            consulta_id="consulta-001",
            nome_display="Serasa",
            org_id=ORG,
            db=db,
            tentativa=service.MAX_ESTRUTURA_TENTATIVAS,
            extract_text=AsyncMock(
                return_value=service.ExtractedPdfText(
                    para_ia=None, erro="Cota do provedor de IA esgotada. ...",
                )
            ),
        )
        assert update_data["status"] == "sucesso"
        assert update_data["estrutura_erro"]
        assert update_data["estrutura_tentativas"] == service.MAX_ESTRUTURA_TENTATIVAS

        row = db.table("certidao_resultados").select("*").eq(
            "id", "resultado-001"
        ).execute().data[0]
        assert row["status"] == "sucesso"
        assert row["estrutura_erro"]

    @pytest.mark.asyncio
    async def test_sucesso_limpa_estrutura_erro_de_uma_tentativa_anterior(self):
        """A retry that finally succeeds clears the reason a prior attempt
        left behind — a stale `estrutura_erro` next to a `sucesso` row would
        misreport the certidão as still failing."""
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[_resultado(
                tipo="serasa", status="processando",
                estrutura_erro="tentativa anterior falhou", estrutura_tentativas=1,
            )],
        )
        update_data = await service.process_manual_extraction(
            pdf_bytes=b"%PDF-1.4",
            resultado_id="resultado-001",
            consulta_id="consulta-001",
            nome_display="Serasa",
            org_id=ORG,
            db=db,
            tentativa=2,
            extract_text=AsyncMock(
                return_value=service.ExtractedPdfText(para_ia="texto extraído")
            ),
            analyze=AsyncMock(return_value="resumo"),
            analyze_estrutura=AsyncMock(return_value=None),
        )
        assert update_data["status"] == "sucesso"
        assert update_data["estrutura_erro"] is None
        row = db.table("certidao_resultados").select("*").eq(
            "id", "resultado-001"
        ).execute().data[0]
        assert row["estrutura_erro"] is None

    @pytest.mark.asyncio
    async def test_travado_e_respeitado_mesmo_no_esgotamento(self):
        """A human-owned resultado stays untouched by the structured leg even
        on the terminal attempt — `resultado`/`numero`/etc. never move."""
        estrutura_ia = AsyncMock()
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[_resultado(
                tipo="serasa", status="processando",
                resultado="negativa", resultado_origem="manual",
            )],
        )
        update_data = await service.process_manual_extraction(
            pdf_bytes=b"%PDF-1.4",
            resultado_id="resultado-001",
            consulta_id="consulta-001",
            nome_display="Serasa",
            org_id=ORG,
            db=db,
            resultado_origem_atual="manual",
            tentativa=service.MAX_ESTRUTURA_TENTATIVAS,
            extract_text=AsyncMock(
                return_value=service.ExtractedPdfText(para_ia="texto extraído")
            ),
            analyze=AsyncMock(return_value="resumo"),
            analyze_estrutura=estrutura_ia,
        )
        assert "resultado" not in update_data
        estrutura_ia.assert_not_awaited()
        row = db.table("certidao_resultados").select("*").eq(
            "id", "resultado-001"
        ).execute().data[0]
        assert row["resultado"] == "negativa"


# ---------------------------------------------------------------------------
# certidoes_por_parte / confirmar_resultado / mint_resultado_url
# ---------------------------------------------------------------------------


class TestCertidoesPorParte:
    def test_sem_consultas_para_a_parte_retorna_vazio(self):
        db = _db(certidao_consultas=[], certidao_resultados=[])
        assert service.certidoes_por_parte(db, ORG, "parte-1") == []

    def test_agrega_resultados_das_consultas_da_parte(self):
        db = _db(
            certidao_consultas=[
                _consulta_row(atendimento_parte_id="parte-1"),
            ],
            certidao_resultados=[
                _resultado(id="r1"), _resultado(id="r2", ordem=2, tipo="trf3"),
            ],
        )
        rows = service.certidoes_por_parte(db, ORG, "parte-1")
        assert {r["id"] for r in rows} == {"r1", "r2"}
        assert rows[0]["consulta_nome"] == "João da Silva"

    def test_nao_traz_consultas_de_outra_parte(self):
        db = _db(
            certidao_consultas=[
                _consulta_row(id="c-outra", atendimento_parte_id="parte-2"),
            ],
            certidao_resultados=[_resultado(consulta_id="c-outra")],
        )
        assert service.certidoes_por_parte(db, ORG, "parte-1") == []

    def test_consulta_excluida_nao_aparece(self):
        """Migration 161 — the contract-automation readiness read (`card_hub.
        contrato_gerador.validacao_extracao`) runs straight through this
        function, so a soft-deleted consulta's certidões must not count as
        evidence a party's certidões exist."""
        db = _db(
            certidao_consultas=[_consulta_row(
                atendimento_parte_id="parte-1",
                excluida_em="2026-09-01T10:00:00+00:00", excluida_por="user-1",
            )],
            certidao_resultados=[_resultado(id="r1")],
        )
        assert service.certidoes_por_parte(db, ORG, "parte-1") == []

    def test_a_query_nunca_seleciona_o_texto_da_certidao(self):
        """Migration 113: this panel polls like the consulta-detail screen.
        `MockSupabaseClient` does not project columns (see
        `test_matriculas_router.py::test_a_lista_nao_seleciona_o_texto_
        extraido`), so — same house pattern — the contract is asserted on
        the projection STRING itself."""
        assert "texto_extraido" not in service.RESULTADO_COLUNAS_SEM_TEXTO
        assert "formatacao" not in service.RESULTADO_COLUNAS_SEM_TEXTO
        assert "tem_transcricao" in service.RESULTADO_COLUNAS_SEM_TEXTO
        assert "id" in service.RESULTADO_COLUNAS_SEM_TEXTO
        assert "status" in service.RESULTADO_COLUNAS_SEM_TEXTO


class TestCertidoesPorCliente:
    """`certidoes_por_parte`'s sibling for a card's titular (migration
    116) — same shared `_resultados_das_consultas` body, keyed on
    `cliente_id` instead of `atendimento_parte_id`."""

    def test_sem_consultas_para_o_cliente_retorna_vazio(self):
        db = _db(certidao_consultas=[], certidao_resultados=[])
        assert service.certidoes_por_cliente(db, ORG, "cliente-1") == []

    def test_agrega_resultados_das_consultas_do_cliente(self):
        db = _db(
            certidao_consultas=[_consulta_row(cliente_id="cliente-1")],
            certidao_resultados=[
                _resultado(id="r1"), _resultado(id="r2", ordem=2, tipo="trf3"),
            ],
        )
        rows = service.certidoes_por_cliente(db, ORG, "cliente-1")
        assert {r["id"] for r in rows} == {"r1", "r2"}
        assert rows[0]["consulta_nome"] == "João da Silva"

    def test_nao_traz_consultas_de_outro_cliente(self):
        db = _db(
            certidao_consultas=[
                _consulta_row(id="c-outra", cliente_id="cliente-2"),
            ],
            certidao_resultados=[_resultado(consulta_id="c-outra")],
        )
        assert service.certidoes_por_cliente(db, ORG, "cliente-1") == []

    def test_inclui_situacao_cadastral_denormalizada(self):
        db = _db(
            certidao_consultas=[_consulta_row(
                cliente_id="cliente-1",
                situacao_cadastral="ativa",
                data_situacao="2026-08-01",
                situacao_origem="manual",
            )],
            certidao_resultados=[_resultado(id="r1")],
        )
        rows = service.certidoes_por_cliente(db, ORG, "cliente-1")
        assert rows[0]["consulta_situacao_cadastral"] == "ativa"
        assert rows[0]["consulta_data_situacao"] == "2026-08-01"
        assert rows[0]["consulta_situacao_origem"] == "manual"

    def test_consulta_excluida_nao_aparece(self):
        db = _db(
            certidao_consultas=[_consulta_row(
                cliente_id="cliente-1",
                excluida_em="2026-09-01T10:00:00+00:00", excluida_por="user-1",
            )],
            certidao_resultados=[_resultado(id="r1")],
        )
        assert service.certidoes_por_cliente(db, ORG, "cliente-1") == []

    def test_uma_consulta_ligada_por_vincular_parte_tambem_conta(self):
        """`vincular_parte` denormalizes `cliente_id` too (migration 107) —
        `certidoes_por_cliente` deliberately does not filter those out."""
        db = _db(
            certidao_consultas=[_consulta_row(
                atendimento_parte_id="parte-9", cliente_id="cliente-1",
            )],
            certidao_resultados=[_resultado(id="r1")],
        )
        rows = service.certidoes_por_cliente(db, ORG, "cliente-1")
        assert {r["id"] for r in rows} == {"r1"}


class TestAtualizarSituacaoCadastral:
    def test_grava_campos_e_estampa_origem_manual(self):
        db = _db(certidao_consultas=[_consulta_row()])
        updated = service.atualizar_situacao_cadastral(
            db, ORG, "consulta-001",
            {"situacao_cadastral": "baixada", "data_situacao": "2026-01-01"},
        )
        assert updated["situacao_cadastral"] == "baixada"
        assert updated["data_situacao"] == "2026-01-01"
        assert updated["situacao_origem"] == "manual"

    def test_consulta_inexistente_retorna_none(self):
        db = _db(certidao_consultas=[])
        assert service.atualizar_situacao_cadastral(
            db, ORG, "sumiu", {"situacao_cadastral": "ativa"}
        ) is None

    def test_consulta_de_outra_org_retorna_none(self):
        db = _db(certidao_consultas=[_consulta_row(org_id=OTHER_ORG)])
        assert service.atualizar_situacao_cadastral(
            db, ORG, "consulta-001", {"situacao_cadastral": "ativa"}
        ) is None

    def test_consulta_excluida_retorna_none(self):
        db = _db(certidao_consultas=[_consulta_row(
            excluida_em="2026-09-01T10:00:00+00:00", excluida_por="user-1",
        )])
        assert service.atualizar_situacao_cadastral(
            db, ORG, "consulta-001", {"situacao_cadastral": "ativa"}
        ) is None


class TestConfirmarResultado:
    def test_grava_campos_e_estampa_confirmacao(self):
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[_resultado()],
        )
        updated = service.confirmar_resultado(
            db, ORG, "resultado-001",
            {"resultado": "positiva", "numero": "X-1"}, "user-9",
        )
        assert updated["resultado"] == "positiva"
        assert updated["numero"] == "X-1"
        assert updated["resultado_origem"] == "manual"
        assert updated["confirmado_por"] == "user-9"
        assert updated["confirmado_em"] is not None

    def test_corpo_vazio_ainda_estampa_confirmacao(self):
        """A pure 'I reviewed this' confirm — no field changes, but the lock
        is set all the same."""
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[_resultado(resultado="negativa", resultado_origem="api")],
        )
        updated = service.confirmar_resultado(db, ORG, "resultado-001", {}, "user-9")
        assert updated["resultado"] == "negativa"
        assert updated["resultado_origem"] == "manual"
        assert updated["confirmado_por"] == "user-9"

    def test_resultado_inexistente_retorna_none(self):
        db = _db(certidao_resultados=[])
        assert service.confirmar_resultado(db, ORG, "sumiu", {}, "user-9") is None

    def test_resultado_de_outra_org_retorna_none(self):
        db = _db(certidao_resultados=[_resultado(org_id=OTHER_ORG)])
        assert service.confirmar_resultado(db, ORG, "resultado-001", {}, "user-9") is None

    def test_resultado_excluido_retorna_none(self):
        db = _db(certidao_resultados=[_resultado(
            excluida_em="2026-09-01T10:00:00+00:00", excluida_por="user-1",
        )])
        assert service.confirmar_resultado(db, ORG, "resultado-001", {}, "user-9") is None

    def test_nunca_devolve_o_texto_da_certidao(self):
        """🔴 An UPDATE returns its full row by default — including
        `texto_extraido`/`formatacao` once migration 113 lands them — and
        this dict rides straight into `confirmar_ou_corrigir_resultado`'s
        HTTP response. Stripped in the service, not merely absent from the
        test fixture: seed the row WITH text so the assertion is real."""
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[_resultado(
                texto_extraido="CPF: 123.456.789-00",
                formatacao=[{"start": 0, "end": 3, "bold": True, "underline": False}],
            )],
        )
        updated = service.confirmar_resultado(db, ORG, "resultado-001", {}, "user-9")
        assert "texto_extraido" not in updated
        assert "formatacao" not in updated


class TestMintResultadoUrl:
    @pytest.mark.asyncio
    async def test_chave_de_storage_e_assinada_e_logada(self):
        key = f"{ORG}/certidoes/consulta-001/cnd_federal_ab.pdf"
        db = _db(certidao_resultados=[_resultado(arquivo_url=key)])
        storage = FakeStorageBackend()
        result = await service.mint_resultado_url(
            db, storage, ORG, "resultado-001", usuario_id="user-1", intent="view",
        )
        assert result["url"].startswith("fake://storage/")
        assert result["expires_at"] is not None
        log = db.table("certidao_resultado_acessos").select("*").execute().data
        assert len(log) == 1
        assert log[0]["acao"] == "view"
        assert log[0]["documento_id"] == "resultado-001"

    @pytest.mark.asyncio
    async def test_url_externa_e_devolvida_sem_assinar(self):
        db = _db(certidao_resultados=[
            _resultado(arquivo_url="https://infosimples.com/x.pdf"),
        ])
        result = await service.mint_resultado_url(
            db, FakeStorageBackend(), ORG, "resultado-001", usuario_id="user-1",
        )
        assert result["url"] == "https://infosimples.com/x.pdf"
        assert result["expires_at"] is None

    @pytest.mark.asyncio
    async def test_sem_arquivo_retorna_marcador_de_erro(self):
        db = _db(certidao_resultados=[_resultado(arquivo_url=None)])
        result = await service.mint_resultado_url(
            db, FakeStorageBackend(), ORG, "resultado-001", usuario_id="user-1",
        )
        assert result == {"error": "sem_arquivo"}

    @pytest.mark.asyncio
    async def test_resultado_inexistente_retorna_none(self):
        db = _db(certidao_resultados=[])
        result = await service.mint_resultado_url(
            db, FakeStorageBackend(), ORG, "sumiu", usuario_id="user-1",
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_resultado_de_outra_org_retorna_none(self):
        db = _db(certidao_resultados=[
            _resultado(org_id=OTHER_ORG, arquivo_url="https://x/a.pdf"),
        ])
        result = await service.mint_resultado_url(
            db, FakeStorageBackend(), ORG, "resultado-001", usuario_id="user-1",
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_resultado_excluido_retorna_none(self):
        db = _db(certidao_resultados=[_resultado(
            arquivo_url="https://x/a.pdf",
            excluida_em="2026-09-01T10:00:00+00:00", excluida_por="user-1",
        )])
        result = await service.mint_resultado_url(
            db, FakeStorageBackend(), ORG, "resultado-001", usuario_id="user-1",
        )
        assert result is None


# ---------------------------------------------------------------------------
# Soft-delete / restore / purge — migration 161 (S3, audit-trail slice)
# ---------------------------------------------------------------------------


class TestSoftDeleteConsulta:
    def test_estampa_consulta_e_resultados(self):
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[
                _resultado(id="r1"), _resultado(id="r2", ordem=2, tipo="trf3"),
            ],
        )
        n = service.soft_delete_consulta(db, ORG, "consulta-001", "user-9")
        assert n == 2

        consulta = db.table("certidao_consultas").select("*").eq(
            "id", "consulta-001"
        ).execute().data[0]
        assert consulta["excluida_em"] is not None
        assert consulta["excluida_por"] == "user-9"

        resultados = db.table("certidao_resultados").select("*").execute().data
        assert all(r["excluida_em"] is not None for r in resultados)
        assert all(r["excluida_por"] == "user-9" for r in resultados)

    def test_nao_toca_o_storage(self):
        """The service function itself never imports/calls a storage seam —
        soft-delete is DB-only by construction, not by convention."""
        import inspect

        source = inspect.getsource(service.soft_delete_consulta)
        assert "storage" not in source

    def test_consulta_inexistente_retorna_none(self):
        db = _db(certidao_consultas=[])
        assert service.soft_delete_consulta(db, ORG, "sumiu", "user-9") is None

    def test_consulta_ja_excluida_retorna_none(self):
        db = _db(certidao_consultas=[_consulta_row(
            excluida_em="2026-09-01T10:00:00+00:00", excluida_por="user-1",
        )])
        assert service.soft_delete_consulta(db, ORG, "consulta-001", "user-9") is None

    def test_consulta_de_outra_org_retorna_none(self):
        db = _db(certidao_consultas=[_consulta_row(org_id=OTHER_ORG)])
        assert service.soft_delete_consulta(db, ORG, "consulta-001", "user-9") is None


class TestRestaurarConsulta:
    def test_limpa_consulta_e_resultados(self):
        db = _db(
            certidao_consultas=[_consulta_row(
                excluida_em="2026-09-01T10:00:00+00:00", excluida_por="user-1",
            )],
            certidao_resultados=[_resultado(
                id="r1",
                excluida_em="2026-09-01T10:00:00+00:00", excluida_por="user-1",
            )],
        )
        restored = service.restaurar_consulta(db, ORG, "consulta-001")
        assert restored["excluida_em"] is None
        assert restored["excluida_por"] is None

        resultado = db.table("certidao_resultados").select("*").execute().data[0]
        assert resultado["excluida_em"] is None
        assert resultado["excluida_por"] is None

    def test_consulta_inexistente_retorna_none(self):
        db = _db(certidao_consultas=[])
        assert service.restaurar_consulta(db, ORG, "sumiu") is None

    def test_consulta_nunca_excluida_retorna_none(self):
        db = _db(certidao_consultas=[_consulta_row()])
        assert service.restaurar_consulta(db, ORG, "consulta-001") is None

    def test_consulta_de_outra_org_retorna_none(self):
        db = _db(certidao_consultas=[_consulta_row(
            org_id=OTHER_ORG,
            excluida_em="2026-09-01T10:00:00+00:00", excluida_por="user-1",
        )])
        assert service.restaurar_consulta(db, ORG, "consulta-001") is None


class TestPurgeExcluidas:
    @pytest.mark.asyncio
    async def test_purga_apenas_apos_30_dias(self):
        """The whole point of the retention window: an excluded-yesterday
        consulta survives, an excluded-32-days-ago one does not."""
        ontem = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        antiga = (datetime.now(timezone.utc) - timedelta(days=32)).isoformat()
        db = _db(
            certidao_consultas=[
                _consulta_row(id="recente", excluida_em=ontem, excluida_por="user-1"),
                _consulta_row(id="antiga", excluida_em=antiga, excluida_por="user-1"),
            ],
            certidao_resultados=[
                _resultado(id="r-recente", consulta_id="recente",
                           excluida_em=ontem, excluida_por="user-1"),
                _resultado(id="r-antiga", consulta_id="antiga",
                           excluida_em=antiga, excluida_por="user-1"),
            ],
        )
        result = await service.purge_excluidas(db, FakeStorageBackend())
        assert result["consultas"] == 1
        assert result["resultados"] == 1

        remaining = {c["id"] for c in db.table("certidao_consultas").select("*").execute().data}
        assert remaining == {"recente"}
        remaining_resultados = {
            r["id"] for r in db.table("certidao_resultados").select("*").execute().data
        }
        assert remaining_resultados == {"r-recente"}

    @pytest.mark.asyncio
    async def test_nao_toca_consultas_ativas(self):
        db = _db(certidao_consultas=[_consulta_row()])
        result = await service.purge_excluidas(db, FakeStorageBackend())
        assert result == {"consultas": 0, "resultados": 0, "arquivos": 0}
        assert len(db.table("certidao_consultas").select("*").execute().data) == 1

    @pytest.mark.asyncio
    async def test_apaga_os_blobs(self):
        antiga = (datetime.now(timezone.utc) - timedelta(days=32)).isoformat()
        key = f"{ORG}/certidoes/consulta-001/cnd_federal_ab.pdf"
        db = _db(
            certidao_consultas=[_consulta_row(
                excluida_em=antiga, excluida_por="user-1",
            )],
            certidao_resultados=[_resultado(
                id="r1", arquivo_url=key,
                excluida_em=antiga, excluida_por="user-1",
            )],
        )
        storage = FakeStorageBackend()
        await storage.put(bucket=service.BUCKET, key=key, data=b"%PDF-x")
        result = await service.purge_excluidas(db, storage)
        assert result["arquivos"] == 1
        assert await storage.get(bucket=service.BUCKET, key=key) is None

    @pytest.mark.asyncio
    async def test_janela_customizavel(self):
        """`older_than_days` is a parameter, not a hardcoded 30 — the
        scheduler wraps a constant, this function does not own one."""
        cutoff_5d = (datetime.now(timezone.utc) - timedelta(days=6)).isoformat()
        db = _db(certidao_consultas=[_consulta_row(
            excluida_em=cutoff_5d, excluida_por="user-1",
        )])
        result = await service.purge_excluidas(
            db, FakeStorageBackend(), older_than_days=5,
        )
        assert result["consultas"] == 1


# ---------------------------------------------------------------------------
# _extract_pdf_text / ExtractedPdfText — migration 113
# ---------------------------------------------------------------------------

#: >=100 chars of filler so `classify_pdf_text_layer` (the seed's rung-1
#: gate) treats the page as a substantive, trustworthy text layer rather
#: than routing it to vision — same floor `test_transcription_formatting.py`
#: documents. Built with PyMuPDF directly (not reportlab) so the bytes carry
#: the font/flag metadata the seed's OWN bold detector reads.
_PREENCHIMENTO_CERTIDAO = (
    "Certidao emitida para fins de comprovacao de regularidade fiscal do "
    "requerente perante o orgao competente, sem qualquer valor probatorio "
    "adicional alem do quanto aqui descrito."
)


def _pdf_certidao_com_negrito() -> bytes:
    """A real, synthetic certidão PDF with one bold word — exercises
    `_extract_pdf_text`'s REAL text-layer rung end-to-end, no transcriber
    stub."""
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    y = 72.0
    page.insert_text((72, y), _PREENCHIMENTO_CERTIDAO[:70], fontsize=11)
    y += 16
    page.insert_text((72, y), _PREENCHIMENTO_CERTIDAO[70:], fontsize=11)
    y += 24
    page.insert_text((72, y), "Regular", fontsize=11, fontname="Helvetica-Bold")
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


class TestExtractPdfText:
    @pytest.mark.asyncio
    async def test_texto_e_formatacao_de_um_pdf_real(self):
        """`max_vision_pages=0` never needs a vision credential for a page
        with a real, substantive text layer — no transcriber stub here."""
        resultado = await service._extract_pdf_text(
            _pdf_certidao_com_negrito(), "CND Federal", org_id=None,
        )
        assert resultado.texto_extraido is not None
        assert "Regular" in resultado.texto_extraido
        assert any(r.bold for r in resultado.formatacao)

    @pytest.mark.asyncio
    async def test_para_ia_fica_no_formato_de_sempre(self):
        """UNCHANGED by migration 113 — same prefix, same shape."""
        resultado = await service._extract_pdf_text(
            _pdf_certidao_com_negrito(), "CND Federal", org_id=None,
        )
        assert resultado.para_ia.startswith("Certidão: CND Federal\n\n")
        assert "Regular" in resultado.para_ia

    @pytest.mark.asyncio
    async def test_pdf_invalido_nunca_levanta(self):
        """Contract §4: a failed transcription is logged, never raised, and
        leaves both fields empty — `erro` now names why."""
        resultado = await service._extract_pdf_text(b"nao e um pdf", "X", org_id=None)
        assert resultado.para_ia is None
        assert resultado.texto_extraido is None
        assert resultado.erro == service._ESTRUTURA_ERRO_MENSAGENS["no_pages"]

    @pytest.mark.asyncio
    async def test_pdf_sem_texto_confiavel_fica_vazio(self):
        """A page too short to clear the substantive-text floor routes to
        vision, which is disabled here (`max_vision_pages=0`, the automated
        flow's default) — `vision_disabled`, not an exception, still no
        `para_ia`, and `erro` names it (harmless: `_process_single_certidao`
        never reads this field)."""
        import fitz

        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "curto", fontsize=11)
        pdf_bytes = doc.tobytes()
        doc.close()

        resultado = await service._extract_pdf_text(pdf_bytes, "X", org_id=None)
        assert resultado.para_ia is None
        assert resultado.erro == service._ESTRUTURA_ERRO_MENSAGENS["vision_disabled"]

    @pytest.mark.asyncio
    async def test_max_vision_pages_zero_e_o_padrao(self):
        """`_extract_pdf_text`'s own default, UNCHANGED for any caller that
        does not pass `max_vision_pages` — the automated scheduler flow."""
        import fitz

        doc = fitz.open()
        doc.new_page().insert_text((72, 72), "curto", fontsize=11)
        pdf_bytes = doc.tobytes()
        doc.close()

        resultado = await service._extract_pdf_text(pdf_bytes, "X", org_id=None)
        assert resultado.erro == service._ESTRUTURA_ERRO_MENSAGENS["vision_disabled"]

    @pytest.mark.asyncio
    async def test_max_vision_pages_acima_de_zero_tenta_a_visao(self, monkeypatch):
        """Raising the cap (`CERTIDAO_MANUAL_MAX_VISION_PAGES`, the manual-
        upload path) actually reaches rung 2 — `missing_credentials`, not
        `vision_disabled`, is the proof the vision leg was attempted rather
        than skipped."""
        monkeypatch.setattr(
            "noctusai_lib.config.credentials.resolve_credential",
            lambda key, org_id=None: None,
        )
        import fitz

        doc = fitz.open()
        doc.new_page().insert_text((72, 72), "curto", fontsize=11)
        pdf_bytes = doc.tobytes()
        doc.close()

        resultado = await service._extract_pdf_text(
            pdf_bytes, "X", org_id=None,
            max_vision_pages=service.CERTIDAO_MANUAL_MAX_VISION_PAGES,
        )
        assert resultado.para_ia is None
        assert resultado.erro == service._ESTRUTURA_ERRO_MENSAGENS["missing_credentials"]


# ---------------------------------------------------------------------------
# _process_single_certidao — persists texto_extraido/formatacao (migration 113)
# ---------------------------------------------------------------------------


class TestProcessSingleCertidaoTranscricao:
    @pytest.mark.asyncio
    async def test_persiste_texto_e_formatacao_no_caminho_de_sucesso(self):
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[_resultado()],
        )
        http = _FakeHttp(_api_ok(), file_body=b"%PDF-1.4 real")
        extraido = service.ExtractedPdfText(
            para_ia=None, texto_extraido="Bold word here",
            formatacao=(FormatRange(start=0, end=4, bold=True),),
        )
        await service._process_single_certidao(
            CONFIG_FEDERAL, _consulta_row(), "tok", db,
            "resultado-001", http, FakeStorageBackend(),
            analyze=_noop_analyze, extract_text=AsyncMock(return_value=extraido),
            core_db=MockSupabaseClient(schema="public"),
        )
        row = db.table("certidao_resultados").select("*").eq(
            "id", "resultado-001"
        ).execute().data[0]
        assert row["texto_extraido"] == "Bold word here"
        assert row["formatacao"] == [
            {"start": 0, "end": 4, "bold": True, "underline": False}
        ]

    @pytest.mark.asyncio
    async def test_persiste_texto_no_caminho_nada_consta_com_recibo(self):
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[_resultado(tipo="cenprot", id="r-cenprot")],
        )
        http = _FakeHttp(
            {
                "code": 612,
                "errors": ["Não constam protestos"],
                "data": [],
                "site_receipts": ["https://x/cenprot.html"],
            },
            file_body=b"<html><body>Nao constam protestos</body></html>",
            file_content_type="text/html",
        )
        extraido = service.ExtractedPdfText(
            para_ia=None, texto_extraido="Nao constam protestos",
        )
        await service._process_single_certidao(
            config_for("cenprot"), _consulta_row(), "tok", db,
            "r-cenprot", http, FakeStorageBackend(),
            analyze=_noop_analyze, extract_text=AsyncMock(return_value=extraido),
            core_db=MockSupabaseClient(schema="public"),
        )
        row = db.table("certidao_resultados").select("*").eq(
            "id", "r-cenprot"
        ).execute().data[0]
        assert row["texto_extraido"] == "Nao constam protestos"
        assert row["formatacao"] == []

    @pytest.mark.asyncio
    async def test_transcricao_vazia_nao_falha_a_certidao(self):
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[_resultado()],
        )
        http = _FakeHttp(_api_ok(), file_body=b"%PDF-1.4 real")
        await service._process_single_certidao(
            CONFIG_FEDERAL, _consulta_row(), "tok", db,
            "resultado-001", http, FakeStorageBackend(),
            analyze=_noop_analyze,
            extract_text=AsyncMock(
                return_value=service.ExtractedPdfText(para_ia=None)
            ),
            core_db=MockSupabaseClient(schema="public"),
        )
        row = db.table("certidao_resultados").select("*").eq(
            "id", "resultado-001"
        ).execute().data[0]
        assert row["status"] == "sucesso"
        assert row["texto_extraido"] is None
        assert row["formatacao"] == []

    @pytest.mark.asyncio
    async def test_nada_e_armazenado_nunca_chama_extract_text(self):
        """Content-type desconhecido -> nada persistido -> nada a transcrever."""
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[_resultado()],
        )
        http = _FakeHttp(
            _api_ok(), file_body=b"\x89PNG\r\n", file_content_type="image/png"
        )
        extract = AsyncMock()
        await service._process_single_certidao(
            CONFIG_FEDERAL, _consulta_row(), "tok", db,
            "resultado-001", http, FakeStorageBackend(),
            analyze=_noop_analyze, extract_text=extract,
            core_db=MockSupabaseClient(schema="public"),
        )
        extract.assert_not_awaited()


# ---------------------------------------------------------------------------
# process_manual_upload — persists but never RETURNS the text (migration 113)
# ---------------------------------------------------------------------------


class TestProcessManualUpload:
    """The SYNCHRONOUS, storage-only half — `process_manual_extraction`
    (the AI/vision leg) is its own class below; splitting them is the point
    of the D3/item-4 redesign (KB roadmap
    `sw-extraction-contract-gate-2026-09.md`)."""

    @pytest.mark.asyncio
    async def test_persiste_arquivo_e_marca_processando(self):
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[_resultado(tipo="serasa", nome_display="Serasa")],
        )
        update_data = await service.process_manual_upload(
            pdf_bytes=b"%PDF-1.4",
            resultado_id="resultado-001",
            consulta=_consulta_row(),
            tipo="serasa",
            nome_display="Serasa",
            org_id=ORG,
            db=db,
            storage=FakeStorageBackend(),
        )
        assert update_data["status"] == "processando"
        assert update_data["arquivo_url"] is not None
        assert update_data["arquivo_nome"] == "serasa.pdf"

        row = db.table("certidao_resultados").select("*").eq(
            "id", "resultado-001"
        ).execute().data[0]
        assert row["status"] == "processando"
        assert row["arquivo_url"] is not None
        assert row["api_requested_at"] is not None


class TestProcessManualExtractionTranscricao:
    @pytest.mark.asyncio
    async def test_persiste_no_banco_mas_nunca_devolve_ao_chamador(self):
        db = _db(
            certidao_consultas=[_consulta_row()],
            certidao_resultados=[_resultado(tipo="serasa", nome_display="Serasa")],
        )
        extraido = service.ExtractedPdfText(
            para_ia="Certidão: Serasa\n\nBold word here",
            texto_extraido="Bold word here",
            formatacao=(FormatRange(start=0, end=4, bold=True),),
        )
        update_data = await service.process_manual_extraction(
            pdf_bytes=b"%PDF-1.4",
            resultado_id="resultado-001",
            consulta_id="consulta-001",
            nome_display="Serasa",
            org_id=ORG,
            db=db,
            extract_text=AsyncMock(return_value=extraido),
            analyze=AsyncMock(return_value="resumo"),
            analyze_estrutura=AsyncMock(return_value=None),
        )
        # 🔴 The router never echoes THIS dict — it runs after the response
        # already went out — but `RESULTADO_COLUNAS_SEM_TEXTO`'s rule still
        # holds for whatever a caller (tests, the retry sweep) inspects here.
        assert "texto_extraido" not in update_data
        assert "formatacao" not in update_data

        row = db.table("certidao_resultados").select("*").eq(
            "id", "resultado-001"
        ).execute().data[0]
        assert row["texto_extraido"] == "Bold word here"
        assert row["formatacao"] == [
            {"start": 0, "end": 4, "bold": True, "underline": False}
        ]


# ---------------------------------------------------------------------------
# obter_transcricao_resultado / renderizar_transcricao_pdf — migration 113
# ---------------------------------------------------------------------------


class TestObterTranscricaoResultado:
    def test_resultado_inexistente_retorna_none(self):
        db = _db(certidao_resultados=[])
        assert service.obter_transcricao_resultado(
            db, ORG, "sumiu", usuario_id="user-1"
        ) is None

    def test_resultado_de_outra_org_retorna_none(self):
        db = _db(certidao_resultados=[
            _resultado(org_id=OTHER_ORG, texto_extraido="x"),
        ])
        assert service.obter_transcricao_resultado(
            db, ORG, "resultado-001", usuario_id="user-1"
        ) is None

    def test_resultado_excluido_retorna_none(self):
        db = _db(certidao_resultados=[_resultado(
            texto_extraido="x",
            excluida_em="2026-09-01T10:00:00+00:00", excluida_por="user-1",
        )])
        assert service.obter_transcricao_resultado(
            db, ORG, "resultado-001", usuario_id="user-1"
        ) is None

    def test_sem_transcricao_retorna_indisponivel_sem_logar(self):
        db = _db(certidao_resultados=[_resultado(texto_extraido=None)])
        result = service.obter_transcricao_resultado(
            db, ORG, "resultado-001", usuario_id="user-1"
        )
        assert result == {"disponivel": False}
        assert db.table("certidao_resultado_acessos").select("*").execute().data == []

    def test_com_transcricao_devolve_texto_html_e_loga_o_acesso(self):
        db = _db(certidao_resultados=[_resultado(
            texto_extraido="Bold word here",
            formatacao=[{"start": 0, "end": 4, "bold": True, "underline": False}],
        )])
        result = service.obter_transcricao_resultado(
            db, ORG, "resultado-001", usuario_id="user-1"
        )
        assert result["disponivel"] is True
        assert result["texto"] == "Bold word here"
        assert "<b>Bold</b>" in result["texto_html"]
        assert result["formatacao"] == [
            {"start": 0, "end": 4, "bold": True, "underline": False}
        ]

        log = db.table("certidao_resultado_acessos").select("*").execute().data
        assert len(log) == 1
        assert log[0]["acao"] == "view"
        assert log[0]["documento_id"] == "resultado-001"


class TestRenderizarTranscricaoPdf:
    def test_pdf_traz_titulo_e_texto_com_negrito(self):
        pdf_bytes = service.renderizar_transcricao_pdf(
            "CND Federal", "Bold word here",
            [{"start": 0, "end": 4, "bold": True, "underline": False}],
        )
        assert pdf_bytes[:5] == b"%PDF-"

        import fitz

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        texto = "".join(page.get_text() for page in doc)
        assert "Transcrição — CND Federal" in texto
        assert "Bold word here" in texto

        spans = {}
        for page in doc:
            info = page.get_text("dict", flags=fitz.TEXTFLAGS_DICT)
            for block in info["blocks"]:
                for line in block.get("lines", []):
                    for span in line["spans"]:
                        spans[span["text"]] = span
        assert "Bold" in spans["Bold"]["font"]
        assert "Bold" not in spans[" word here"]["font"]

    def test_glifo_nao_suportado_levanta_com_o_caractere_nomeado(self):
        from noctusai_lib.integrations.documents.abnt import UnsupportedGlyphError

        with pytest.raises(UnsupportedGlyphError) as exc:
            service.renderizar_transcricao_pdf("X", "emoji \U0001F600 aqui", [])
        assert "\U0001F600" in str(exc.value) or "1F600" in str(exc.value)
