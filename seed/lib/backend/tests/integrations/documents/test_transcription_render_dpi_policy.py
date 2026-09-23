"""`RenderDpiPolicy` / `identity_document_render_dpi_policy` — the
`NOC-REMEDIATE[identity-vision-render-dpi]` fix.

Reproduces the measured 2026-09-23 finding with INVENTED fixtures only, no
real document or PII anywhere:

- A "CNH Digital"-shaped page: the card's fields live in a small embedded
  image, the page's own selectable text is nothing but the ONR/Serpro
  provenance disclaimer (byte-identical stamp text `pdf_text` already
  strips — see `ONR_STAMP` below). At the seed-wide default 200 DPI, a
  full-page raster is too coarse for the vision model to read the card;
  a naive GLOBAL DPI bump elsewhere in this finding 413'd a 2-page
  certidão against Anthropic's per-image ceiling.

This file covers three layers: the policy's own page-count mapping (pure),
the byte-budget stepping + native-embedded-image shortcut inside
`LadderDocumentTranscriber` (mocked PDF mechanics, mirroring
`test_transcription.py`'s `_transcriber` helper), and one true end-to-end
pass through real PyMuPDF with a synthetic one-page PDF built in-test.
"""
from __future__ import annotations

import base64
import logging

import pytest

from noctusai_lib.integrations.documents.transcription import (
    RENDER_DPI,
    LadderDocumentTranscriber,
    RenderDpiPolicy,
    _dominant_embedded_image,
    _encoded_size,
    identity_document_render_dpi_policy,
)
from noctusai_lib.integrations.media import PdfPage, PdfTextLayer

#: The real ONR stamp (already used by `test_transcription.py`) — every
#: line matches a `pdf_text._PROVENANCE_STAMP_PATTERNS` entry, so the page
#: strips to nothing and `_classify_page` returns
#: `reason="provenance stamp only"` for real, no fixture-faking of that
#: signal required.
ONR_STAMP = (
    "Valide este documento clicando no link a seguir: "
    "https://assinador-web.onr.org.br/docs/7JX9U-HLZEA-9LJWT-PM2QS\n"
    "Valide aqui\neste documento"
)


def _camada(*paginas: tuple[str, bool, str]) -> PdfTextLayer:
    return PdfTextLayer(
        pages=tuple(
            PdfPage(number=i, text=t, is_substantive=sub, reason=reason)
            for i, (t, sub, reason) in enumerate(paginas, 1)
        ),
        tooling_available=True,
    )


class _Vision:
    """Records every image it was called with — bytes only, not shape —
    so a test can assert whether the NATIVE embedded image or a full-page
    raster reached the vision call."""

    def __init__(self, texto=lambda n: f"OCR PAGINA {n}"):
        self.images: list[bytes] = []
        self._next = 0

    async def __call__(
        self, image, prompt, *, model=None, provider=None, org_id=None, max_tokens=None
    ):
        self._next += 1
        self.images.append(image)
        return f"OCR PAGINA {self._next}"


class TestIdentityPolicyPageCountMapping:
    """Pure — no PDF, no PyMuPDF, no network."""

    def test_single_page_gets_the_sharpest_render(self) -> None:
        policy = identity_document_render_dpi_policy()
        assert policy.dpi_for_page_count(1) == 400

    @pytest.mark.parametrize("num_pages", [2, 3])
    def test_a_few_pages_steps_down_but_stays_sharp(self, num_pages: int) -> None:
        policy = identity_document_render_dpi_policy()
        assert policy.dpi_for_page_count(num_pages) == 300

    @pytest.mark.parametrize("num_pages", [4, 7, 40])
    def test_longer_documents_keep_the_unchanged_canonical_default(
        self, num_pages: int
    ) -> None:
        policy = identity_document_render_dpi_policy()
        assert policy.dpi_for_page_count(num_pages) == RENDER_DPI

    def test_max_encoded_bytes_is_anthropics_documented_ceiling(self) -> None:
        from noctusai_lib.integrations.llm.providers.anthropic_provider import (
            MAX_IMAGE_BYTES,
        )

        policy = identity_document_render_dpi_policy()
        assert policy.max_encoded_bytes == MAX_IMAGE_BYTES

    def test_step_down_candidates_are_all_below_render_dpi_default_or_equal(self) -> None:
        # The floor of the step-down ladder is the seed-wide canonical
        # default — this policy never renders BELOW what every other
        # consumer already accepts as legible.
        policy = identity_document_render_dpi_policy()
        assert min(policy.step_down_dpis) <= RENDER_DPI


