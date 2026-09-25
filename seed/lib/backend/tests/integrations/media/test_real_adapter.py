"""`RealMediaResolver` — the per-org vision-provider switch + the
page-complete scanned-PDF delegation.

Two 2026-09-18/20 production defects, both fixed here:

1. **The provider was ignored.** `org_settings.llm_vision_provider` was set
   for an org, OpenAI's account was out of credit, Anthropic's key worked —
   and every extraction still hit OpenAI, because no `provider=` parameter
   existed anywhere between `make_identity_extractor` and the vision call.
2. **A scanned PDF was read from page 1 only.** `_resolve_pdf` rasterized up
   to `max_pages` pages and then described `page_images[0]` alone,
   regardless of `max_pages` — a certidão de casamento's AVERBAÇÃO (a later
   page) never reached the model, and the answer inverted rather than
   degraded.

These tests exercise `RealMediaResolver` directly via its `analyze=` /
`document_transcriber=` DI seams (`KB § PATTERNS/backend/di-test-seam.md`
Class-B) — never by patching this module's own functions.
"""
from __future__ import annotations

import pytest

from noctusai_lib.integrations.documents import TranscribedPage, Transcription, TextSource
from noctusai_lib.integrations.media import InboundMedia
from noctusai_lib.integrations.media.real_adapter import RealMediaResolver


class _FakeAnalyze:
    """Records every call; returns a canned, obviously-synthetic answer."""

    def __init__(self, answer: str = "[FAKE] descricao") -> None:
        self.answer = answer
        self.calls: list[dict] = []

    async def __call__(self, image, prompt, **kwargs):
        self.calls.append({"prompt": prompt, **kwargs})
        return self.answer


class _FakeTranscriber:
    """Stands in for `documents.make_document_transcriber(real=True, ...)`."""

    def __init__(self, transcricao: Transcription) -> None:
        self._transcricao = transcricao
        self.calls: list[dict] = []

    async def transcribe(self, content, *, mimetype=None, filename=None, force_vision=False):
        self.calls.append(
            {
                "content": content,
                "mimetype": mimetype,
                "filename": filename,
                "force_vision": force_vision,
            }
        )
        return self._transcricao


def _scanned_pdf(num_pages: int) -> bytes:
    """A PDF with `num_pages` pages, each a page-sized raster image and NO
    extractable text — `classify_pdf_text_layer` reports `is_substantive`
    False for every page, exactly like a photographed cartório document.
    Mirrors `tests/integrations/media/test_pdf_text.py::_pdf`.
    """
    fitz = pytest.importorskip("fitz")

    doc = fitz.open()
    for _ in range(num_pages):
        page = doc.new_page()
        pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 200, 280))
        pix.set_rect(pix.irect, (128, 128, 128))
        page.insert_image(page.rect, pixmap=pix)
    out = doc.tobytes()
    doc.close()
    return out


