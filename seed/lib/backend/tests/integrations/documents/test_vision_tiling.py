"""`documents.vision_tiling` + the native-resolution vision path of
`documents.transcription` (2026-10-13).

The page used to be stepped DOWN in DPI until it fit a byte budget, and was
then downscaled AGAIN by the vendor to the model's native resolution. These
tests lock in the replacement: pre-fit to the published native resolution,
band a dense full page (ordered, overlapping, one request), encode JPEG/PNG
by size under the byte budget, and never degrade silently
(`resolucao_reduzida`). Real PDFs built with PyMuPDF — no PDF mechanics
mocked, no network.
"""
from __future__ import annotations

import logging

import pytest

fitz = pytest.importorskip("fitz")

from noctusai_lib.integrations.documents import releitura  # noqa: E402
from noctusai_lib.integrations.documents.ladder import LeituraTexto  # noqa: E402
from noctusai_lib.integrations.documents.real import LadderIdentityExtractor  # noqa: E402
from noctusai_lib.integrations.documents.transcription import (  # noqa: E402
    FULL_PAGE_MAX_BANDS,
    OCR_BANDS_PROMPT_SUFFIX,
    LadderDocumentTranscriber,
    RenderDpiPolicy,
    full_page_document_render_dpi_policy,
    identity_document_render_dpi_policy,
    render_dpi_policy_for,
)
from noctusai_lib.integrations.documents.types import IdentityFields, TextSource  # noqa: E402
from noctusai_lib.integrations.documents.vision_tiling import (  # noqa: E402
    AVISO_RESOLUCAO_REDUZIDA,
    VisionResolution,
    encode_for_vision,
    encoded_size,
    plan_bands,
    render_page_for_vision,
    vision_resolution_for,
)

HIGH = VisionResolution(2576, 4784)
STANDARD = VisionResolution(1568, 1568)


# ── fixtures: real PDFs ──────────────────────────────────────────────────


def _pdf_texto_denso(largura: float = 595, altura: float = 842) -> bytes:
    """A vector page of dense small print, with a solid black bar at the
    very top (so a test can tell the TOP band from the others)."""
    doc = fitz.open()
    page = doc.new_page(width=largura, height=altura)
    page.draw_rect(fitz.Rect(0, 0, largura, 20), color=(0, 0, 0), fill=(0, 0, 0))
    y = 40
    i = 0
    while y < altura - 20:
        page.insert_text(
            (30, y),
            f"AVERBACAO {i}: LIVRO B-0031 FOLHAS 074 TERMO 9077 CPF 758.834.498-91",
            fontsize=7,
        )
        y += 9
        i += 1
    data = doc.tobytes()
    doc.close()
    return data


