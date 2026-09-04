"""Whole-document transcription: the ladder, per page.

Lifted 2026-08-25 from `erp-imobiliario/app/services/matricula_service.py`
along with the capability itself. The assertions are the product's, because
they encode incidents that actually happened there — a certidão returned as
three copies of its own signature stamp, and a whole document billed to
vision when half of it was already machine-readable.
"""
from __future__ import annotations

import pytest

from noctusai_lib.integrations.documents import (
    FakeDocumentTranscriber,
    TextSource,
    Transcription,
    make_document_transcriber,
)
from noctusai_lib.integrations.documents.transcription import (
    DEFAULT_VISION_PROVIDER,
    OCR_MODELS,
    LadderDocumentTranscriber,
)
from noctusai_lib.integrations.media import PdfPage, PdfTextLayer

#: The real stamp from the 2026-08-25 ERP defect.
ONR_STAMP = (
    "Valide este documento clicando no link a seguir: "
    "https://assinador-web.onr.org.br/docs/7JX9U-HLZEA-9LJWT-PM2QS\n"
    "Valide aqui\neste documento"
)


def _camada(*paginas: tuple[str, bool]) -> PdfTextLayer:
    return PdfTextLayer(
        pages=tuple(
            PdfPage(number=i, text=t, is_substantive=sub, reason="stub")
            for i, (t, sub) in enumerate(paginas, 1)
        ),
        tooling_available=True,
    )


class _Vision:
    """Stands in for the vision rung, recording which pages it was billed for.

    Also records the `(provider, model)` it was called with: those two must
    travel together, and a stub that swallowed them would let the pair drift
    apart unnoticed.
    """

    def __init__(self, texto=lambda n: f"OCR PAGINA {n}"):
        self.pages: list[int] = []
        self.calls: list[tuple[str | None, str | None]] = []
        self._texto = texto
        self._next = 0

    async def __call__(
        self, image, prompt, *, model=None, provider=None, org_id=None, max_tokens=None
    ):
        self._next += 1
        self.pages.append(self._next)
        self.calls.append((provider, model))
        return self._texto(self._next)


def _transcriber(monkeypatch, camada, *, num_paginas, vision=None, **kw):
    """Wire a Ladder transcriber over stubbed PDF mechanics.

    PyMuPDF is stubbed out rather than fed synthetic PDFs: what these tests
    defend is the ROUTING between rungs, and real bytes would make each case
    an exercise in PDF construction instead.
    """
    import noctusai_lib.integrations.documents.transcription as mod

    monkeypatch.setattr(mod, "_contar_paginas", lambda b: num_paginas)
    monkeypatch.setattr(
        "noctusai_lib.integrations.media.classify_pdf_text_layer", lambda b: camada
    )
    monkeypatch.setattr(
        mod, "_pdf_to_images", lambda b, paginas, dpi: {n: b"png" for n in paginas}
    )
    return LadderDocumentTranscriber(analyze=vision or _Vision(), **kw)


class TestFakeIsTheDefault:
    def test_factory_returns_the_fake_unless_asked(self) -> None:
        assert isinstance(make_document_transcriber(), FakeDocumentTranscriber)

    @pytest.mark.asyncio
    async def test_the_fake_is_obviously_fake(self) -> None:
        out = await FakeDocumentTranscriber().transcribe(b"%PDF")
        assert out.ok
        assert "FALSA" in out.text, "a fixture on a real screen must look wrong"

    @pytest.mark.asyncio
    async def test_empty_bytes_are_an_error_not_an_empty_string(self) -> None:
        out = await FakeDocumentTranscriber().transcribe(b"")
        assert out.error == "empty_document"


