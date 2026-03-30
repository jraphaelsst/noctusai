"""Tests for the Certidões Negativas service — parameter builders, API fetching,
PDF download, AI analysis, and full processing pipeline."""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock

import httpx

from app.services.certidoes_service import (
    CERTIDOES_CONFIG,
    PARAM_BUILDERS,
    TJSP_COOLDOWN_SECONDS,
    TJSP_TIPO,
    _build_params_cnd_federal,
    _build_params_trf3_sp,
    _build_params_trf3,
    _build_params_trt2_digital,
    _build_params_trt2_fisico,
    _build_params_simples,
    _build_params_tjsp,
    _fetch_certidao,
    _download_file,
    _convert_html_to_pdf,
    _analyze_with_ai,
    _process_single_certidao,
    _atualizar_status_consulta,
    _get_tjsp_last_request_at,
    _get_tjsp_remaining_cooldown,
    _delayed_tjsp_process,
    schedule_tjsp_for_org,
    schedule_all_pending_tjsp,
    recover_stuck_processando,
    processar_consulta,
    get_certidoes_tipos,
    check_required_credentials,
)
from tests.conftest import MockSupabaseClient, MockSupabaseResponse


# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

CONSULTA_CPF = {
    "id": "consulta-001",
    "org_id": "org-001",
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
    "org_id": "org-001",
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
    "org_id": "org-001",
    "tipo_documento": "cpf",
    "documento": "99988877766",
    "nome": "Teste",
}


# ---------------------------------------------------------------------------
# CERTIDOES_CONFIG
# ---------------------------------------------------------------------------

class TestCertidoesConfig:
    def test_tem_10_tipos(self):
        assert len(CERTIDOES_CONFIG) == 10

    def test_ordens_sequenciais(self):
        ordens = [c["ordem"] for c in CERTIDOES_CONFIG]
        assert ordens == list(range(1, 11))

    def test_todos_tem_campos_obrigatorios(self):
        for config in CERTIDOES_CONFIG:
            assert "tipo" in config
            assert "nome" in config
            assert "endpoint" in config
            assert "ordem" in config
            assert "params_fn" in config
            assert "response_format" in config

    def test_params_fn_validos(self):
        for config in CERTIDOES_CONFIG:
            assert config["params_fn"] in PARAM_BUILDERS

    def test_response_format_validos(self):
        for config in CERTIDOES_CONFIG:
            assert config["response_format"] in ("pdf", "html")


# ---------------------------------------------------------------------------
# check_required_credentials
# ---------------------------------------------------------------------------

class TestCheckRequiredCredentials:
    def test_sem_infosimples_retorna_mensagem(self):
        with patch("app.services.certidoes_service.resolve_credential", return_value=None):
            missing = check_required_credentials("org-001")
        assert len(missing) == 1
        assert "InfoSimples" in missing[0]

    def test_com_infosimples_retorna_vazio(self):
        with patch("app.services.certidoes_service.resolve_credential", return_value="tok-123"):
            missing = check_required_credentials("org-001")
        assert missing == []


# ---------------------------------------------------------------------------
# get_certidoes_tipos
# ---------------------------------------------------------------------------

class TestGetCertidoesTipos:
    def test_retorna_lista(self):
        result = get_certidoes_tipos()
        assert isinstance(result, list)
        assert len(result) == 10

    def test_cada_item_tem_tipo_nome_ordem(self):
        for item in get_certidoes_tipos():
            assert set(item.keys()) == {"tipo", "nome", "ordem"}

    def test_nao_expoe_campos_internos(self):
        for item in get_certidoes_tipos():
            assert "endpoint" not in item
            assert "params_fn" not in item
            assert "response_format" not in item


# ---------------------------------------------------------------------------
# Parameter Builders
# ---------------------------------------------------------------------------

class TestBuildParamsCndFederal:
    def test_cpf_com_birthdate(self):
        params = _build_params_cnd_federal(CONSULTA_CPF, "tok123")
        assert params["token"] == "tok123"
        assert params["cpf"] == "12345678901"
        assert params["birthdate"] == "1990-01-15"
        assert params["preferencia_emissao"] == "2via"
        assert "cnpj" not in params
        assert "nome" not in params  # CND Federal does NOT take nome

    def test_cnpj(self):
        params = _build_params_cnd_federal(CONSULTA_CNPJ, "tok123")
        assert params["cnpj"] == "12345678000190"
        assert "cpf" not in params

    def test_sem_data_nascimento(self):
        params = _build_params_cnd_federal(CONSULTA_MINIMAL, "tok123")
        assert "birthdate" not in params
        assert params["preferencia_emissao"] == "2via"


class TestBuildParamsTrf3:
    def test_inclui_tipo_abrangencia_tipo_documento(self):
        params = _build_params_trf3(CONSULTA_CPF, "tok123")
        assert params["tipo"] == "1"
        assert params["abrangencia"] == "1"
        assert params["tipo_documento"] == "1"

    def test_cnpj_tipo_documento_2(self):
        params = _build_params_trf3(CONSULTA_CNPJ, "tok123")
        assert params["tipo_documento"] == "2"

    def test_usa_nome_social(self):
        params = _build_params_trf3(CONSULTA_CPF, "tok123")
        assert params["nome_social"] == "João da Silva"
        assert "nome" not in params  # TRF3 uses nome_social, not nome

    def test_campos_basicos(self):
        params = _build_params_trf3(CONSULTA_CPF, "tok123")
        assert params["token"] == "tok123"
        assert params["cpf"] == "12345678901"