class TestUnsetProviderIsTheDocumentDefault:
    """(b) An org that never touched `llm_vision_provider` reads documents
    with the seed's canonical DOCUMENT provider (Anthropic since 2026-09-22 —
    OpenAI had no credit), paired with its pinned model. Before, `None` fell
    through to the fleet chat default ("openai") and every read 429'd."""

    @pytest.mark.asyncio
    async def test_unset_provider_resolves_to_the_document_default(self) -> None:
        from noctusai_lib.integrations.documents.providers import (
            DEFAULT_DOCUMENT_PROVIDER,
            OCR_MODELS,
        )

        analyze = _FakeAnalyze()
        resolver = RealMediaResolver(org_id="org-1", analyze=analyze)

        await resolver.resolve(InboundMedia(content=b"\xff\xd8\xff", mimetype="image/jpeg"))

        assert len(analyze.calls) == 1
        assert analyze.calls[0]["provider"] == DEFAULT_DOCUMENT_PROVIDER == "anthropic"
        assert analyze.calls[0]["model"] == OCR_MODELS["anthropic"]

    @pytest.mark.asyncio
    async def test_a_missing_key_is_named_not_swapped(self) -> None:
        """🔴 No silent fallback: the selected vendor's missing key comes back
        as `missing_credentials` on the result — never a retry on OpenAI."""
        from noctusai_lib.integrations.llm.exceptions import LLMNotConfigured

        calls: list[dict] = []

        async def _sem_chave(image, prompt, **kwargs):
            calls.append(kwargs)
            raise LLMNotConfigured(kwargs.get("provider") or "?")

        resolver = RealMediaResolver(org_id="org-1", analyze=_sem_chave)

        out = await resolver.resolve(InboundMedia(content=b"\xff\xd8\xff", mimetype="image/jpeg"))

        assert out.error == "missing_credentials"
        assert "Anthropic" in (out.error_message or "")
        assert [c["provider"] for c in calls] == ["anthropic"]

    @pytest.mark.asyncio
    async def test_explicit_openai_also_keeps_the_tuned_default_model(self) -> None:
        """OpenAI explicitly chosen (the switch's own documented default)
        must not move off the already-tuned `gpt-4o` onto the OCR pin —
        only a NON-OpenAI vendor has no tuned default at this layer."""
        analyze = _FakeAnalyze()
        resolver = RealMediaResolver(org_id="org-1", provider="openai", analyze=analyze)

        await resolver.resolve(InboundMedia(content=b"\xff\xd8\xff", mimetype="image/jpeg"))

        assert analyze.calls[0]["provider"] == "openai"
        assert analyze.calls[0]["model"] is None


class TestProviderRoutesVendorAndModelTogether:
    """(a) `documents.providers.OCR_MODELS` says the model is NOT
    portable across providers — selecting a provider must select its model
    too, or a switch to Anthropic sends it OpenAI's model name."""

    @pytest.mark.asyncio
    async def test_anthropic_selects_its_own_model(self) -> None:
        analyze = _FakeAnalyze()
        resolver = RealMediaResolver(org_id="org-1", provider="anthropic", analyze=analyze)

        await resolver.resolve(InboundMedia(content=b"\xff\xd8\xff", mimetype="image/jpeg"))

        assert analyze.calls[0]["provider"] == "anthropic"
        assert analyze.calls[0]["model"] == "claude-haiku-4-5"

    @pytest.mark.asyncio
    async def test_gemini_selects_its_own_model(self) -> None:
        analyze = _FakeAnalyze()
        resolver = RealMediaResolver(org_id="org-1", provider="gemini", analyze=analyze)

        await resolver.resolve(InboundMedia(content=b"\xff\xd8\xff", mimetype="image/jpeg"))

        assert analyze.calls[0]["provider"] == "gemini"
        assert analyze.calls[0]["model"] == "gemini-2.0-flash"