class TestTheTextLayerRungIsFree:
    @pytest.mark.asyncio
    async def test_a_typeset_document_never_reaches_vision(self, monkeypatch) -> None:
        vision = _Vision()
        t = _transcriber(
            monkeypatch, _camada(("CORPO UM", True), ("CORPO DOIS", True)),
            num_paginas=2, vision=vision,
        )
        out = await t.transcribe(b"%PDF")

        assert vision.pages == [], "paid for vision on a machine-readable PDF"
        assert out.text == "CORPO UM\n\nCORPO DOIS"
        assert out.paginas_por_camada == (1, 2)
        assert out.paginas_por_visao == ()

    @pytest.mark.asyncio
    async def test_it_works_with_no_credential_configured(self, monkeypatch) -> None:
        """Rung 1 runs BEFORE the credential check on purpose: refusing a
        document we can read for free would be refusing work we can do."""
        import noctusai_lib.integrations.documents.transcription as mod

        monkeypatch.setattr(mod, "_contar_paginas", lambda b: 1)
        monkeypatch.setattr(
            "noctusai_lib.integrations.media.classify_pdf_text_layer",
            lambda b: _camada(("CORPO", True)),
        )
        monkeypatch.setattr(
            "noctusai_lib.config.credentials.resolve_credential",
            lambda *a, **k: None,
        )
        out = await LadderDocumentTranscriber().transcribe(b"%PDF")
        assert out.ok and out.text == "CORPO"


class TestAScanIsNotATextLayer:
    """🔴 The 2026-08-25 defect that caused this lift.

    A cartório scan carries an ONR digital-signature stamp as real,
    selectable text. Accepting it returned a few hundred characters of
    validation URL as the whole matrícula, with status "concluida" — total
    data loss wearing a success badge.
    """

    @pytest.mark.asyncio
    async def test_a_signature_stamp_is_not_a_transcription(self, monkeypatch) -> None:
        vision = _Vision()
        t = _transcriber(
            monkeypatch, _camada(*[(ONR_STAMP, False)] * 3),
            num_paginas=3, vision=vision,
        )
        out = await t.transcribe(b"%PDF")

        assert vision.pages == [1, 2, 3], "a scan must reach vision"
        assert "assinador-web" not in out.text
        assert out.text == "OCR PAGINA 1\n\nOCR PAGINA 2\n\nOCR PAGINA 3"
        assert out.paginas_por_visao == (1, 2, 3)

    @pytest.mark.asyncio
    async def test_a_mixed_document_pays_only_where_needed(self, monkeypatch) -> None:
        """A typeset body with a scanned averbação stapled on is ordinary in
        Brazilian registries. Whole-document routing has to pick one rung for
        both halves; per-page routing does not."""
        vision = _Vision(texto=lambda n: "AVERBACAO ESCANEADA")
        t = _transcriber(
            monkeypatch,
            _camada(("CORPO", True), (ONR_STAMP, False), ("FECHAMENTO", True)),
            num_paginas=3, vision=vision,
        )
        out = await t.transcribe(b"%PDF")

        assert len(vision.pages) == 1, "billed for pages it could read for free"
        assert out.text == "CORPO\n\nAVERBACAO ESCANEADA\n\nFECHAMENTO"
        assert out.paginas_por_camada == (1, 3)
        assert out.paginas_por_visao == (2,)

    @pytest.mark.asyncio
    async def test_degraded_classification_sends_every_page_to_vision(
        self, monkeypatch
    ) -> None:
        """Without PyMuPDF the classifier returns one synthetic page for the
        whole document. Mixing that with page-scoped OCR would attribute the
        document's entire text to page 1, so nothing is taken for free."""
        vision = _Vision()
        degraded = PdfTextLayer(
            pages=(PdfPage(number=1, text="stamp", is_substantive=False, reason="x"),),
            tooling_available=True,
        )
        t = _transcriber(monkeypatch, degraded, num_paginas=4, vision=vision)
        out = await t.transcribe(b"%PDF")

        assert vision.pages == [1, 2, 3, 4]
        assert out.num_paginas == 4


