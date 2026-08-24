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



# ---------------------------------------------------------------------------
# Rung 1 — the PDF's own text layer
# ---------------------------------------------------------------------------

from app.services import matricula_service  # noqa: E402


class _RecordingDB:
    """Records what the service wrote, which MockSupabaseClient swallows.

    These tests are about the OUTCOME written to the row, so the double has
    to keep it.
    """

    def __init__(self):
        self.updates: list[dict] = []

    def table(self, _name):
        return self

    def update(self, payload):
        self.updates.append(payload)
        return self

    def eq(self, _col, _val):
        return self

    def execute(self):
        return MagicMock(data=[])

    @property
    def last(self) -> dict:
        return self.updates[-1]


class TestTextLayerRung:
    """🔴 The rung that was missing until 2026-08-24.

    Every one of these is about NOT calling vision. A digitally-issued
    matrícula carries exact, machine-readable text; rasterizing it and asking
    a model to read the picture costs money to produce a worse answer.
    """

    @pytest.mark.asyncio
    async def test_a_pdf_with_a_text_layer_never_reaches_vision(self):
        db = _RecordingDB()
        rendered: list[int] = []

        with patch.object(matricula_service, "_contar_paginas", return_value=2), \
             patch.object(
                 matricula_service, "_pdf_to_images",
                 side_effect=lambda _b: (rendered.append(1), [b"png"])[1],
             ), \
             patch("noctusai_lib.integrations.media.extract_pdf_text",
                   return_value="X" * 500):
            await matricula_service.processar_extracao("e1", b"%PDF", None, db)

        assert rendered == [], "rasterized a PDF that already had a text layer"
        assert db.last["status"] == "concluida"
        assert db.last["texto_extraido"] == "X" * 500
        assert db.last["num_paginas"] == 2

    @pytest.mark.asyncio
    async def test_it_works_with_no_openai_key_configured(self):
        """The reason rung 1 runs BEFORE the credential check.

        An org that has never configured OpenAI can still extract a
        digitally-issued matrícula. Checking the key first would refuse work
        we are entirely able to do.
        """
        db = _RecordingDB()
        with patch.object(matricula_service, "_contar_paginas", return_value=1), \
             patch.object(matricula_service, "resolve_credential", return_value=None), \
             patch("noctusai_lib.integrations.media.extract_pdf_text",
                   return_value="Y" * 400):
            await matricula_service.processar_extracao("e2", b"%PDF", None, db)

        assert db.last["status"] == "concluida"

    def test_a_scan_with_a_smudge_of_text_still_goes_to_vision(self):
        """A stamp or a signature footer is not a text layer.

        Accepting it would return a few dozen characters of junk as the whole
        matrícula — a silent, total data loss that looks like success.
        """
        with patch("noctusai_lib.integrations.media.extract_pdf_text",
                   return_value="Assinado digitalmente"):
            assert matricula_service._texto_da_camada(b"%PDF", 3) is None

    def test_a_real_text_layer_clears_the_bar(self):
        with patch("noctusai_lib.integrations.media.extract_pdf_text",
                   return_value="A" * 4000):
            assert matricula_service._texto_da_camada(b"%PDF", 3) == "A" * 4000

    def test_a_text_layer_failure_falls_through_rather_than_erroring(self):
        """Rung 1 is an optimisation. It must never fail an extraction that
        rung 2 could have completed."""
        with patch("noctusai_lib.integrations.media.extract_pdf_text",
                   side_effect=RuntimeError("mupdf exploded")):
            assert matricula_service._texto_da_camada(b"%PDF", 1) is None

    def test_zero_pages_is_not_a_text_layer(self):
        assert matricula_service._texto_da_camada(b"%PDF", 0) is None

    def test_corrupt_bytes_count_as_zero_pages_rather_than_raising(self):
        assert matricula_service._contar_paginas(b"not a pdf at all") == 0

    @pytest.mark.asyncio
    async def test_a_corrupt_upload_gets_the_actionable_message(self):
        db = _RecordingDB()
        await matricula_service.processar_extracao("e3", b"not a pdf", None, db)
        assert db.last["status"] == "erro"
        assert "sem páginas" in db.last["erro_mensagem"]