class TestScannedPdfDelegatesInsteadOfDescribingPageOne:
    """(c) The averbação-inversion regression: a multi-page scanned PDF
    must yield text from EVERY page, not a description of the first."""

    @pytest.mark.asyncio
    async def test_last_page_content_reaches_the_output(self) -> None:
        transcricao = Transcription(
            pages=(
                TranscribedPage(number=1, text="CASAMENTO: JOAO E MARIA", source=TextSource.OCR),
                TranscribedPage(number=2, text="REGIME: COMUNHAO PARCIAL", source=TextSource.OCR),
                TranscribedPage(
                    number=3,
                    text="AVERBACAO Nº 1: DIVORCIO AVERBADO EM 2020",
                    source=TextSource.OCR,
                ),
            ),
            num_paginas=3,
        )
        transcriber = _FakeTranscriber(transcricao)
        resolver = RealMediaResolver(
            org_id="org-1", max_pages=None, document_transcriber=transcriber
        )

        pdf_bytes = _scanned_pdf(3)
        out = await resolver.resolve(
            InboundMedia(content=pdf_bytes, mimetype="application/pdf", filename="certidao.pdf")
        )

        assert out.error is None
        assert "AVERBACAO" in out.text
        assert "DIVORCIO" in out.text
        # the whole document reached the transcriber, not a truncated slice
        assert transcriber.calls[0]["content"] == pdf_bytes

    @pytest.mark.asyncio
    async def test_a_substantive_text_layer_still_short_circuits(self) -> None:
        """The free rung is untouched by this change: a digitally-issued
        PDF never reaches the transcriber at all."""
        transcriber = _FakeTranscriber(Transcription(error="should_not_be_called"))
        resolver = RealMediaResolver(org_id="org-1", document_transcriber=transcriber)

        fitz = pytest.importorskip("fitz")
        doc = fitz.open()
        page = doc.new_page()
        # Above `MIN_CHARS_PER_PAGE` (100) so the classifier calls this page
        # substantive rather than "below char floor".
        texto = "TEXTO DIGITAL REAL. " * 10
        page.insert_textbox(fitz.Rect(20, 20, 500, 500), texto, fontsize=10)
        pdf_bytes = doc.tobytes()
        doc.close()

        out = await resolver.resolve(
            InboundMedia(content=pdf_bytes, mimetype="application/pdf")
        )

        assert out.error is None
        assert "TEXTO DIGITAL REAL" in out.text
        assert transcriber.calls == []

    @pytest.mark.asyncio
    async def test_force_vision_overrides_the_short_circuit_even_when_substantive(
        self,
    ) -> None:
        """`InboundMedia.force_vision=True` (the identity extractor's forced
        retry, via `DocumentTextLadder.to_text(pular_camada_texto=True)`)
        must reach the transcriber even though this SAME text layer is, by
        the field-agnostic classifier, substantive. Without this, a caller
        retrying because this exact text held none of its fields gets this
        exact text back again — measured 2026-09-23 on a "CNH Digital" PDF
        whose card-cover disclaimer classifies substantive while every
        identity field lives in a small embedded image."""
        transcricao = Transcription(
            pages=(TranscribedPage(number=1, text="NOME: FULANO DE TAL", source=TextSource.OCR),),
            num_paginas=1,
        )
        transcriber = _FakeTranscriber(transcricao)
        resolver = RealMediaResolver(org_id="org-1", document_transcriber=transcriber)

        fitz = pytest.importorskip("fitz")
        doc = fitz.open()
        page = doc.new_page()
        texto = "TEXTO DIGITAL REAL. " * 10
        page.insert_textbox(fitz.Rect(20, 20, 500, 500), texto, fontsize=10)
        pdf_bytes = doc.tobytes()
        doc.close()

        out = await resolver.resolve(
            InboundMedia(content=pdf_bytes, mimetype="application/pdf", force_vision=True)
        )

        assert out.error is None
        assert "NOME: FULANO DE TAL" in out.text
        assert "TEXTO DIGITAL REAL" not in out.text  # the vision answer won, not the text layer
        assert len(transcriber.calls) == 1
        assert transcriber.calls[0]["force_vision"] is True


class TestQuotaFailurePropagates:
    """(d) `insufficient_quota` must reach the caller as that exact code —
    not folded into a generic `resolve_failed`/`pdf_no_text`."""

    @pytest.mark.asyncio
    async def test_insufficient_quota_is_not_genericised(self) -> None:
        transcriber = _FakeTranscriber(
            Transcription(
                error="insufficient_quota",
                error_message="Error code: 429 - insufficient_quota",
            )
        )
        resolver = RealMediaResolver(org_id="org-1", document_transcriber=transcriber)

        pdf_bytes = _scanned_pdf(1)
        out = await resolver.resolve(
            InboundMedia(content=pdf_bytes, mimetype="application/pdf")
        )

        assert out.error == "insufficient_quota"
        assert "429" in out.error_message