class TestFailuresAreValuesNotExceptions:
    """Transcription runs detached in background jobs — an exception would
    surface nowhere and strand the document mid-pipeline."""

    @pytest.mark.asyncio
    async def test_a_corrupt_pdf_reports_no_pages(self, monkeypatch) -> None:
        import noctusai_lib.integrations.documents.transcription as mod

        monkeypatch.setattr(mod, "_contar_paginas", lambda b: 0)
        out = await LadderDocumentTranscriber().transcribe(b"not a pdf")
        assert out.error == "no_pages" and not out.ok

    @pytest.mark.asyncio
    async def test_a_dropped_page_fails_loudly_rather_than_shipping_short(
        self, monkeypatch
    ) -> None:
        import noctusai_lib.integrations.documents.transcription as mod

        monkeypatch.setattr(mod, "_contar_paginas", lambda b: 2)
        monkeypatch.setattr(
            "noctusai_lib.integrations.media.classify_pdf_text_layer",
            lambda b: _camada((ONR_STAMP, False), (ONR_STAMP, False)),
        )
        monkeypatch.setattr(mod, "_pdf_to_images", lambda b, paginas, dpi: {1: b"png"})
        out = await LadderDocumentTranscriber(analyze=_Vision()).transcribe(b"%PDF")

        assert out.error == "rasterize_failed"
        assert "page 2 of 2" in (out.error_message or "")

    @pytest.mark.asyncio
    async def test_a_missing_credential_is_a_code_not_a_crash(
        self, monkeypatch
    ) -> None:
        import noctusai_lib.integrations.documents.transcription as mod

        monkeypatch.setattr(mod, "_contar_paginas", lambda b: 1)
        monkeypatch.setattr(
            "noctusai_lib.integrations.media.classify_pdf_text_layer",
            lambda b: _camada((ONR_STAMP, False)),
        )
        monkeypatch.setattr(
            "noctusai_lib.config.credentials.resolve_credential",
            lambda *a, **k: None,
        )
        out = await LadderDocumentTranscriber().transcribe(b"%PDF")
        assert out.error == "missing_credentials"
        assert out.num_paginas == 1, "the page count is known even on failure"

    @pytest.mark.asyncio
    async def test_a_runaway_document_is_capped(self, monkeypatch) -> None:
        vision = _Vision()
        t = _transcriber(
            monkeypatch, _camada(*[(ONR_STAMP, False)] * 5),
            num_paginas=5, vision=vision, max_vision_pages=3,
        )
        out = await t.transcribe(b"%PDF")

        assert out.error == "too_many_vision_pages"
        assert vision.pages == [], "the cap must fire BEFORE any billing"

    @pytest.mark.asyncio
    async def test_an_unexpected_error_comes_back_as_a_value(
        self, monkeypatch
    ) -> None:
        import noctusai_lib.integrations.documents.transcription as mod

        def explode(_b):
            raise RuntimeError("mupdf exploded")

        monkeypatch.setattr(mod, "_contar_paginas", explode)
        out = await LadderDocumentTranscriber().transcribe(b"%PDF")
        assert out.error == "transcription_failed"
        assert "mupdf exploded" in (out.error_message or "")


class TestVisionCanBeDisabled:
    """`max_vision_pages=0` — the free half of the ladder, for consumers on a
    timer who have not opted into per-page billing (`certidoes_service`)."""

    @pytest.mark.asyncio
    async def test_the_readable_half_still_comes_back(self, monkeypatch) -> None:
        vision = _Vision()
        t = _transcriber(
            monkeypatch, _camada(("CORPO", True), (ONR_STAMP, False)),
            num_paginas=2, vision=vision, max_vision_pages=0,
        )
        out = await t.transcribe(b"%PDF")

        assert vision.pages == []
        assert out.text == "CORPO"
        assert out.error == "vision_disabled", (
            "a partial read must never look like a whole one"
        )
        assert out.ok is False

    @pytest.mark.asyncio
    async def test_a_fully_scanned_document_yields_nothing(self, monkeypatch) -> None:
        t = _transcriber(
            monkeypatch, _camada((ONR_STAMP, False)),
            num_paginas=1, max_vision_pages=0,
        )
        out = await t.transcribe(b"%PDF")
        assert out.text == "" and out.error == "vision_disabled"


class TestTheProtocolShape:
    def test_both_adapters_satisfy_the_protocol(self) -> None:
        from noctusai_lib.integrations.documents import DocumentTranscriber

        assert isinstance(FakeDocumentTranscriber(), DocumentTranscriber)
        assert isinstance(LadderDocumentTranscriber(), DocumentTranscriber)

    def test_an_empty_transcription_is_falsy_but_not_an_error(self) -> None:
        assert Transcription().text == ""
        assert Transcription().ok is True

    @pytest.mark.asyncio
    async def test_source_is_recorded_per_page(self, monkeypatch) -> None:
        t = _transcriber(
            monkeypatch, _camada(("CORPO", True), (ONR_STAMP, False)), num_paginas=2
        )
        out = await t.transcribe(b"%PDF")
        assert [p.source for p in out.pages] == [TextSource.TEXT_LAYER, TextSource.OCR]