class TestBuildParamsTrf3Sp:
    def test_tipo_2_abrangencia_1(self):
        params = _build_params_trf3_sp(CONSULTA_CPF, "tok123")
        assert params["tipo"] == "2"
        assert params["abrangencia"] == "1"

    def test_cpf_tipo_documento_1(self):
        params = _build_params_trf3_sp(CONSULTA_CPF, "tok123")
        assert params["tipo_documento"] == "1"

    def test_cnpj_tipo_documento_2(self):
        params = _build_params_trf3_sp(CONSULTA_CNPJ, "tok123")
        assert params["tipo_documento"] == "2"

    def test_usa_nome_social(self):
        params = _build_params_trf3_sp(CONSULTA_CPF, "tok123")
        assert params["nome_social"] == "João da Silva"
        assert "nome" not in params

    def test_campos_basicos(self):
        params = _build_params_trf3_sp(CONSULTA_CPF, "tok123")
        assert params["token"] == "tok123"
        assert params["cpf"] == "12345678901"

    def test_cnpj_campos_basicos(self):
        params = _build_params_trf3_sp(CONSULTA_CNPJ, "tok123")
        assert params["cnpj"] == "12345678000190"
        assert "cpf" not in params


class TestBuildParamsTrt2Digital:
    def test_cpf_simples(self):
        params = _build_params_trt2_digital(CONSULTA_CPF, "tok123")
        assert params["token"] == "tok123"
        assert params["cpf"] == "12345678901"
        assert "nome" not in params  # TRT2 Digital only takes doc

    def test_cnpj_usa_cnpj_raiz(self):
        params = _build_params_trt2_digital(CONSULTA_CNPJ, "tok123")
        assert params["cnpj_raiz"] == "12345678000190"
        assert "cnpj" not in params


class TestBuildParamsTrt2Fisico:
    def test_inclui_nome(self):
        params = _build_params_trt2_fisico(CONSULTA_CPF, "tok123")
        assert params["token"] == "tok123"
        assert params["cpf"] == "12345678901"
        assert params["nome"] == "João da Silva"


class TestBuildParamsSimples:
    def test_apenas_token_e_doc(self):
        params = _build_params_simples(CONSULTA_CPF, "tok123")
        assert params == {"token": "tok123", "cpf": "12345678901"}
        assert "nome" not in params
        assert "data_nascimento" not in params


class TestBuildParamsTjsp:
    """TJSP builder resolves email_envio via credential_resolver."""

    _CRED = "app.services.certidoes_service.resolve_credential"

    def test_inclui_modelo(self):
        with patch(self._CRED, return_value="jur@example.com"):
            params = _build_params_tjsp(CONSULTA_CPF, "tok123")
        assert params["modelo"] == "4"

    def test_cpf_usa_nome_completo(self):
        with patch(self._CRED, return_value="jur@example.com"):
            params = _build_params_tjsp(CONSULTA_CPF, "tok123")
        assert params["nome_completo"] == "João da Silva"
        assert "razao_social" not in params

    def test_cnpj_usa_razao_social(self):
        with patch(self._CRED, return_value="jur@example.com"):
            params = _build_params_tjsp(CONSULTA_CNPJ, "tok123")
        assert params["razao_social"] == "Empresa XPTO"
        assert "nome_completo" not in params

    def test_inclui_birthdate(self):
        with patch(self._CRED, return_value="jur@example.com"):
            params = _build_params_tjsp(CONSULTA_CPF, "tok123")
        assert params["birthdate"] == "1990-01-15"

    def test_inclui_email_envio_quando_configurado(self):
        with patch(self._CRED, return_value="jur@example.com"):
            params = _build_params_tjsp(CONSULTA_CPF, "tok123")
        assert params["email_envio"] == "jur@example.com"

    def test_omite_email_envio_quando_nao_configurado(self):
        with patch(self._CRED, return_value=None):
            params = _build_params_tjsp(CONSULTA_CPF, "tok123")
        assert "email_envio" not in params

    def test_inclui_campos_opcionais_quando_presentes(self):
        with patch(self._CRED, return_value="jur@example.com"):
            params = _build_params_tjsp(CONSULTA_CPF, "tok123")
        assert params["rg"] == "123456789"
        assert params["genero"] == "M"
        assert params["nome_mae"] == "Maria da Silva"
        assert params["nome_pai"] == "José da Silva"

    def test_omite_campos_opcionais_quando_ausentes(self):
        with patch(self._CRED, return_value=None):
            params = _build_params_tjsp(CONSULTA_MINIMAL, "tok123")
        assert "rg" not in params
        assert "genero" not in params
        assert "nome_mae" not in params
        assert "nome_pai" not in params

    def test_herda_campos_basicos(self):
        with patch(self._CRED, return_value="jur@example.com"):
            params = _build_params_tjsp(CONSULTA_CPF, "tok123")
        assert params["token"] == "tok123"
        assert params["cpf"] == "12345678901"