class TestEncodedSize:
    """`_encoded_size` must agree with the real base64 length it stands in
    for — it is a shortcut, not a different number."""

    @pytest.mark.parametrize("n", [0, 1, 2, 3, 4, 100, 4096, 1_234_567])
    def test_matches_real_base64_length(self, n: int) -> None:
        raw = b"x" * n
        assert _encoded_size(raw) == len(base64.b64encode(raw))


class TestDominantEmbeddedImage:
    """Real PyMuPDF, synthetic one-page PDFs — invented pixels, no PII."""

    @staticmethod
    def _card_png(color=(0.1, 0.3, 0.7)) -> bytes:
        import fitz  # type: ignore

        doc = fitz.open()
        page = doc.new_page(width=40, height=25)
        page.draw_rect(page.rect, color=color, fill=color)
        png = page.get_pixmap(matrix=fitz.Matrix(4, 4)).tobytes("png")
        doc.close()
        return png

    def _pdf_com_um_cartao_e_disclaimer(self) -> tuple[bytes, bytes]:
        """One page: a small embedded "card" image + the ONR disclaimer as
        the page's ONLY selectable text — the exact shape this finding
        measured. Returns `(pdf_bytes, card_png_bytes)`."""
        import fitz  # type: ignore

        card_png = self._card_png()
        doc = fitz.open()
        page = doc.new_page(width=200, height=280)
        page.insert_image(fitz.Rect(20, 20, 60, 45), stream=card_png)
        for i, linha in enumerate(ONR_STAMP.splitlines()):
            page.insert_text((10, 100 + i * 10), linha, fontsize=6)
        pdf_bytes = doc.tobytes()
        doc.close()
        return pdf_bytes, card_png

    def test_single_embedded_image_extracted_at_native_resolution(self) -> None:
        pdf_bytes, card_png = self._pdf_com_um_cartao_e_disclaimer()
        extraido = _dominant_embedded_image(pdf_bytes, 1)
        assert extraido == card_png

    def test_page_classification_is_the_real_provenance_stamp_verdict(self) -> None:
        """Not faked in this test class: the SAME `classify_pdf_text_layer`
        the ladder itself calls must independently reach
        `reason="provenance stamp only"` on this fixture, or the fixture
        does not reproduce the finding."""
        from noctusai_lib.integrations.media import classify_pdf_text_layer

        pdf_bytes, _card_png = self._pdf_com_um_cartao_e_disclaimer()
        camada = classify_pdf_text_layer(pdf_bytes)
        assert len(camada.pages) == 1
        assert camada.pages[0].is_substantive is False
        assert camada.pages[0].reason == "provenance stamp only"

    def test_two_comparable_images_are_ambiguous_no_dominant_answer(self) -> None:
        import fitz  # type: ignore

        img_a = self._card_png(color=(0.1, 0.3, 0.7))
        img_b = self._card_png(color=(0.7, 0.2, 0.1))
        doc = fitz.open()
        page = doc.new_page(width=200, height=280)
        page.insert_image(fitz.Rect(20, 20, 60, 45), stream=img_a)
        page.insert_image(fitz.Rect(100, 20, 140, 45), stream=img_b)
        pdf_bytes = doc.tobytes()
        doc.close()

        assert _dominant_embedded_image(pdf_bytes, 1) is None

    def test_page_with_no_images_returns_none(self) -> None:
        import fitz  # type: ignore

        doc = fitz.open()
        page = doc.new_page(width=200, height=280)
        page.insert_text((10, 100), "no images on this page at all")
        pdf_bytes = doc.tobytes()
        doc.close()

        assert _dominant_embedded_image(pdf_bytes, 1) is None

    def test_out_of_range_page_number_returns_none_not_raises(self) -> None:
        pdf_bytes, _card_png = self._pdf_com_um_cartao_e_disclaimer()
        assert _dominant_embedded_image(pdf_bytes, 99) is None

    def test_unopenable_bytes_return_none_not_raises(self) -> None:
        assert _dominant_embedded_image(b"not a pdf at all", 1) is None