# ---------------------------------------------------------------------------
# The manual provider switch
# ---------------------------------------------------------------------------
#
# Added 2026-09-04 so an operator whose OpenAI account runs out of credit can
# keep transcribing by pointing the vision rung at Anthropic. It is a MANUAL
# switch by explicit decision: nothing here fails over, because a silent
# vendor change would alter which model transcribed a legal document with no
# record that it happened.


class TestTheVisionProviderIsSelectable:
    @pytest.mark.asyncio
    async def test_openai_stays_the_default(self, monkeypatch) -> None:
        """An existing consumer that passes nothing must not move vendors."""
        vision = _Vision()
        t = _transcriber(
            monkeypatch, _camada(("", False)), num_paginas=1, vision=vision
        )
        await t.transcribe(b"%PDF")

        assert vision.calls == [("openai", "gpt-4.1-mini")]

    @pytest.mark.asyncio
    async def test_selecting_anthropic_selects_its_model_too(
        self, monkeypatch
    ) -> None:
        """🔴 The pair must travel together.

        `gpt-4.1-mini` sent to Anthropic is a 404 that reads like a broken
        key. Selecting the provider has to select the model, or the switch
        ships a failure mode instead of a feature.
        """
        vision = _Vision()
        t = _transcriber(
            monkeypatch,
            _camada(("", False)),
            num_paginas=1,
            vision=vision,
            provider="anthropic",
        )
        await t.transcribe(b"%PDF")

        assert vision.calls == [("anthropic", "claude-opus-5")]

    @pytest.mark.asyncio
    async def test_an_explicit_model_still_wins(self, monkeypatch) -> None:
        """The pairing is a default, not a lock — a consumer may pin one."""
        vision = _Vision()
        t = _transcriber(
            monkeypatch,
            _camada(("", False)),
            num_paginas=1,
            vision=vision,
            provider="anthropic",
            ocr_model="claude-haiku-4-5",
        )
        await t.transcribe(b"%PDF")

        assert vision.calls == [("anthropic", "claude-haiku-4-5")]

    def test_every_provider_in_the_map_has_a_model(self) -> None:
        """A provider without a pinned model would fall back to OpenAI's,
        which is the exact cross-vendor mismatch this map exists to stop."""
        assert OCR_MODELS
        assert all(model for model in OCR_MODELS.values())
        assert DEFAULT_VISION_PROVIDER in OCR_MODELS

    @pytest.mark.asyncio
    async def test_the_selected_providers_key_is_the_one_checked(
        self, monkeypatch
    ) -> None:
        """🔴 NOT OpenAI's key regardless of selection.

        Checking the wrong vendor's credential would refuse work the
        configured vendor can do — and report it as `missing_credentials`,
        sending the operator to fix a key that was never going to be used.
        """
        pedidos: list[str] = []

        def _resolve(key, org_id=None):
            pedidos.append(key)
            return "sk-ant-live" if key == "anthropic_api_key" else None

        monkeypatch.setattr(
            "noctusai_lib.config.credentials.resolve_credential", _resolve
        )
        monkeypatch.setattr(
            "noctusai_lib.integrations.llm.analyze_image",
            _Vision(),
            raising=False,
        )
        t = _transcriber(
            monkeypatch,
            _camada(("", False)),
            num_paginas=1,
            provider="anthropic",
        )
        t._analyze = None  # force the lazy resolution path under test

        out = await t.transcribe(b"%PDF")

        assert pedidos == ["anthropic_api_key"]
        assert out.ok, out.error_message

    @pytest.mark.asyncio
    async def test_a_missing_key_names_the_provider(self, monkeypatch) -> None:
        """With a switch in front of it, "no credential" is ambiguous until
        the message says WHICH vendor was selected."""
        monkeypatch.setattr(
            "noctusai_lib.config.credentials.resolve_credential",
            lambda key, org_id=None: None,
        )
        t = _transcriber(
            monkeypatch,
            _camada(("", False)),
            num_paginas=1,
            provider="anthropic",
        )
        t._analyze = None

        out = await t.transcribe(b"%PDF")

        assert out.ok is False
        assert out.error == "missing_credentials"
        assert "anthropic" in (out.error_message or "")

    def test_the_factory_forwards_the_selection(self) -> None:
        t = make_document_transcriber(real=True, provider="anthropic")
        assert isinstance(t, LadderDocumentTranscriber)
        assert t._provider == "anthropic"
        assert t._ocr_model == OCR_MODELS["anthropic"]