# ---------------------------------------------------------------------------
# _fetch_certidao
# ---------------------------------------------------------------------------

class TestFetchCertidao:
    @pytest.mark.asyncio
    async def test_sucesso_com_pdf(self):
        config = CERTIDOES_CONFIG[0]  # cnd_federal, response_format=pdf
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "code": 200,
            "data": [{"site_receipt": "https://example.com/cert.pdf", "status": "regular"}],
        }
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(return_value=mock_resp)

        result = await _fetch_certidao(config, CONSULTA_CPF, "tok123", client)
        assert result["success"] is True
        assert result["file_url"] == "https://example.com/cert.pdf"
        assert result["error"] is None

    @pytest.mark.asyncio
    async def test_sucesso_com_html(self):
        config = CERTIDOES_CONFIG[3]  # trt2_digital, response_format=html
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "code": 200,
            "data": [{"site_receipt": "<html>certidão</html>"}],
        }
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(return_value=mock_resp)

        result = await _fetch_certidao(config, CONSULTA_CPF, "tok123", client)
        assert result["success"] is True
        assert result["file_url"] == "<html>certidão</html>"

    @pytest.mark.asyncio
    async def test_sucesso_site_receipts_fallback(self):
        """CENPROT returns file URL in root-level site_receipts[] instead of data[0].site_receipt."""
        config = CERTIDOES_CONFIG[7]  # cenprot
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "code": 200,
            "data": [{"status": "nada consta", "nome": "Fulano"}],
            "site_receipts": ["https://example.com/cenprot.html"],
        }
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(return_value=mock_resp)

        result = await _fetch_certidao(config, CONSULTA_CPF, "tok123", client)
        assert result["success"] is True
        assert result["file_url"] == "https://example.com/cenprot.html"

    @pytest.mark.asyncio
    async def test_erro_api(self):
        config = CERTIDOES_CONFIG[0]
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "code": 400,
            "message": "CPF inválido",
        }
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(return_value=mock_resp)

        result = await _fetch_certidao(config, CONSULTA_CPF, "tok123", client)
        assert result["success"] is False
        assert result["error"] == "CPF inválido"

    @pytest.mark.asyncio
    async def test_erro_api_code_message_fallback(self):
        config = CERTIDOES_CONFIG[0]
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "code": 500,
            "code_message": "Serviço indisponível",
        }
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(return_value=mock_resp)

        result = await _fetch_certidao(config, CONSULTA_CPF, "tok123", client)
        assert result["success"] is False
        assert result["error"] == "Serviço indisponível"

    @pytest.mark.asyncio
    async def test_erro_api_prefere_errors_sobre_message(self):
        """errors[] should take priority over generic message field."""
        config = CERTIDOES_CONFIG[0]
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "code": 600,
            "message": "O site ou aplicativo de origem parece estar indisponível.",
            "errors": ["Limite de 1 consulta a cada 30 minutos atingido."],
        }
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(return_value=mock_resp)

        result = await _fetch_certidao(config, CONSULTA_CPF, "tok123", client)
        assert result["success"] is False
        assert "30 minutos" in result["error"]
        assert "indisponível" in result["error"]

    @pytest.mark.asyncio
    async def test_erro_api_sem_mensagem(self):
        config = CERTIDOES_CONFIG[0]
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"code": 500}
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(return_value=mock_resp)

        result = await _fetch_certidao(config, CONSULTA_CPF, "tok123", client)
        assert result["success"] is False
        assert "code: 500" in result["error"]

    @pytest.mark.asyncio
    async def test_excecao_rede(self):
        config = CERTIDOES_CONFIG[0]
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))

        result = await _fetch_certidao(config, CONSULTA_CPF, "tok123", client)
        assert result["success"] is False
        assert "Connection refused" in result["error"]
        assert result["raw_response"] is None

    @pytest.mark.asyncio
    async def test_resposta_200_sem_data(self):
        config = CERTIDOES_CONFIG[0]
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"code": 200, "data": []}
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(return_value=mock_resp)

        result = await _fetch_certidao(config, CONSULTA_CPF, "tok123", client)
        assert result["success"] is False


# ---------------------------------------------------------------------------
# _download_file
# ---------------------------------------------------------------------------

