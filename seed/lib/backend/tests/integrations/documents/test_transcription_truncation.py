"""A truncated vision reply must never pass as a complete page.

Measured live 2026-09-27: a dense page (a Guia de ITBI) hit exactly
`max_tokens=4096` on Sonnet and the reply came back cut off mid-page — with
nothing here checking the provider's stop reason, that half-page was
treated as the finished transcription. These tests exercise the fix
end-to-end through `LadderDocumentTranscriber`, via the `analyze=` DI seam
every other transcriber test already uses — no network, no monkeypatch of
this module's own guards.
"""
from __future__ import annotations

import pytest

from noctusai_lib.integrations.documents.transcription import (
    ERROR_TRANSCRICAO_TRUNCADA,
    VISION_MAX_TOKENS,
    VISION_MAX_TOKENS_RETRY,
    LadderDocumentTranscriber,
)
from noctusai_lib.integrations.llm.vision_types import VisionResult
from noctusai_lib.integrations.media import PdfPage, PdfTextLayer


def _camada_sem_texto(num_paginas: int) -> PdfTextLayer:
    """One page, no trustworthy text — routes straight to the vision rung."""
    return PdfTextLayer(
        pages=tuple(
            PdfPage(number=n, text="", is_substantive=False, reason="stub")
            for n in range(1, num_paginas + 1)
        ),
        tooling_available=True,
    )


class _ScriptedVision:
    """The `analyze=` DI seam's stand-in for these tests.

    `script` is one `(text, truncated)` pair PER CALL, consumed in order —
    a page that truncates once and then succeeds on retry scripts two
    entries; a page that never recovers scripts two truncated entries.
    Records every call's `max_tokens` + `return_metadata` so a test can
    assert the retry actually asked for a bigger cap, not just that it
    asked again.
    """

    def __init__(self, script: list[tuple[str, bool]]):
        self._script = list(script)
        self.calls: list[dict] = []

    async def __call__(
        self,
        image,
        prompt,
        *,
        model=None,
        provider=None,
        org_id=None,
        max_tokens=None,
        return_metadata: bool = False,
        **kwargs,
    ):
        self.calls.append(
            {"max_tokens": max_tokens, "return_metadata": return_metadata}
        )
        texto, truncado = self._script.pop(0)
        if return_metadata:
            return VisionResult(text=texto, truncated=truncado)
        return texto


def _transcriber(monkeypatch, vision: _ScriptedVision, *, num_paginas: int = 1):
    import noctusai_lib.integrations.documents.transcription as mod

    monkeypatch.setattr(mod, "_contar_paginas", lambda b: num_paginas)
    monkeypatch.setattr(
        "noctusai_lib.integrations.media.classify_pdf_text_layer",
        lambda b: _camada_sem_texto(num_paginas),
    )
    monkeypatch.setattr(
        mod, "_pdf_to_images", lambda b, paginas, dpi: {n: b"png" for n in paginas}
    )
    return LadderDocumentTranscriber(analyze=vision)


class TestTruncatedThenRetrySucceeds:
    @pytest.mark.asyncio
    async def test_retry_lands_the_full_page(self, monkeypatch) -> None:
        vision = _ScriptedVision(
            [("PAGINA CORTADA NA MET", True), ("PAGINA COMPLETA", False)]
        )
        t = _transcriber(monkeypatch, vision)

        out = await t.transcribe(b"%PDF")

        assert out.ok, out.error_message
        assert out.text == "PAGINA COMPLETA"
        assert len(vision.calls) == 2, "one call, one retry — never more"

    @pytest.mark.asyncio
    async def test_retry_asks_for_the_bigger_cap(self, monkeypatch) -> None:
        vision = _ScriptedVision([("cortada", True), ("completa", False)])
        t = _transcriber(monkeypatch, vision)

        await t.transcribe(b"%PDF")

        assert [c["max_tokens"] for c in vision.calls] == [
            VISION_MAX_TOKENS,
            VISION_MAX_TOKENS_RETRY,
        ]
        assert all(c["return_metadata"] is True for c in vision.calls)


class TestTruncatedTwiceIsANamedError:
    @pytest.mark.asyncio
    async def test_still_truncated_after_retry_is_the_named_error(
        self, monkeypatch
    ) -> None:
        vision = _ScriptedVision([("cortada uma vez", True), ("cortada de novo", True)])
        t = _transcriber(monkeypatch, vision)

        out = await t.transcribe(b"%PDF")

        assert not out.ok
        assert out.error == ERROR_TRANSCRICAO_TRUNCADA
        assert "page 1 of 1" in out.error_message
        # Never a half page reported as complete text.
        assert out.pages == ()
        assert out.text == ""

    @pytest.mark.asyncio
    async def test_only_two_calls_are_made_never_a_loop(self, monkeypatch) -> None:
        vision = _ScriptedVision([("a", True), ("b", True)])
        t = _transcriber(monkeypatch, vision)

        await t.transcribe(b"%PDF")

        assert len(vision.calls) == 2


class TestNonTruncatedPageIsUnchanged:
    @pytest.mark.asyncio
    async def test_a_normal_reply_costs_exactly_one_call(self, monkeypatch) -> None:
        vision = _ScriptedVision([("texto normal da pagina", False)])
        t = _transcriber(monkeypatch, vision)

        out = await t.transcribe(b"%PDF")

        assert out.ok
        assert out.text == "texto normal da pagina"
        assert len(vision.calls) == 1
        assert vision.calls[0]["max_tokens"] == VISION_MAX_TOKENS

    @pytest.mark.asyncio
    async def test_a_plain_string_reply_is_read_as_not_truncated(
        self, monkeypatch
    ) -> None:
        """A caller-injected `analyze` that accepts `return_metadata` but
        keeps returning a bare string (every transcriber test written
        before this feature existed) must be read the same as before:
        `truncated=False`, one call, page complete."""

        async def analyze(image, prompt, *, model=None, provider=None, org_id=None,
                           max_tokens=None, return_metadata=False, **kwargs):
            return "texto de sempre"

        import noctusai_lib.integrations.documents.transcription as mod

        monkeypatch.setattr(mod, "_contar_paginas", lambda b: 1)
        monkeypatch.setattr(
            "noctusai_lib.integrations.media.classify_pdf_text_layer",
            lambda b: _camada_sem_texto(1),
        )
        monkeypatch.setattr(
            mod, "_pdf_to_images", lambda b, paginas, dpi: {n: b"png" for n in paginas}
        )
        out = await LadderDocumentTranscriber(analyze=analyze).transcribe(b"%PDF")

        assert out.ok
        assert out.text == "texto de sempre"
