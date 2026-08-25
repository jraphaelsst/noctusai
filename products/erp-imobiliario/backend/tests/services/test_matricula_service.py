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
        assert set(images) == {1}, "keyed by 1-based page number, not list index"
        # PNG magic bytes
        assert images[1][:4] == b"\x89PNG"

    def test_pdf_invalido_levanta_excecao(self):
        with pytest.raises(Exception):
            _pdf_to_images(b"not a pdf")

    def test_renders_only_the_requested_pages(self):
        """Rasterizing a page we already read for free is wasted CPU, and
        once it reaches `_ocr_page` it is wasted money."""
        assert _pdf_to_images(MINIMAL_PDF, []) == {}
        assert set(_pdf_to_images(MINIMAL_PDF, [1])) == {1}


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


def _camada(*paginas):
    """Build a `PdfTextLayer` from (text, is_substantive) pairs."""
    from noctusai_lib.integrations.media import PdfPage, PdfTextLayer

    return PdfTextLayer(
        pages=tuple(
            PdfPage(number=i, text=t, is_substantive=sub, reason="test")
            for i, (t, sub) in enumerate(paginas, 1)
        ),
        tooling_available=True,
    )


class TestTextLayerRung:
    """🔴 The rung that was missing until 2026-08-24.

    Every one of these is about NOT calling vision. A digitally-issued
    matrícula carries exact, machine-readable text; rasterizing it and asking
    a model to read the picture costs money to produce a worse answer.

    The mirror-image failure — trusting a text layer that is only a
    signature stamp — is `TestScannedDocumentsReachVision` below.
    """

    @pytest.mark.asyncio
    async def test_a_pdf_with_a_text_layer_never_reaches_vision(self):
        db = _RecordingDB()
        rendered: list[int] = []

        with patch.object(matricula_service, "_contar_paginas", return_value=2), \
             patch.object(
                 matricula_service, "_pdf_to_images",
                 side_effect=lambda *a, **k: (rendered.append(1), {1: b"png"})[1],
             ), \
             patch.object(
                 matricula_service, "classify_pdf_text_layer",
                 return_value=_camada(("X" * 250, True), ("X" * 249, True)),
             ):
            await matricula_service.processar_extracao("e1", b"%PDF", None, db)

        assert rendered == [], "rasterized a PDF that already had a text layer"
        assert db.last["status"] == "concluida"
        assert db.last["texto_extraido"] == "X" * 250 + "\n" + "X" * 249
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
             patch.object(
                 matricula_service, "classify_pdf_text_layer",
                 return_value=_camada(("Y" * 400, True)),
             ):
            await matricula_service.processar_extracao("e2", b"%PDF", None, db)

        assert db.last["status"] == "concluida"

    def test_zero_pages_is_not_a_text_layer(self):
        assert matricula_service._contar_paginas(b"") == 0

    def test_corrupt_bytes_count_as_zero_pages_rather_than_raising(self):
        assert matricula_service._contar_paginas(b"not a pdf at all") == 0