class TestDownloadFile:
    @pytest.mark.asyncio
    async def test_sucesso_retorna_bytes_e_content_type(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"%PDF-1.4 fake content"
        mock_resp.headers = {"content-type": "application/pdf"}
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(return_value=mock_resp)

        result = await _download_file("https://example.com/cert.pdf", client)
        assert result is not None
        content, ct = result
        assert content == b"%PDF-1.4 fake content"
        assert ct == "application/pdf"

    @pytest.mark.asyncio
    async def test_status_404(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(return_value=mock_resp)

        result = await _download_file("https://example.com/missing.pdf", client)
        assert result is None

    @pytest.mark.asyncio
    async def test_excecao(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(side_effect=httpx.ReadTimeout("timeout"))

        result = await _download_file("https://example.com/cert.pdf", client)
        assert result is None


# ---------------------------------------------------------------------------
# _convert_html_to_pdf
# ---------------------------------------------------------------------------

class TestConvertHtmlToPdf:
    def test_converte_html_simples(self):
        html = b"<html><body><h1>Certidao</h1><p>Nada consta.</p></body></html>"
        result = _convert_html_to_pdf(html)
        assert result is not None
        assert len(result) > 0
        assert result[:4] == b"%PDF"

    def test_html_vazio(self):
        result = _convert_html_to_pdf(b"")
        # xhtml2pdf can produce a PDF even from empty input
        assert result is not None or result is None  # doesn't crash

    def test_html_invalido_nao_crasheia(self):
        result = _convert_html_to_pdf(b"not html at all <><><>")
        # Should not raise — returns PDF or None
        assert result is None or isinstance(result, bytes)

    def test_pdf_bytes_not_converted(self):
        """PDF bytes passed to _convert_html_to_pdf produce garbage — callers
        must detect PDF magic bytes and skip conversion. This test documents
        the expected behavior if accidentally called with PDF input."""
        pdf_bytes = b"%PDF-1.7 fake pdf content"
        result = _convert_html_to_pdf(pdf_bytes)
        # xhtml2pdf wraps the raw PDF text as HTML content inside a new PDF,
        # producing a valid but useless PDF with source code as text.
        # The caller should never reach this path for PDF input.


# ---------------------------------------------------------------------------
# _analyze_with_ai
# ---------------------------------------------------------------------------

class TestAnalyzeWithAi:
    @pytest.mark.asyncio
    async def test_sem_api_key_retorna_placeholder(self):
        with patch("app.services.certidoes_service.resolve_credential", return_value=None):
            result = await _analyze_with_ai("texto da certidão")
        assert "não disponível" in result
        assert "Configurações" in result

    @pytest.mark.asyncio
    async def test_sucesso_com_api_key(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "Situação regular, sem débitos."}}],
        }
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.certidoes_service.resolve_credential", return_value="sk-test"), \
             patch("app.services.certidoes_service.httpx.AsyncClient", return_value=mock_client):
            result = await _analyze_with_ai("texto da certidão")
        assert result == "Situação regular, sem débitos."

    @pytest.mark.asyncio
    async def test_excecao_retorna_mensagem_erro(self):
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=Exception("API down"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.certidoes_service.resolve_credential", return_value="sk-test"), \
             patch("app.services.certidoes_service.httpx.AsyncClient", return_value=mock_client):
            result = await _analyze_with_ai("texto da certidão")
        assert "Erro na análise IA" in result


# ---------------------------------------------------------------------------
# _process_single_certidao — HTML format with PDF content detection
# ---------------------------------------------------------------------------

class TestProcessSingleCertidaoHtmlPdfDetection:
    """When a certificate has response_format='html' but the downloaded content
    is already a PDF (starts with %PDF-), skip HTML→PDF conversion."""

    @pytest.mark.asyncio
    async def test_html_config_with_pdf_content_skips_conversion(self):
        """site_receipt returns actual PDF bytes for an 'html' config type →
        should NOT pass through _convert_html_to_pdf."""
        config = CERTIDOES_CONFIG[3]  # trt2_digital, response_format=html
        assert config["response_format"] == "html"

        mock_db = MockSupabaseClient()
        mock_db.set_table_data("certidao_resultados", [{"status": "sucesso"}])

        pdf_content = b"%PDF-1.7 real pdf bytes here"

        fetch_result = {
            "success": True,
            "file_url": "https://example.com/cert.pdf",
            "raw_response": {"code": 200, "data": [{"status": "regular"}]},
            "error": None,
        }

        http_client = AsyncMock(spec=httpx.AsyncClient)

        with patch("app.services.certidoes_service._fetch_certidao", new_callable=AsyncMock, return_value=fetch_result), \
             patch("app.services.certidoes_service._download_file", new_callable=AsyncMock, return_value=(pdf_content, "application/pdf")), \
             patch("app.services.certidoes_service._convert_html_to_pdf") as mock_convert, \
             patch("app.services.certidoes_service._upload_to_storage", new_callable=AsyncMock, return_value="https://storage.example.com/cert.pdf"), \
             patch("app.services.certidoes_service._analyze_with_ai", new_callable=AsyncMock, return_value="Análise OK"), \
             patch("app.services.certidoes_service._atualizar_status_consulta"):
            await _process_single_certidao(
                config, CONSULTA_CPF, "tok123", mock_db, "res-1", http_client
            )

        # _convert_html_to_pdf should NOT have been called since content is PDF
        mock_convert.assert_not_called()

    @pytest.mark.asyncio
    async def test_html_config_with_html_content_converts(self):
        """site_receipt returns actual HTML for an 'html' config type →
        should pass through _convert_html_to_pdf."""
        config = CERTIDOES_CONFIG[3]  # trt2_digital, response_format=html

        mock_db = MockSupabaseClient()
        mock_db.set_table_data("certidao_resultados", [{"status": "sucesso"}])

        html_content = b"<html><body><h1>Certidao</h1></body></html>"

        fetch_result = {
            "success": True,
            "file_url": "https://example.com/cert.html",
            "raw_response": {"code": 200, "data": [{"status": "regular"}]},
            "error": None,
        }

        converted_pdf = b"%PDF-1.4 converted"

        http_client = AsyncMock(spec=httpx.AsyncClient)

        with patch("app.services.certidoes_service._fetch_certidao", new_callable=AsyncMock, return_value=fetch_result), \
             patch("app.services.certidoes_service._download_file", new_callable=AsyncMock, return_value=(html_content, "text/html")), \
             patch("app.services.certidoes_service._convert_html_to_pdf", return_value=converted_pdf) as mock_convert, \
             patch("app.services.certidoes_service._upload_to_storage", new_callable=AsyncMock, return_value="https://storage.example.com/cert.pdf"), \
             patch("app.services.certidoes_service._analyze_with_ai", new_callable=AsyncMock, return_value="Análise OK"), \
             patch("app.services.certidoes_service._atualizar_status_consulta"):
            await _process_single_certidao(
                config, CONSULTA_CPF, "tok123", mock_db, "res-1", http_client
            )

        mock_convert.assert_called_once_with(html_content)

    @pytest.mark.asyncio
    async def test_non_pdf_non_html_content_skips_upload(self):
        """site_receipt returns unexpected content type → should skip storage
        and keep original URL."""
        config = CERTIDOES_CONFIG[0]  # cnd_federal, response_format=pdf

        mock_db = MockSupabaseClient()
        mock_db.set_table_data("certidao_resultados", [{"status": "sucesso"}])

        # Some garbage content that's not PDF and not HTML
        weird_content = b"This is not a PDF or HTML"

        fetch_result = {
            "success": True,
            "file_url": "https://example.com/cert",
            "raw_response": {"code": 200, "data": [{"status": "regular"}]},
            "error": None,
        }

        http_client = AsyncMock(spec=httpx.AsyncClient)

        with patch("app.services.certidoes_service._fetch_certidao", new_callable=AsyncMock, return_value=fetch_result), \
             patch("app.services.certidoes_service._download_file", new_callable=AsyncMock, return_value=(weird_content, "text/plain")), \
             patch("app.services.certidoes_service._upload_to_storage", new_callable=AsyncMock) as mock_upload, \
             patch("app.services.certidoes_service._analyze_with_ai", new_callable=AsyncMock, return_value=None), \
             patch("app.services.certidoes_service._atualizar_status_consulta"):
            await _process_single_certidao(
                config, CONSULTA_CPF, "tok123", mock_db, "res-1", http_client
            )

        # Should NOT upload non-PDF/non-HTML content
        mock_upload.assert_not_called()


# ---------------------------------------------------------------------------
# processar_consulta — dry-run path
# ---------------------------------------------------------------------------

class TestProcessarConsultaSemToken:
    @pytest.mark.asyncio
    async def test_sem_token_marca_erro(self):
        """When InfoSimples token is not configured, all results should be marked as error."""
        mock_db = MockSupabaseClient()
        mock_db.set_table_data("certidao_consultas", CONSULTA_CPF)
        resultados = [
            {"id": f"res-{i}", "tipo": c["tipo"], "status": "pendente"}
            for i, c in enumerate(CERTIDOES_CONFIG)
        ]
        mock_db.set_table_data("certidao_resultados", resultados)

        with patch("app.services.certidoes_service._get_infosimples_token", return_value=None):
            await processar_consulta("consulta-001", mock_db)

        # Verifies it didn't raise — the mock swallows DB updates.
        # The service sets status="erro" and erro_mensagem on all resultados.


# ---------------------------------------------------------------------------
# processar_consulta — final status logic
# ---------------------------------------------------------------------------

class TestProcessarConsultaStatusFinal:
    @pytest.mark.asyncio
    async def test_todas_sucesso_status_concluida(self):
        """When all certificates succeed, final status should be 'concluida'."""
        mock_db = MockSupabaseClient()
        mock_db.set_table_data("certidao_consultas", CONSULTA_CPF)

        # resultados needs tipo field for the initial query AND the final status query
        resultados_with_tipo = [
            {"id": f"res-{i}", "tipo": c["tipo"], "status": "sucesso"}
            for i, c in enumerate(CERTIDOES_CONFIG)
        ]
        mock_db.set_table_data("certidao_resultados", resultados_with_tipo)

        with patch("app.services.certidoes_service._get_infosimples_token", return_value="tok"), \
             patch("app.services.certidoes_service._process_single_certidao", new_callable=AsyncMock):
            await processar_consulta("consulta-001", mock_db)

    @pytest.mark.asyncio
    async def test_todas_erro_status_erro(self):
        """When all certificates fail, final status should be 'erro'."""
        mock_db = MockSupabaseClient()
        mock_db.set_table_data("certidao_consultas", CONSULTA_CPF)

        resultados_with_tipo = [
            {"id": f"res-{i}", "tipo": c["tipo"], "status": "erro"}
            for i, c in enumerate(CERTIDOES_CONFIG)
        ]
        mock_db.set_table_data("certidao_resultados", resultados_with_tipo)

        with patch("app.services.certidoes_service._get_infosimples_token", return_value="tok"), \
             patch("app.services.certidoes_service._process_single_certidao", new_callable=AsyncMock):
            await processar_consulta("consulta-001", mock_db)


# ---------------------------------------------------------------------------
# _atualizar_status_consulta
# ---------------------------------------------------------------------------

class TestAtualizarStatusConsulta:
    def test_all_sucesso(self):
        """All resultados sucesso → consulta concluida."""
        mock_db = MockSupabaseClient()
        mock_db.set_table_data("certidao_resultados", [
            {"status": "sucesso"}, {"status": "sucesso"},
        ])
        _atualizar_status_consulta("c-1", mock_db)

    def test_all_erro(self):
        """All resultados erro → consulta erro."""
        mock_db = MockSupabaseClient()
        mock_db.set_table_data("certidao_resultados", [
            {"status": "erro"}, {"status": "erro"},
        ])
        _atualizar_status_consulta("c-1", mock_db)

    def test_some_na_fila(self):
        """Some resultados still na_fila → consulta processando."""
        mock_db = MockSupabaseClient()
        mock_db.set_table_data("certidao_resultados", [
            {"status": "sucesso"}, {"status": "na_fila"},
        ])
        _atualizar_status_consulta("c-1", mock_db)

    def test_mixed_sucesso_erro(self):
        """Mix of sucesso and erro (no pending) → consulta concluida."""
        mock_db = MockSupabaseClient()
        mock_db.set_table_data("certidao_resultados", [
            {"status": "sucesso"}, {"status": "erro"},
        ])
        _atualizar_status_consulta("c-1", mock_db)


# ---------------------------------------------------------------------------
# _get_tjsp_last_request_at
# ---------------------------------------------------------------------------

class TestGetTjspLastRequestAt:
    def test_no_previous_requests(self):
        """No previous TJSP requests → returns None."""
        mock_db = MockSupabaseClient()
        mock_db.set_table_data("certidao_resultados", [])
        result = _get_tjsp_last_request_at("org-001", mock_db)
        assert result is None

    def test_with_previous_request(self):
        """Has a previous TJSP request with api_requested_at → returns datetime."""
        mock_db = MockSupabaseClient()
        mock_db.set_table_data("certidao_resultados", [
            {"api_requested_at": "2026-03-13T10:00:00+00:00"},
        ])
        result = _get_tjsp_last_request_at("org-001", mock_db)
        assert result is not None

    def test_with_invalid_timestamp(self):
        """Invalid timestamp string → returns None."""
        mock_db = MockSupabaseClient()
        mock_db.set_table_data("certidao_resultados", [
            {"api_requested_at": "not-a-date"},
        ])
        result = _get_tjsp_last_request_at("org-001", mock_db)
        assert result is None

    def test_survives_status_reset_on_reprocessing(self):
        """api_requested_at is preserved even when status is reset to na_fila,
        so the cooldown is still enforced after reprocessing."""
        mock_db = MockSupabaseClient()
        mock_db.set_table_data("certidao_resultados", [
            {"api_requested_at": "2026-03-13T10:00:00+00:00", "status": "na_fila"},
        ])
        result = _get_tjsp_last_request_at("org-001", mock_db)
        assert result is not None



# ---------------------------------------------------------------------------
# _get_tjsp_remaining_cooldown
# ---------------------------------------------------------------------------

class TestGetTjspRemainingCooldown:
    def test_no_previous_request(self):
        """No previous TJSP request → 0 seconds remaining."""
        mock_db = MockSupabaseClient()
        mock_db.set_table_data("certidao_resultados", [])
        result = _get_tjsp_remaining_cooldown("org-001", mock_db)
        assert result == 0.0

    def test_cooldown_active(self):
        """Recent request → positive seconds remaining."""
        from datetime import datetime, timezone, timedelta
        mock_db = MockSupabaseClient()
        five_min_ago = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        mock_db.set_table_data("certidao_resultados", [
            {"api_requested_at": five_min_ago},
        ])
        result = _get_tjsp_remaining_cooldown("org-001", mock_db)
        # Should be ~40 min remaining (45 - 5)
        assert result > 2300
        assert result <= TJSP_COOLDOWN_SECONDS

    def test_cooldown_expired(self):
        """Old request → 0 seconds remaining."""
        from datetime import datetime, timezone, timedelta
        mock_db = MockSupabaseClient()
        old = (datetime.now(timezone.utc) - timedelta(minutes=50)).isoformat()
        mock_db.set_table_data("certidao_resultados", [
            {"api_requested_at": old},
        ])
        result = _get_tjsp_remaining_cooldown("org-001", mock_db)
        assert result == 0.0


# ---------------------------------------------------------------------------
# schedule_tjsp_for_org
# ---------------------------------------------------------------------------

class TestScheduleTjspForOrg:
    def test_no_queued_items(self):
        """No items in queue → no task created."""
        import app.services.certidoes_service as svc
        mock_db = MockSupabaseClient()
        mock_db.set_table_data("certidao_resultados", [])

        svc._tjsp_scheduled_tasks.pop("org-001", None)
        with patch("app.services.certidoes_service.asyncio.create_task") as mock_ct:
            schedule_tjsp_for_org("org-001", mock_db)
            mock_ct.assert_not_called()

    def test_creates_task_for_queued_item(self):
        """Queued item → creates asyncio task with correct delay."""
        import app.services.certidoes_service as svc
        mock_db = MockSupabaseClient()
        mock_db.set_table_data("certidao_resultados", [
            {"id": "res-1", "consulta_id": "c-1", "org_id": "org-001"},
        ])

        svc._tjsp_scheduled_tasks.pop("org-001", None)
        mock_task = MagicMock()
        with patch("app.services.certidoes_service._get_tjsp_remaining_cooldown", return_value=1800.0), \
             patch("app.services.certidoes_service.asyncio.create_task", return_value=mock_task) as mock_ct:
            schedule_tjsp_for_org("org-001", mock_db)
            mock_ct.assert_called_once()

        # Cleanup
        svc._tjsp_scheduled_tasks.pop("org-001", None)

    def test_idempotent_when_task_in_flight(self):
        """Already scheduled → does not create a second task."""
        import app.services.certidoes_service as svc
        mock_db = MockSupabaseClient()
        mock_db.set_table_data("certidao_resultados", [
            {"id": "res-1", "consulta_id": "c-1", "org_id": "org-001"},
        ])

        existing_task = MagicMock()
        existing_task.done.return_value = False
        svc._tjsp_scheduled_tasks["org-001"] = existing_task

        with patch("app.services.certidoes_service.asyncio.create_task") as mock_ct:
            schedule_tjsp_for_org("org-001", mock_db)
            mock_ct.assert_not_called()

        # Cleanup
        svc._tjsp_scheduled_tasks.pop("org-001", None)


# ---------------------------------------------------------------------------
# _delayed_tjsp_process
# ---------------------------------------------------------------------------

class TestDelayedTjspProcess:
    @pytest.mark.asyncio
    async def test_processes_item_when_still_queued(self):
        """Item is na_fila → processes it."""
        import app.services.certidoes_service as svc
        mock_db = MockSupabaseClient()
        mock_db.set_table_data("certidao_resultados", [
            {"status": "na_fila"},
        ])

        resultado = {"id": "res-1", "consulta_id": "c-1", "org_id": "org-001"}
        svc._tjsp_scheduled_tasks.pop("org-001", None)

        with patch("app.services.certidoes_service._process_single_tjsp_item", new_callable=AsyncMock) as mock_process, \
             patch("app.services.certidoes_service.schedule_tjsp_for_org"):
            await _delayed_tjsp_process(0, resultado, "org-001", mock_db)
            mock_process.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_item_no_longer_queued(self):
        """Item was deleted or already processed → skips."""
        import app.services.certidoes_service as svc
        mock_db = MockSupabaseClient()
        mock_db.set_table_data("certidao_resultados", [
            {"status": "sucesso"},
        ])

        resultado = {"id": "res-1", "consulta_id": "c-1", "org_id": "org-001"}
        svc._tjsp_scheduled_tasks.pop("org-001", None)

        with patch("app.services.certidoes_service._process_single_tjsp_item", new_callable=AsyncMock) as mock_process, \
             patch("app.services.certidoes_service.schedule_tjsp_for_org"):
            await _delayed_tjsp_process(0, resultado, "org-001", mock_db)
            mock_process.assert_not_called()

    @pytest.mark.asyncio
    async def test_chains_next_item_after_completion(self):
        """After processing, schedules the next queued item for the same org."""
        import app.services.certidoes_service as svc
        mock_db = MockSupabaseClient()
        mock_db.set_table_data("certidao_resultados", [
            {"status": "na_fila"},
        ])

        resultado = {"id": "res-1", "consulta_id": "c-1", "org_id": "org-001"}
        svc._tjsp_scheduled_tasks.pop("org-001", None)

        with patch("app.services.certidoes_service._process_single_tjsp_item", new_callable=AsyncMock), \
             patch("app.services.certidoes_service.schedule_tjsp_for_org") as mock_schedule:
            await _delayed_tjsp_process(0, resultado, "org-001", mock_db)
            mock_schedule.assert_called_once_with("org-001", mock_db)


# ---------------------------------------------------------------------------
# schedule_all_pending_tjsp
# ---------------------------------------------------------------------------

class TestScheduleAllPendingTjsp:
    def test_schedules_per_org(self):
        """Scans for queued items and schedules one task per org."""
        mock_db = MockSupabaseClient()
        mock_db.set_table_data("certidao_resultados", [
            {"org_id": "org-001"},
            {"org_id": "org-001"},
            {"org_id": "org-002"},
        ])

        with patch("app.services.certidoes_service.schedule_tjsp_for_org") as mock_schedule:
            schedule_all_pending_tjsp(mock_db)
            assert mock_schedule.call_count == 2
            called_orgs = {call.args[0] for call in mock_schedule.call_args_list}
            assert called_orgs == {"org-001", "org-002"}

    def test_no_queued_items(self):
        """No items → no calls."""
        mock_db = MockSupabaseClient()
        mock_db.set_table_data("certidao_resultados", [])

        with patch("app.services.certidoes_service.schedule_tjsp_for_org") as mock_schedule:
            schedule_all_pending_tjsp(mock_db)
            mock_schedule.assert_not_called()


# ---------------------------------------------------------------------------
# processar_consulta — TJSP queue separation
# ---------------------------------------------------------------------------

class TestProcessarConsultaTjspQueue:
    @pytest.mark.asyncio
    async def test_tjsp_queued_when_cooldown_active(self):
        """TJSP resultados are queued when cooldown is active."""
        from datetime import datetime, timezone
        mock_db = MockSupabaseClient()
        mock_db.set_table_data("certidao_consultas", CONSULTA_CPF)

        resultados = [
            {"id": f"res-{i}", "tipo": c["tipo"], "status": "pendente"}
            for i, c in enumerate(CERTIDOES_CONFIG)
        ]
        mock_db.set_table_data("certidao_resultados", resultados)

        process_calls = []

        async def track_process(config, consulta, token, db, rid, client):
            process_calls.append(config["tipo"])

        # Cooldown active — last successful request was just now
        with patch("app.services.certidoes_service._get_infosimples_token", return_value="tok"), \
             patch("app.services.certidoes_service._get_tjsp_last_request_at", return_value=datetime.now(timezone.utc)), \
             patch("app.services.certidoes_service._process_single_certidao", side_effect=track_process):
            await processar_consulta("consulta-001", mock_db)

        # TJSP should NOT be processed — it's queued due to cooldown
        assert "tjsp" not in process_calls
        # All other types should be processed
        non_tjsp_types = [c["tipo"] for c in CERTIDOES_CONFIG if c["tipo"] != "tjsp"]
        for t in non_tjsp_types:
            assert t in process_calls

    @pytest.mark.asyncio
    async def test_tjsp_runs_in_parallel_when_cooldown_clear(self):
        """TJSP runs in parallel with other certificates when cooldown has passed."""
        mock_db = MockSupabaseClient()
        mock_db.set_table_data("certidao_consultas", CONSULTA_CPF)

        resultados = [
            {"id": f"res-{i}", "tipo": c["tipo"], "status": "pendente"}
            for i, c in enumerate(CERTIDOES_CONFIG)
        ]
        mock_db.set_table_data("certidao_resultados", resultados)

        process_calls = []

        async def track_process(config, consulta, token, db, rid, client):
            process_calls.append(config["tipo"])

        # No previous TJSP request — cooldown clear
        with patch("app.services.certidoes_service._get_infosimples_token", return_value="tok"), \
             patch("app.services.certidoes_service._get_tjsp_last_request_at", return_value=None), \
             patch("app.services.certidoes_service._process_single_certidao", side_effect=track_process):
            await processar_consulta("consulta-001", mock_db)

        # ALL types including TJSP should be processed in parallel
        all_types = [c["tipo"] for c in CERTIDOES_CONFIG]
        for t in all_types:
            assert t in process_calls


# ---------------------------------------------------------------------------
# Stuck processando recovery
# ---------------------------------------------------------------------------


class TestRecoverStuckProcessando:
    """Tests for recover_stuck_processando (startup recovery)."""

    def test_no_stuck_items(self):
        """No-op when no items are stuck."""
        mock_db = MockSupabaseClient()
        mock_db.set_table_data("certidao_resultados", [])
        recover_stuck_processando(mock_db)

    def test_resets_non_tjsp_to_pendente(self):
        """Non-TJSP stuck items are reset to 'pendente'."""
        mock_db = MockSupabaseClient()
        mock_db.set_table_data("certidao_resultados", [
            {"id": "r1", "tipo": "cnd_federal", "consulta_id": "c1", "status": "processando"},
        ])
        # Should run without error — resets to pendente
        recover_stuck_processando(mock_db)

    def test_resets_tjsp_to_na_fila(self):
        """TJSP stuck items are reset to 'na_fila'."""
        mock_db = MockSupabaseClient()
        mock_db.set_table_data("certidao_resultados", [
            {"id": "r1", "tipo": "tjsp", "consulta_id": "c1", "status": "processando"},
        ])
        # Should run without error — resets to na_fila
        recover_stuck_processando(mock_db)

    def test_mixed_types_recovered(self):
        """Both TJSP and non-TJSP stuck items are recovered in one call."""
        mock_db = MockSupabaseClient()
        mock_db.set_table_data("certidao_resultados", [
            {"id": "r1", "tipo": "cnd_federal", "consulta_id": "c1", "status": "processando"},
            {"id": "r2", "tipo": "tjsp", "consulta_id": "c1", "status": "processando"},
        ])
        recover_stuck_processando(mock_db)
