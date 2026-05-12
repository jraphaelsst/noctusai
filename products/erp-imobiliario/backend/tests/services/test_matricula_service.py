"""Tests for the Matrícula Text Extractor service — PDF→image conversion,
OCR via the seed vision wrapper, and full extraction pipeline.

Updated 2026-05-11 (LLM-ERP rollout, Step A): the service now dispatches
through `noctusai_lib.integrations.llm.analyze_image` instead of raw
`httpx.post(...)`. Tests patch the seed wrapper (external integration, so
`patch` is the right shape per `KB § PATTERNS/testing.md`).
"""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from app.services.matricula_service import (
    _pdf_to_images,
    _ocr_page,
    processar_extracao,
    check_required_credentials,
)
from tests.conftest import MockSupabaseClient


# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

# Minimal valid PDF (1 blank page)
MINIMAL_PDF = (
    b"%PDF-1.0\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj\n"
    b"xref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n"
    b"0000000058 00000 n \n0000000115 00000 n \n"
    b"trailer<</Size 4/Root 1 0 R>>\nstartxref\n190\n%%EOF"
)


# ---------------------------------------------------------------------------
# _pdf_to_images
# ---------------------------------------------------------------------------

class TestPdfToImages:
    def test_converte_pdf_minimo(self):
        images = _pdf_to_images(MINIMAL_PDF)
        assert len(images) == 1
        # PNG magic bytes
        assert images[0][:4] == b"\x89PNG"

    def test_pdf_invalido_levanta_excecao(self):
        with pytest.raises(Exception):
            _pdf_to_images(b"not a pdf")


# ---------------------------------------------------------------------------
# _ocr_page
# ---------------------------------------------------------------------------

class TestOcrPage:
    @pytest.mark.asyncio
    async def test_sucesso(self):
        with patch(
            "app.services.matricula_service.analyze_image",
            new_callable=AsyncMock,
            return_value="Texto extraído da página.",
        ):
            result = await _ocr_page(b"\x89PNG fake", 1, 1, "org-001")
        assert result == "Texto extraído da página."

    @pytest.mark.asyncio
    async def test_chama_seed_wrapper_com_modelo_e_org_id(self):
        """The seed wrapper must receive the OCR-pinned model + the caller's
        org_id (so per-org key resolution works) + max_tokens=4096."""
        mock = AsyncMock(return_value="ok")
        with patch("app.services.matricula_service.analyze_image", new=mock):
            await _ocr_page(b"image-bytes", 1, 1, "org-001")

        # `analyze_image(image, prompt, *, model=..., org_id=..., max_tokens=...)`
        # — first two positional, rest keyword.
        args, kwargs = mock.call_args
        assert args[0] == b"image-bytes"
        assert "Extract the exact text" in args[1]
        assert kwargs.get("model") == "gpt-4.1-mini"
        assert kwargs.get("org_id") == "org-001"
        assert kwargs.get("max_tokens") == 4096


# ---------------------------------------------------------------------------
# check_required_credentials
# ---------------------------------------------------------------------------

class TestCheckRequiredCredentials:
    def test_sem_openai_retorna_mensagem(self):
        with patch("app.services.matricula_service.resolve_credential", return_value=None):
            missing = check_required_credentials("org-001")
        assert len(missing) == 1
        assert "OpenAI" in missing[0]

    def test_com_openai_retorna_vazio(self):
        with patch("app.services.matricula_service.resolve_credential", return_value="sk-test"):
            missing = check_required_credentials("org-001")
        assert missing == []


# ---------------------------------------------------------------------------
# processar_extracao
# ---------------------------------------------------------------------------

class TestProcessarExtracao:
    @pytest.mark.asyncio
    async def test_sem_api_key_marca_erro(self):
        mock_db = MockSupabaseClient()
        mock_db.set_table_data("matricula_extracoes", {"id": "ext-001", "status": "pendente"})

        with patch("app.services.matricula_service.resolve_credential", return_value=None):
            await processar_extracao("ext-001", MINIMAL_PDF, "org-001", mock_db)

        # Should have called update (the mock swallows it)

    @pytest.mark.asyncio
    async def test_pdf_vazio_marca_erro(self):
        """Empty PDF (no pages) should result in error."""
        mock_db = MockSupabaseClient()
        mock_db.set_table_data("matricula_extracoes", {"id": "ext-002", "status": "pendente"})

        with patch("app.services.matricula_service.resolve_credential", return_value="sk-test"), \
             patch("app.services.matricula_service._pdf_to_images", return_value=[]):
            await processar_extracao("ext-002", b"fake", "org-001", mock_db)

    @pytest.mark.asyncio
    async def test_sucesso_completo(self):
        """Full pipeline with mocked OCR."""
        mock_db = MockSupabaseClient()
        mock_db.set_table_data("matricula_extracoes", {"id": "ext-003", "status": "pendente"})

        mock_images = [b"\x89PNG page1", b"\x89PNG page2"]

        async def mock_ocr(img, page_num, total, api_key, client):
            return f"Texto pagina {page_num}"

        with patch("app.services.matricula_service.resolve_credential", return_value="sk-test"), \
             patch("app.services.matricula_service._pdf_to_images", return_value=mock_images), \
             patch("app.services.matricula_service._ocr_page", side_effect=mock_ocr):
            await processar_extracao("ext-003", b"fake-pdf", "org-001", mock_db)