def _spy_pdf_to_images(monkeypatch, respostas: dict[int, dict[int, bytes]]):
    """Stand in for `_pdf_to_images(pdf_bytes, [numero], dpi)`, recording
    every `(numero, dpi)` call and returning bytes sized by `respostas`
    (dpi -> page-number -> bytes), so a test can assert exactly which DPI
    candidates were tried and in what order."""
    import noctusai_lib.integrations.documents.transcription as mod

    chamadas: list[tuple[int, ...]] = []

    def _fake(pdf_bytes, paginas, dpi):
        chamadas.append((dpi, tuple(paginas)))
        por_pagina = respostas.get(dpi, {})
        return {n: por_pagina[n] for n in paginas if n in por_pagina}

    monkeypatch.setattr(mod, "_pdf_to_images", _fake)
    return chamadas


class TestBudgetAwareRasterization:
    """`LadderDocumentTranscriber` with a `render_dpi_policy` set — the
    orchestration layer, PDF mechanics mocked (mirrors
    `test_transcription.py`'s `_transcriber` helper)."""

    def _transcriber(self, monkeypatch, *, num_paginas, camada, policy, vision=None):
        import noctusai_lib.integrations.documents.transcription as mod

        monkeypatch.setattr(mod, "_contar_paginas", lambda b: num_paginas)
        monkeypatch.setattr(
            "noctusai_lib.integrations.media.classify_pdf_text_layer", lambda b: camada
        )
        return LadderDocumentTranscriber(
            analyze=vision or _Vision(), render_dpi_policy=policy
        )

    @pytest.mark.asyncio
    async def test_starting_dpi_used_when_the_first_render_already_fits(
        self, monkeypatch
    ) -> None:
        policy = RenderDpiPolicy(
            dpi_for_page_count=lambda n: 400,
            max_encoded_bytes=10_000_000,
        )
        camada = _camada(("", False, "below char floor"))
        chamadas = _spy_pdf_to_images(monkeypatch, {400: {1: b"x" * 1000}})
        transcriber = self._transcriber(
            monkeypatch, num_paginas=1, camada=camada, policy=policy
        )

        result = await transcriber.transcribe(b"pdf-bytes")

        assert result.ok
        assert chamadas == [(400, (1,))]
        assert result.pages[0].source.value == "ocr"

    @pytest.mark.asyncio
    async def test_steps_down_through_the_ladder_until_it_fits(
        self, monkeypatch
    ) -> None:
        # 400 DPI "renders" oversized; 300 fits — reproduces the exact
        # shape a naive global DPI=400 got wrong (it never tried 300).
        policy = RenderDpiPolicy(
            dpi_for_page_count=lambda n: 400,
            max_encoded_bytes=_encoded_size(b"x" * 500) ,
            step_down_dpis=(300, 200, 150, 100),
        )
        camada = _camada(("", False, "below char floor"))
        chamadas = _spy_pdf_to_images(
            monkeypatch, {400: {1: b"x" * 5000}, 300: {1: b"x" * 400}}
        )
        transcriber = self._transcriber(
            monkeypatch, num_paginas=1, camada=camada, policy=policy
        )

        result = await transcriber.transcribe(b"pdf-bytes")

        assert result.ok
        assert chamadas == [(400, (1,)), (300, (1,))]

    @pytest.mark.asyncio
    async def test_floor_still_over_budget_is_sent_anyway_and_logged(
        self, monkeypatch, caplog
    ) -> None:
        # Every candidate is oversized — the page must NOT be silently
        # dropped (a document that loses a page because it is dense is the
        # exact "no silent errors" shape this whole family forbids), but
        # the near-413 must be visible.
        policy = RenderDpiPolicy(
            dpi_for_page_count=lambda n: 400,
            max_encoded_bytes=1,
            step_down_dpis=(300, 200),
        )
        camada = _camada(("", False, "below char floor"))
        _spy_pdf_to_images(
            monkeypatch,
            {400: {1: b"x" * 9000}, 300: {1: b"x" * 6000}, 200: {1: b"x" * 3000}},
        )
        transcriber = self._transcriber(
            monkeypatch, num_paginas=1, camada=camada, policy=policy
        )

        with caplog.at_level(logging.ERROR):
            result = await transcriber.transcribe(b"pdf-bytes")

        assert result.ok  # sent anyway, never dropped
        assert any("still exceeds" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_dominant_embedded_image_bypasses_the_page_raster_entirely(
        self, monkeypatch
    ) -> None:
        policy = RenderDpiPolicy(
            dpi_for_page_count=lambda n: 400,
            max_encoded_bytes=10_000_000,
        )
        camada = _camada((ONR_STAMP, False, "provenance stamp only"))
        chamadas = _spy_pdf_to_images(monkeypatch, {400: {1: b"FULL PAGE RASTER"}})

        import noctusai_lib.integrations.documents.transcription as mod

        cartao_nativo = b"NATIVE CARD BYTES"
        monkeypatch.setattr(mod, "_dominant_embedded_image", lambda b, n: cartao_nativo)

        vision = _Vision()
        transcriber = self._transcriber(
            monkeypatch, num_paginas=1, camada=camada, policy=policy, vision=vision
        )

        result = await transcriber.transcribe(b"pdf-bytes")

        assert result.ok
        assert chamadas == []  # the whole-page raster rung never ran
        assert vision.images == [cartao_nativo]

    @pytest.mark.asyncio
    async def test_dominant_image_over_budget_falls_back_to_page_raster(
        self, monkeypatch
    ) -> None:
        policy = RenderDpiPolicy(
            dpi_for_page_count=lambda n: 400,
            max_encoded_bytes=_encoded_size(b"x" * 100),
        )
        camada = _camada((ONR_STAMP, False, "provenance stamp only"))
        chamadas = _spy_pdf_to_images(monkeypatch, {400: {1: b"y" * 50}})

        import noctusai_lib.integrations.documents.transcription as mod

        # The "native" image is itself bigger than the budget — must not
        # be sent as-is; the ordinary raster rung (which DOES fit) answers.
        monkeypatch.setattr(
            mod, "_dominant_embedded_image", lambda b, n: b"z" * 100_000
        )
        transcriber = self._transcriber(
            monkeypatch, num_paginas=1, camada=camada, policy=policy
        )

        result = await transcriber.transcribe(b"pdf-bytes")

        assert result.ok
        assert chamadas == [(400, (1,))]

    @pytest.mark.asyncio
    async def test_no_render_dpi_policy_is_the_unchanged_flat_dpi_path(
        self, monkeypatch
    ) -> None:
        """`render_dpi_policy=None` (every non-identity consumer) must not
        even LOOK at the budget/dominant-image machinery — same call shape
        as before this fix existed."""
        import noctusai_lib.integrations.documents.transcription as mod

        calls: list[tuple[int, ...]] = []

        def _fake(pdf_bytes, paginas, dpi):
            calls.append((dpi, tuple(paginas)))
            return {n: b"png" for n in paginas}

        monkeypatch.setattr(mod, "_pdf_to_images", _fake)
        monkeypatch.setattr(mod, "_contar_paginas", lambda b: 1)
        monkeypatch.setattr(
            "noctusai_lib.integrations.media.classify_pdf_text_layer",
            lambda b: _camada((ONR_STAMP, False, "provenance stamp only")),
        )

        transcriber = LadderDocumentTranscriber(analyze=_Vision(), render_dpi=222)
        result = await transcriber.transcribe(b"pdf-bytes")

        assert result.ok
        assert calls == [(222, (1,))]


class TestIdentityExtractorWiresThePolicyByDefault:
    """`LadderIdentityExtractor` opts INTO the fix by construction — no
    caller-side change required anywhere it is already used."""

    def test_default_ladder_carries_the_identity_policy(self) -> None:
        from noctusai_lib.integrations.documents.real import LadderIdentityExtractor

        extractor = LadderIdentityExtractor()
        policy = extractor._ladder._render_dpi_policy
        assert isinstance(policy, RenderDpiPolicy)
        assert policy.dpi_for_page_count(1) == 400

    def test_an_injected_ladder_overrides_it_same_as_every_other_default(self) -> None:
        from noctusai_lib.integrations.documents.ladder import DocumentTextLadder
        from noctusai_lib.integrations.documents.real import LadderIdentityExtractor

        custom = DocumentTextLadder(resolver=object())
        extractor = LadderIdentityExtractor(ladder=custom)
        assert extractor._ladder is custom
        assert extractor._ladder._render_dpi_policy is None


class TestPolicyThreadsThroughTheFullChain:
    """`DocumentTextLadder` -> `get_media_resolver` -> `RealMediaResolver`
    -> `make_document_transcriber` — each hop forwards `render_dpi_policy`
    verbatim, capture-the-kwarg style (mirrors how the rest of this ladder
    family is tested elsewhere in this suite)."""

    def test_ladder_forwards_policy_to_get_media_resolver(self, monkeypatch) -> None:
        from noctusai_lib.integrations.documents.ladder import DocumentTextLadder

        captured: dict = {}

        def _fake_get_media_resolver(**kwargs):
            captured.update(kwargs)
            return object()

        monkeypatch.setattr(
            "noctusai_lib.integrations.media.get_media_resolver",
            _fake_get_media_resolver,
        )

        policy = identity_document_render_dpi_policy()
        ladder = DocumentTextLadder(render_dpi_policy=policy)
        ladder._get_resolver()

        assert captured["render_dpi_policy"] is policy

    def test_get_media_resolver_forwards_policy_to_real_media_resolver(
        self, monkeypatch
    ) -> None:
        from noctusai_lib.integrations.media import get_media_resolver

        captured: dict = {}

        class _FakeRealMediaResolver:
            def __init__(self, **kwargs):
                captured.update(kwargs)

        monkeypatch.setattr(
            "noctusai_lib.integrations.media.real_adapter.RealMediaResolver",
            _FakeRealMediaResolver,
        )

        policy = identity_document_render_dpi_policy()
        get_media_resolver(real=True, render_dpi_policy=policy)

        assert captured["render_dpi_policy"] is policy

    def test_real_media_resolver_forwards_policy_to_make_document_transcriber(
        self, monkeypatch
    ) -> None:
        from noctusai_lib.integrations.media.real_adapter import RealMediaResolver

        captured: dict = {}

        def _fake_make_document_transcriber(**kwargs):
            captured.update(kwargs)
            return object()

        import noctusai_lib.integrations.documents.transcription as transcription_mod

        monkeypatch.setattr(
            transcription_mod, "make_document_transcriber", _fake_make_document_transcriber
        )

        resolver = RealMediaResolver(render_dpi_policy="the-policy-object")
        resolver._get_document_transcriber()

        assert captured["render_dpi_policy"] == "the-policy-object"