class TestMaxPagesMapsToMaxVisionPages:
    """`self._max_pages` (a page-count cap) feeds the transcriber's
    `max_vision_pages` (a cap on pages NEEDING vision) — the fix does not
    just delegate, it maps the two knobs onto each other correctly."""

    def test_none_keeps_the_transcribers_own_safety_cap(self) -> None:
        from noctusai_lib.integrations.documents.transcription import (
            MAX_VISION_PAGES,
            LadderDocumentTranscriber,
        )

        resolver = RealMediaResolver(org_id="org-1", max_pages=None)
        transcriber = resolver._get_document_transcriber()

        assert isinstance(transcriber, LadderDocumentTranscriber)
        assert transcriber._max_vision_pages == MAX_VISION_PAGES

    def test_a_concrete_cap_is_forwarded_verbatim(self) -> None:
        from noctusai_lib.integrations.documents.transcription import (
            LadderDocumentTranscriber,
        )

        resolver = RealMediaResolver(org_id="org-1", max_pages=3)
        transcriber = resolver._get_document_transcriber()

        assert isinstance(transcriber, LadderDocumentTranscriber)
        assert transcriber._max_vision_pages == 3

    def test_provider_reaches_the_delegated_transcriber_too(self) -> None:
        from noctusai_lib.integrations.documents.transcription import (
            LadderDocumentTranscriber,
        )

        resolver = RealMediaResolver(org_id="org-1", provider="anthropic")
        transcriber = resolver._get_document_transcriber()

        assert isinstance(transcriber, LadderDocumentTranscriber)
        assert transcriber._provider == "anthropic"
        assert transcriber._ocr_model == "claude-haiku-4-5"


class TestDocumentPromptReachesTheDelegatedTranscriber:
    """🔴 P1/883 (2026-09-25): `_resolve_image` always honoured
    `self._doc_prompt`; `_resolve_pdf`'s vision rung — the ONLY rung a
    scanned/image-only PDF, or a mixed PDF's scanned pages, ever reaches —
    silently did not, always building its transcriber with
    `documents.transcription.OCR_PROMPT` regardless of what the caller
    named. An identity document that happens to arrive as a PDF (a CNH-e
    upload, not a raw photo) inherited the matrícula-tuned prompt instead of
    `LadderIdentityExtractor`'s own `_IDENTITY_DOCUMENT_PROMPT` — real,
    measured: a CNH-e's `DOC. IDENTIDADE / ÓRG. EMISSOR / UF` box and `DATA
    NASCIMENTO` field went unread even though every parser in this package
    is label-anchored and that prompt exists exactly to keep a label next to
    its value. See `RealMediaResolver._doc_prompt_override`'s own comment."""

    def test_an_explicit_document_prompt_becomes_the_transcribers_ocr_prompt(
        self,
    ) -> None:
        resolver = RealMediaResolver(
            org_id="org-1", document_prompt="RÓTULO: valor, um campo por linha"
        )
        transcriber = resolver._get_document_transcriber()
        assert transcriber._ocr_prompt == "RÓTULO: valor, um campo por linha"

    def test_no_document_prompt_keeps_ocr_prompt_untouched(self) -> None:
        """Matrícula/certidão-estrutura pass `document_prompt=None` and rely
        on `OCR_PROMPT`'s `**bold**`/`<u>underline</u>` markup preservation
        for `parse_markup` — this fix must not touch that default."""
        from noctusai_lib.integrations.documents.transcription import OCR_PROMPT

        resolver = RealMediaResolver(org_id="org-1")
        transcriber = resolver._get_document_transcriber()
        assert transcriber._ocr_prompt == OCR_PROMPT

    def test_the_identity_extractors_own_prompt_reaches_it_end_to_end(self) -> None:
        """The full seam: `make_identity_extractor` -> `DocumentTextLadder`
        -> `RealMediaResolver` -> the delegated PDF transcriber."""
        from noctusai_lib.integrations.documents import make_identity_extractor
        from noctusai_lib.integrations.documents.real import (
            _IDENTITY_DOCUMENT_PROMPT,
        )

        extractor = make_identity_extractor(real=True)
        resolver = extractor._ladder._get_resolver()
        transcriber = resolver._get_document_transcriber()
        assert transcriber._ocr_prompt == _IDENTITY_DOCUMENT_PROMPT