def _foto(px_w: int, px_h: int) -> bytes:
    """A photographic-looking JPEG (smooth gradients + noise)."""
    import random

    rnd = random.Random(7)
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, px_w, px_h), False)
    amostras = bytearray(px_w * px_h * 3)
    for y in range(px_h):
        for x in range(px_w):
            k = (y * px_w + x) * 3
            amostras[k] = (x * 255 // px_w + rnd.randint(0, 40)) % 256
            amostras[k + 1] = (y * 255 // px_h + rnd.randint(0, 40)) % 256
            amostras[k + 2] = rnd.randint(90, 160)
    pix = fitz.Pixmap(fitz.csRGB, px_w, px_h, bytes(amostras), False)
    return pix.tobytes("jpg", jpg_quality=90)


def _pdf_scan(px_w: int, px_h: int, *, pagina=(595, 842), rect=None) -> bytes:
    """A page that IS a scan: one embedded photo, no text layer."""
    doc = fitz.open()
    page = doc.new_page(width=pagina[0], height=pagina[1])
    page.insert_image(rect or page.rect, stream=_foto(px_w, px_h))
    data = doc.tobytes()
    doc.close()
    return data


class _Vision:
    """Records each call: the image argument (bytes, or a list of bands)
    and the prompt."""

    def __init__(self) -> None:
        self.calls: list[tuple[object, str]] = []

    async def __call__(self, image, prompt, **kwargs):
        self.calls.append((image, prompt))
        return f"OCR CHAMADA {len(self.calls)}"


# ── VisionResolution: Anthropic's published resize rule ──────────────────


class TestFitSizeMatchesThePublishedRule:
    """Every example from the vision / vision-coordinates guides."""

    def test_standard_tier_a4_scan_example(self) -> None:
        assert STANDARD.fit_size(1075, 1520) == (924, 1307)

    def test_standard_tier_1080p(self) -> None:
        assert STANDARD.fit_size(1920, 1080) == (1456, 819)

    def test_high_res_tier_1080p_is_not_resized(self) -> None:
        assert HIGH.fit_size(1920, 1080) == (1920, 1080)

    def test_high_res_tier_4k(self) -> None:
        assert HIGH.fit_size(3840, 2160) == (2576, 1449)

    def test_visual_tokens_is_patch_count(self) -> None:
        assert VisionResolution.visual_tokens(1000, 1000) == 1296
        assert VisionResolution.visual_tokens(2000, 1500) == 3888


class TestCatalogResolution:
    @pytest.mark.parametrize(
        "model", ["claude-sonnet-5", "claude-opus-5-5", "claude-fable-5-1"]
    )
    def test_pinned_document_models_are_high_resolution(self, model) -> None:
        assert vision_resolution_for("anthropic", model) == HIGH

    def test_pre_4_7_model_is_standard_tier(self) -> None:
        assert vision_resolution_for("anthropic", "claude-haiku-4-5") == STANDARD

    def test_unpublished_vendor_resolution_is_none(self) -> None:
        assert vision_resolution_for("openai", "gpt-4o") is None

    def test_a_price_override_keeps_the_resolution(self) -> None:
        from noctusai_lib.integrations.llm.catalog_overrides import (
            ModelOverride,
            clear_model_overrides,
            set_model_overrides,
        )

        try:
            set_model_overrides([
                ModelOverride(
                    provider="anthropic", kind="vision", model_id="claude-sonnet-5",
                    cost_per_1m_input_tokens=9.0, cost_per_1m_output_tokens=9.0,
                )
            ])
            assert vision_resolution_for("anthropic", "claude-sonnet-5") == HIGH
        finally:
            clear_model_overrides()


# ── plan_bands ───────────────────────────────────────────────────────────


class TestPlanBands:
    def test_a4_at_300_dpi_becomes_ordered_overlapping_native_bands(self) -> None:
        plano = plan_bands(2481, 3508, HIGH, max_bands=4, overlap=0.08)

        assert len(plano.bands) == 3
        assert plano.bands[0][0] == 0
        assert plano.bands[-1][1] == plano.height
        for y0, y1 in plano.bands:
            assert HIGH.fits(plano.width, y1 - y0)
        for (a0, a1), (b0, b1) in zip(plano.bands, plano.bands[1:]):
            assert a0 < b0  # strictly top to bottom
            assert a1 - b0 >= 0.08 * (a1 - a0)  # overlap honoured
        # Full width kept — nothing downscaled at 300 DPI on A4.
        assert plano.scale == pytest.approx(1.0)

    def test_single_band_when_max_bands_is_one_is_the_vendor_fit(self) -> None:
        plano = plan_bands(3024, 4032, HIGH, max_bands=1, overlap=0.08)
        assert plano.bands == ((0, plano.height),)
        assert (plano.width, plano.height) == HIGH.fit_size(3024, 4032)

    def test_a_page_that_already_fits_is_not_split(self) -> None:
        plano = plan_bands(1200, 1600, HIGH, max_bands=4, overlap=0.08)
        assert plano.bands == ((0, 1600),) and plano.scale == 1.0

    def test_wider_than_the_edge_limit_is_capped_to_it(self) -> None:
        plano = plan_bands(3307, 4677, HIGH, max_bands=4, overlap=0.08)
        assert plano.width <= 2576
        assert all(HIGH.fits(plano.width, y1 - y0) for y0, y1 in plano.bands)

    def test_too_tall_for_max_bands_scales_down_and_still_covers(self) -> None:
        plano = plan_bands(2481, 25000, HIGH, max_bands=2, overlap=0.08)
        assert len(plano.bands) <= 2
        assert plano.scale < 1.0
        assert plano.bands[0][0] == 0 and plano.bands[-1][1] == plano.height
        assert all(HIGH.fits(plano.width, y1 - y0) for y0, y1 in plano.bands)


# ── encode_for_vision ────────────────────────────────────────────────────


class TestEncodeForVision:
    def test_photographic_content_is_jpeg(self) -> None:
        pix = fitz.Pixmap(_foto(400, 300))
        enc = encode_for_vision(pix, 5_000_000)
        assert enc is not None and enc.fmt == "jpeg" and enc.quality == 90
        assert enc.data[:2] == b"\xff\xd8"

    def test_bilevel_text_render_is_png_when_smaller(self) -> None:
        doc = fitz.open(stream=_pdf_texto_denso(), filetype="pdf")
        pix = doc[0].get_pixmap(matrix=fitz.Matrix(300 / 72, 300 / 72))
        enc = encode_for_vision(pix, 5_000_000)
        assert enc is not None
        assert enc.fmt == "png"
        assert len(enc.data) < len(pix.tobytes("jpg", jpg_quality=90))

    def test_byte_budget_steps_jpeg_quality_down_before_anything_else(self) -> None:
        pix = fitz.Pixmap(_foto(600, 450))
        q90 = encoded_size(pix.tobytes("jpg", jpg_quality=90))
        q82 = encoded_size(pix.tobytes("jpg", jpg_quality=82))
        enc = encode_for_vision(pix, (q90 + q82) // 2)
        assert enc is not None and enc.quality == 82
        assert encoded_size(enc.data) <= (q90 + q82) // 2

    def test_nothing_fits_returns_none(self) -> None:
        assert encode_for_vision(fitz.Pixmap(_foto(200, 200)), 10) is None


# ── render_page_for_vision ───────────────────────────────────────────────


class TestRenderPageForVision:
    def _page(self, data: bytes):
        return fitz.open(stream=data, filetype="pdf")[0]

    def test_dense_a4_page_is_three_bands_top_band_first(self) -> None:
        page = self._page(_pdf_texto_denso())
        plano = render_page_for_vision(
            page, None, target_dpi=300, min_dpi=200, native_dpi=None,
            resolution=HIGH, max_bands=4, overlap=0.08, max_encoded_bytes=5_242_880,
        )
        assert plano is not None
        assert len(plano.images) == 3
        assert not plano.resolucao_reduzida
        for img in plano.images:
            px = fitz.Pixmap(img)
            assert HIGH.fits(px.width, px.height)
            assert encoded_size(img) <= 5_242_880

        def escuro_no_topo(img: bytes) -> bool:
            px = fitz.Pixmap(img)
            return px.pixel(px.width // 2, 5)[0] < 60

        assert escuro_no_topo(plano.images[0])  # the black bar is in band 1
        assert not any(escuro_no_topo(i) for i in plano.images[1:])

    def test_floor_breach_is_marked_and_never_silent(self) -> None:
        page = self._page(_pdf_texto_denso(altura=6000))
        plano = render_page_for_vision(
            page, None, target_dpi=300, min_dpi=200, native_dpi=None,
            resolution=HIGH, max_bands=2, overlap=0.08, max_encoded_bytes=5_242_880,
        )
        assert plano is not None
        assert plano.resolucao_reduzida
        assert plano.delivered_dpi < 200

    def test_coarse_scan_at_its_own_native_density_is_not_reduced(self) -> None:
        page = self._page(_pdf_scan(300, 400))  # ~36 DPI on A4
        plano = render_page_for_vision(
            page, None, target_dpi=72, min_dpi=200, native_dpi=36.3,
            resolution=HIGH, max_bands=4, overlap=0.08, max_encoded_bytes=5_242_880,
        )
        assert plano is not None and not plano.resolucao_reduzida
        assert len(plano.images) == 1


# ── the transcriber, end to end over a real PDF ──────────────────────────


class TestTranscriberNativePath:
    @pytest.mark.asyncio
    async def test_full_page_policy_sends_ordered_bands_in_one_call(self) -> None:
        vision = _Vision()
        t = LadderDocumentTranscriber(
            analyze=vision, render_dpi_policy=full_page_document_render_dpi_policy()
        )
        result = await t.transcribe(_pdf_texto_denso(), force_vision=True)

        assert result.ok and result.avisos == ()
        assert len(vision.calls) == 1  # ONE request for the page
        imagem, prompt = vision.calls[0]
        assert isinstance(imagem, list) and len(imagem) == 3
        assert OCR_BANDS_PROMPT_SUFFIX.format(n=3) in prompt
        assert result.pages[0].text == "OCR CHAMADA 1"
        assert result.pages[0].resolucao_reduzida is False

    @pytest.mark.asyncio
    async def test_card_policy_sends_one_native_image(self) -> None:
        vision = _Vision()
        t = LadderDocumentTranscriber(
            analyze=vision, render_dpi_policy=identity_document_render_dpi_policy()
        )
        result = await t.transcribe(_pdf_texto_denso(), force_vision=True)

        assert result.ok
        imagem, prompt = vision.calls[0]
        assert isinstance(imagem, bytes)
        px = fitz.Pixmap(imagem)
        assert HIGH.fits(px.width, px.height)  # pre-fitted: no server resize
        assert "strips" not in prompt

    @pytest.mark.asyncio
    async def test_scanned_photo_is_cropped_to_the_image_region(self) -> None:
        vision = _Vision()
        t = LadderDocumentTranscriber(
            analyze=vision, render_dpi_policy=identity_document_render_dpi_policy()
        )
        # A landscape page with the photo in its left half (the RG shape).
        dados = _pdf_scan(300, 400, pagina=(842, 595), rect=fitz.Rect(36, 36, 428, 559))
        result = await t.transcribe(dados)

        assert result.ok
        px = fitz.Pixmap(vision.calls[0][0])
        assert px.height > px.width  # the portrait photo, not the landscape page

    @pytest.mark.asyncio
    async def test_reduced_page_surfaces_as_an_aviso_and_a_warning(self, caplog) -> None:
        vision = _Vision()
        policy = RenderDpiPolicy(
            dpi_for_page_count=lambda n: 300, max_encoded_bytes=5_242_880, max_bands=2
        )
        t = LadderDocumentTranscriber(analyze=vision, render_dpi_policy=policy)
        with caplog.at_level(logging.WARNING):
            result = await t.transcribe(_pdf_texto_denso(altura=6000), force_vision=True)

        assert result.ok
        assert result.avisos == (AVISO_RESOLUCAO_REDUZIDA,)
        assert result.paginas_resolucao_reduzida == (1,)
        assert any("resolucao_reduzida" in r.getMessage() for r in caplog.records)


class TestPolicyByDocumentClass:
    @pytest.mark.parametrize("tipo", ["rg", "cnh", "CPF", "cin"])
    def test_cards_are_one_image(self, tipo) -> None:
        assert render_dpi_policy_for(tipo).max_bands == 1

    @pytest.mark.parametrize(
        "tipo", ["certidao_casamento", "certidao_nascimento", "comprovante_endereco", None]
    )
    def test_full_pages_may_band(self, tipo) -> None:
        assert render_dpi_policy_for(tipo).max_bands == FULL_PAGE_MAX_BANDS

    def test_extractor_reads_a_certidao_through_the_full_page_ladder(self) -> None:
        ex = LadderIdentityExtractor()
        assert ex._ladder_para("rg") is ex._ladder
        pagina = ex._ladder_para("certidao_casamento")
        assert pagina is not ex._ladder
        assert pagina._render_dpi_policy.max_bands == FULL_PAGE_MAX_BANDS
        assert ex._get_escalation_ladder("certidao_casamento")._render_dpi_policy.max_bands == (
            FULL_PAGE_MAX_BANDS
        )


# ── the aviso reaches the read and the trust gate ────────────────────────


class _LadderComAviso:
    def __init__(self, texto: str) -> None:
        self._texto = texto

    async def ler(self, content, mimetype=None, filename=None, **kwargs) -> LeituraTexto:
        return LeituraTexto(self._texto, TextSource.OCR, None, (AVISO_RESOLUCAO_REDUZIDA,))


class TestAvisoReachesTheRead:
    @pytest.mark.asyncio
    async def test_extractor_marks_the_fields(self) -> None:
        ex = LadderIdentityExtractor(ladder=_LadderComAviso("NOME: FULANO DE TAL\nCPF 529.982.247-25"))
        fields = await ex.extract(b"x", mimetype="image/jpeg", tipo_documento="rg")
        assert releitura.resolucao_reduzida(fields)
        assert AVISO_RESOLUCAO_REDUZIDA in (fields.aviso or "").split("+")

    def test_reduced_read_is_escalated(self) -> None:
        f = releitura.marcar_resolucao_reduzida(IdentityFields(source=TextSource.OCR))
        assert releitura.deve_escalar(f, None)

    def test_marking_is_idempotent_and_additive(self) -> None:
        f = IdentityFields(source=TextSource.OCR, aviso="titulares_multiplos")
        uma = releitura.marcar_resolucao_reduzida(f)
        assert uma.aviso == "titulares_multiplos+resolucao_reduzida"
        assert releitura.marcar_resolucao_reduzida(uma) == uma


# ── providers: one request, ordered image blocks ─────────────────────────


class _Msg:
    def __init__(self) -> None:
        self.content = []
        self.stop_reason = "end_turn"
        self.usage = None


class _Messages:
    def __init__(self) -> None:
        self.sent: dict = {}

    async def create(self, **kwargs):
        self.sent = kwargs
        return _Msg()


class _Client:
    def __init__(self) -> None:
        self.messages = _Messages()


class TestProvidersAcceptOrderedBands:
    @pytest.mark.asyncio
    async def test_anthropic_labels_each_band_then_the_prompt(self) -> None:
        from noctusai_lib.integrations.llm.providers.anthropic_provider import AnthropicProvider

        provider = AnthropicProvider()
        client = _Client()
        provider._clients["k"] = client
        await provider.analyze_image([b"\xff\xd8\xffa", b"\x89PNG\r\n\x1a\nb"], "PROMPT", model="m", api_key="k")

        content = client.messages.sent["messages"][0]["content"]
        assert [c["type"] for c in content] == ["text", "image", "text", "image", "text"]
        assert content[0]["text"] == "Image 1:" and content[2]["text"] == "Image 2:"
        assert content[1]["source"]["media_type"] == "image/jpeg"
        assert content[3]["source"]["media_type"] == "image/png"
        assert content[-1]["text"] == "PROMPT"

    @pytest.mark.asyncio
    async def test_anthropic_single_image_shape_unchanged(self) -> None:
        from noctusai_lib.integrations.llm.providers.anthropic_provider import AnthropicProvider

        provider = AnthropicProvider()
        client = _Client()
        provider._clients["k"] = client
        await provider.analyze_image(b"\xff\xd8a", "PROMPT", model="m", api_key="k")
        content = client.messages.sent["messages"][0]["content"]
        assert [c["type"] for c in content] == ["image", "text"]

    @pytest.mark.asyncio
    async def test_fake_provider_records_the_band_count(self) -> None:
        from noctusai_lib.integrations.llm.providers.fake_provider import FakeProvider

        fake = FakeProvider()
        await fake.analyze_image([b"a", b"b", b"c"], "p", model="m", api_key="k")
        assert fake.calls[-1]["image_count"] == 3