class TestScannedDocumentsReachVision:
    """The 2026-08-25 defect: a CERTIDÃO DE MATRÍCULA transcribed as nothing
    but its own validation stamp.

    A cartório scan is a page-sized JPEG with an ONR digital-signature stamp
    overlaid as REAL, selectable text — 137 characters per page, which
    cleared the old `>= 100 chars/page` bar. The extraction reported
    "concluida" and returned three copies of "Valide este documento clicando
    no link a seguir: ..." while the matrícula itself never left the JPEG.
    Total data loss wearing a success badge.
    """

    ONR_STAMP = (
        "Valide este documento clicando no link a seguir: "
        "https://assinador-web.onr.org.br/docs/7JX9U-HLZEA-9LJWT-PM2QS\n"
        "Valide aqui\neste documento"
    )

    @pytest.mark.asyncio
    async def test_a_signature_stamp_is_not_a_transcription(self):
        db = _RecordingDB()
        with patch.object(matricula_service, "_contar_paginas", return_value=3), \
             patch.object(matricula_service, "resolve_credential", return_value="sk-x"), \
             patch.object(
                 matricula_service, "classify_pdf_text_layer",
                 return_value=_camada(*[(self.ONR_STAMP, False)] * 3),
             ), \
             patch.object(
                 matricula_service, "_pdf_to_images",
                 side_effect=lambda _b, paginas=None: {n: b"png" for n in paginas},
             ), \
             patch.object(
                 matricula_service, "_ocr_page",
                 new=AsyncMock(side_effect=lambda _i, n, *a: f"CONTEUDO PAGINA {n}"),
             ):
            await matricula_service.processar_extracao("e4", b"%PDF", None, db)

        assert db.last["status"] == "concluida"
        texto = db.last["texto_extraido"]
        assert "assinador-web.onr.org.br" not in texto, (
            "returned the validation stamp instead of the matrícula"
        )
        assert texto == (
            "CONTEUDO PAGINA 1\n\nCONTEUDO PAGINA 2\n\nCONTEUDO PAGINA 3"
        )

    @pytest.mark.asyncio
    async def test_a_mixed_document_pays_for_vision_only_where_needed(self):
        """A typeset body with a scanned averbação stapled on is ordinary in
        Brazil. Whole-document routing has to pick one rung for both halves."""
        db = _RecordingDB()
        ocr_calls: list[int] = []

        with patch.object(matricula_service, "_contar_paginas", return_value=3), \
             patch.object(matricula_service, "resolve_credential", return_value="sk-x"), \
             patch.object(
                 matricula_service, "classify_pdf_text_layer",
                 return_value=_camada(
                     ("CORPO TIPOGRAFADO", True),
                     (self.ONR_STAMP, False),
                     ("FECHAMENTO TIPOGRAFADO", True),
                 ),
             ), \
             patch.object(
                 matricula_service, "_pdf_to_images",
                 side_effect=lambda _b, paginas=None: {n: b"png" for n in paginas},
             ), \
             patch.object(
                 matricula_service, "_ocr_page",
                 new=AsyncMock(
                     side_effect=lambda _i, n, *a: (
                         ocr_calls.append(n), "AVERBACAO ESCANEADA"
                     )[1]
                 ),
             ):
            await matricula_service.processar_extracao("e5", b"%PDF", None, db)

        assert ocr_calls == [2], "paid for vision on pages it could read for free"
        assert db.last["texto_extraido"] == (
            "CORPO TIPOGRAFADO\n\nAVERBACAO ESCANEADA\n\nFECHAMENTO TIPOGRAFADO"
        ), "pages must reassemble in document order"

    @pytest.mark.asyncio
    async def test_a_dropped_page_fails_loudly_rather_than_shipping_short(self):
        """A matrícula missing a page must never reach status 'concluida'."""
        db = _RecordingDB()
        with patch.object(matricula_service, "_contar_paginas", return_value=2), \
             patch.object(matricula_service, "resolve_credential", return_value="sk-x"), \
             patch.object(
                 matricula_service, "classify_pdf_text_layer",
                 return_value=_camada((self.ONR_STAMP, False), (self.ONR_STAMP, False)),
             ), \
             patch.object(
                 matricula_service, "_pdf_to_images", return_value={1: b"png"}
             ), \
             patch.object(
                 matricula_service, "_ocr_page", new=AsyncMock(return_value="pagina 1")
             ):
            await matricula_service.processar_extracao("e6", b"%PDF", None, db)

        assert db.last["status"] == "erro"
        assert "rasterizar a página 2" in db.last["erro_mensagem"]

    @pytest.mark.asyncio
    async def test_degraded_classification_sends_every_page_to_vision(self):
        """Without PyMuPDF the seed cannot classify per page and returns one
        synthetic page. Mixing that with page-scoped OCR would attribute the
        whole document's text to page 1, so we take nothing for free."""
        from noctusai_lib.integrations.media import PdfPage, PdfTextLayer

        db = _RecordingDB()
        ocr_calls: list[int] = []
        degraded = PdfTextLayer(
            pages=(PdfPage(number=1, text="stamp", is_substantive=False, reason="x"),),
            tooling_available=True,
        )

        with patch.object(matricula_service, "_contar_paginas", return_value=4), \
             patch.object(matricula_service, "resolve_credential", return_value="sk-x"), \
             patch.object(
                 matricula_service, "classify_pdf_text_layer", return_value=degraded
             ), \
             patch.object(
                 matricula_service, "_pdf_to_images",
                 side_effect=lambda _b, paginas=None: {n: b"png" for n in paginas},
             ), \
             patch.object(
                 matricula_service, "_ocr_page",
                 new=AsyncMock(
                     side_effect=lambda _i, n, *a: (ocr_calls.append(n), "p")[1]
                 ),
             ):
            await matricula_service.processar_extracao("e7", b"%PDF", None, db)

        assert ocr_calls == [1, 2, 3, 4]


class TestCorruptUpload:
    @pytest.mark.asyncio
    async def test_a_corrupt_upload_gets_the_actionable_message(self):
        db = _RecordingDB()
        await matricula_service.processar_extracao("e3", b"not a pdf", None, db)
        assert db.last["status"] == "erro"
        assert "sem páginas" in db.last["erro_mensagem"]
