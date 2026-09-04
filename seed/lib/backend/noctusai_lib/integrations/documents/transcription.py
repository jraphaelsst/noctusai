"""Whole-document transcription — Protocol + Fake + Real + factory.

WHY THIS IS NOT `DocumentTextLadder`
------------------------------------
The ladder answers "what text is in these bytes, and how sure can you be of
it" for an EXTRACTOR — something that wants one field (a birthdate, a
matrícula number) and stops as soon as it can read it. Its vision rung
delegates to `OpenAIMediaResolver`, which rasterizes at most
`_RASTERIZE_MAX_PAGES` (3) and describes only `page_images[0]`. That is the
right shape for "what is this document", and the wrong shape for "give me
every word of it": a 7-page matrícula would come back as a prose summary of
its first page.

Transcription is the other question. It is page-complete by definition, it
has to interleave rungs (a typeset body with a scanned averbação stapled on
is ordinary in Brazilian registries), and its output is the document rather
than a description of one.

WHY IT IS IN THE SEED
---------------------
It was `erp-imobiliario/app/services/matricula_service.py`, product-local,
and every lesson the seed's document family learned had to be re-learned
there one incident at a time — rung 1 on 2026-08-24, per-page routing and
the scan-stamp defect on 2026-08-25. Two more consumers are known
(`certidoes_service`, and social-wiring's inbound-document path), which is
N=3 on a capability with real money attached.

WHAT STAYS WITH THE PRODUCT
---------------------------
Persistence and status. This module takes bytes and returns a
`Transcription`; it does not know about `matricula_extracoes`, background
jobs, or how a product phrases a failure to its users. Errors come back as
machine codes (`error`) plus a developer-facing `error_message`, and the
product renders whatever its users should read — the same split
`ResolvedMedia` uses.

NEVER RAISES
------------
Transcription runs in background jobs, detached from the request that
triggered it, so an exception would surface nowhere and strand the document
mid-pipeline. Every failure is returned as a value.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional, Protocol, runtime_checkable

from noctusai_lib.integrations.documents.types import TextSource

logger = logging.getLogger(__name__)

#: Rasterization DPI for the vision rung. 200 balances legibility against
#: image-token cost — the canonical answer for registry documents, which are
#: dense small print. Override per-consumer only with a reason.
RENDER_DPI = 200

#: Which vendor's vision model reads a scanned page, when the consumer does
#: not say. OpenAI stays the default so no existing consumer changes
#: behaviour by upgrading.
DEFAULT_VISION_PROVIDER = "openai"

#: Pinned OCR model PER PROVIDER, separate from any chat-model pin a product
#: carries. Tuned for page throughput at transcription quality; tune here,
#: not at the call site.
#:
#: 🔴 THE MODEL IS NOT PORTABLE ACROSS PROVIDERS — that is why this is a
#: mapping and not a string. `gpt-4.1-mini` sent to Anthropic is a 404, and
#: a consumer that switches provider without switching model gets a failure
#: that reads like a broken key. Selecting a provider MUST select its model
#: unless the caller overrides both.
OCR_MODELS: dict[str, str] = {
    "openai": "gpt-4.1-mini",
    # Registry documents are dense small print where a misread digit names a
    # DIFFERENT PROPERTY (see `matricula_extractor`'s header), so the
    # Anthropic side is pinned to the strongest current model rather than
    # the cheapest. A 3-page matrícula costs on the order of cents.
    # `claude-sonnet-5` / `claude-haiku-4-5` are the cheaper current-
    # generation swaps if a consumer decides the tradeoff differently.
    "anthropic": "claude-opus-5",
}

#: Back-compat alias for the OpenAI pin. Consumers that imported this before
#: provider selection existed keep working unchanged.
OCR_MODEL = OCR_MODELS["openai"]

#: Deliberately anti-helpful. A transcription prompt that invites the model
#: to tidy anything gets a tidied document, and a matrícula that has been
#: silently corrected is worse than one that is visibly hard to read.
OCR_PROMPT = (
    "Extract the exact text from the provided image. "
    "Return only the text content exactly as it appears in the document, "
    "without corrections, formatting changes, or any modifications."
)

#: Cap on vision calls for one document. A runaway PDF (a 400-page bundle
#: uploaded by mistake) would otherwise bill page-by-page to completion.
#: Exceeding it is an error, NOT a silent truncation — a half-transcribed
#: matrícula that reports success is the failure mode this whole module
#: family exists to prevent.
#:
#: Setting it to 0 means "text layer only": rung 2 never fires, and a
#: document needing it comes back with whatever rung 1 could read plus
#: `error="vision_disabled"`. That is for consumers who want the free,
#: exact half of the ladder without opting into per-page billing — and it
#: is an ERROR rather than a quiet empty string, because "this document was
#: not transcribed" must never look like "this document was blank".
MAX_VISION_PAGES = 40


def _classify_failure(exc: Exception) -> str:
    """Name the failure when we can, so the consumer can say something useful.

    The catch-all above exists because a background job must not die — but
    "transcription_failed" is the same word for a corrupt PDF, an expired
    key, and an unpaid bill, and only one of those is fixed by re-uploading.
    A consumer can only write an actionable sentence for a cause it can
    distinguish.

    `insufficient_quota` is broken out first because it is the one an
    operator can fix in two minutes and would otherwise never guess: the
    provider answers HTTP 429, which reads as "too busy, try later", when it
    actually means the account is out of credit and retrying will never
    work. Found in prod 2026-09-03 — a scanned matrícula surfaced as
    "Erro inesperado: HTTP 429" with no hint that billing was the cause.

    Rate limiting keeps its own code: same status, opposite advice (waiting
    DOES help).
    """
    text = f"{type(exc).__name__}: {exc}".lower()
    if any(s in text for s in (
        "insufficient_quota", "credit_balance_exhausted", "no credits remaining",
        "exceeded your current quota", "billing",
    )):
        return "insufficient_quota"
    if "rate limit" in text or "rate_limit" in text or "429" in text:
        return "rate_limited"
    if any(s in text for s in ("invalid_api_key", "incorrect api key", "401", "unauthorized")):
        return "invalid_credentials"
    return "transcription_failed"



@dataclass(frozen=True)
class TranscribedPage:
    """One page, its text, and which rung produced it."""

    number: int  # 1-based, matches what a human sees in a PDF reader
    text: str
    source: TextSource


@dataclass(frozen=True)
class Transcription:
    """The whole document, or a truthful account of why not.

    `num_paginas` is the page count of the PDF itself, not of `pages` —
    they differ exactly when transcription failed partway, and a consumer
    writing "3 of 7 pages" needs both numbers to say so.
    """

    pages: tuple[TranscribedPage, ...] = ()
    num_paginas: int = 0
    error: Optional[str] = None
    error_message: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None

    @property
    def text(self) -> str:
        """The document, page order, blank pages dropped."""
        return "\n\n".join(p.text for p in self.pages if p.text)

    @property
    def paginas_por_visao(self) -> tuple[int, ...]:
        """Pages that cost a vision call — the bill, and the pages whose
        transcription is approximate rather than exact."""
        return tuple(p.number for p in self.pages if p.source is TextSource.OCR)

    @property
    def paginas_por_camada(self) -> tuple[int, ...]:
        """Pages read exactly, for free, from the PDF's own text layer."""
        return tuple(p.number for p in self.pages if p.source is TextSource.TEXT_LAYER)


@runtime_checkable
class DocumentTranscriber(Protocol):
    """Bytes → the document's full text. Never raises."""

    async def transcribe(
        self,
        content: bytes,
        *,
        mimetype: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> Transcription:
        ...


class FakeDocumentTranscriber:
    """Deterministic transcriber — the dev/test default.

    Returns obviously-synthetic text so a fixture that leaks onto a real
    screen is recognisable as fake rather than plausible.
    """

    PAGINAS = 2

    async def transcribe(
        self,
        content: bytes,
        *,
        mimetype: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> Transcription:
        if not content:
            return Transcription(
                error="empty_document", error_message="no bytes to transcribe"
            )
        return Transcription(
            pages=tuple(
                TranscribedPage(
                    number=n,
                    text=f"[TRANSCRICAO FALSA] pagina {n} de {self.PAGINAS}",
                    source=TextSource.TEXT_LAYER,
                )
                for n in range(1, self.PAGINAS + 1)
            ),
            num_paginas=self.PAGINAS,
        )


class LadderDocumentTranscriber:
    """Text-layer-first, vision-second, decided PER PAGE.

    Construct via `make_document_transcriber(real=True)`.
    """

    def __init__(
        self,
        *,
        org_id: Optional[str] = None,
        provider: Optional[str] = None,
        ocr_model: Optional[str] = None,
        ocr_prompt: str = OCR_PROMPT,
        render_dpi: int = RENDER_DPI,
        max_vision_pages: int = MAX_VISION_PAGES,
        analyze=None,
    ) -> None:
        self._org_id = org_id
        self._provider = provider or DEFAULT_VISION_PROVIDER
        # Model follows provider unless the caller pinned one explicitly —
        # see `OCR_MODELS`. Defaulting the parameter to a string instead
        # would silently send OpenAI's model name to Anthropic.
        self._ocr_model = ocr_model or OCR_MODELS.get(
            self._provider, OCR_MODELS[DEFAULT_VISION_PROVIDER]
        )
        self._ocr_prompt = ocr_prompt
        self._render_dpi = render_dpi
        self._max_vision_pages = max_vision_pages
        # Injected in tests; resolved lazily otherwise so importing this
        # module never drags in the LLM stack.
        self._analyze = analyze

    async def transcribe(
        self,
        content: bytes,
        *,
        mimetype: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> Transcription:
        try:
            return await self._transcribe(content)
        except Exception as exc:  # noqa: BLE001 - background job must not die
            logger.warning("transcription failed: %s", exc)
            return Transcription(
                error=_classify_failure(exc), error_message=str(exc)
            )

    async def _transcribe(self, content: bytes) -> Transcription:
        if not content:
            return Transcription(
                error="empty_document", error_message="no bytes to transcribe"
            )

        num_paginas = _contar_paginas(content)
        if num_paginas == 0:
            return Transcription(
                error="no_pages",
                error_message="PDF has no readable pages (corrupt, or not a PDF)",
            )

        # ── Rung 1: the PDF's own text layer ─────────────────────────
        #
        # Runs BEFORE the credential check on purpose: a digitally-issued
        # document needs no key, no vision call and no rasterization, so a
        # consumer that has never configured a provider can still transcribe
        # one. Checking the key first would refuse work we can do.
        from noctusai_lib.integrations.media import classify_pdf_text_layer

        camada = classify_pdf_text_layer(content)
        textos = _texto_confiavel_por_pagina(camada, num_paginas)
        paginas_para_visao = [n for n in range(1, num_paginas + 1) if n not in textos]

        if not paginas_para_visao:
            return Transcription(
                pages=tuple(
                    TranscribedPage(
                        number=n, text=textos[n], source=TextSource.TEXT_LAYER
                    )
                    for n in sorted(textos)
                ),
                num_paginas=num_paginas,
            )

        # ── Rung 2: rasterize → vision, for the pages rung 1 missed ───
        if self._max_vision_pages == 0:
            # Partial pages are returned deliberately: a consumer that asked
            # for the free half should still get it, and `ok` is False so it
            # cannot mistake a partial read for the whole document.
            return Transcription(
                pages=tuple(
                    TranscribedPage(
                        number=n, text=textos[n], source=TextSource.TEXT_LAYER
                    )
                    for n in sorted(textos)
                ),
                num_paginas=num_paginas,
                error="vision_disabled",
                error_message=(
                    f"{len(paginas_para_visao)} of {num_paginas} page(s) need "
                    "vision, which this transcriber has disabled"
                ),
            )

        if len(paginas_para_visao) > self._max_vision_pages:
            return Transcription(
                num_paginas=num_paginas,
                error="too_many_vision_pages",
                error_message=(
                    f"{len(paginas_para_visao)} pages need vision, over the "
                    f"{self._max_vision_pages}-page cap"
                ),
            )

        analyze = self._get_analyze()
        if analyze is None:
            return Transcription(
                num_paginas=num_paginas,
                error="missing_credentials",
                # Names the provider: with a manual switch in front of this,
                # "no credential" is ambiguous until you know WHICH vendor
                # was selected — the operator may have configured the other.
                error_message=(
                    f"no {self._provider} credential resolved; scanned pages "
                    "need a vision call"
                ),
            )

        images = _pdf_to_images(content, paginas_para_visao, self._render_dpi)
        for numero in paginas_para_visao:
            img = images.get(numero)
            if img is None:
                # Dropping a page silently would ship a short document that
                # reports success — the exact shape this family forbids.
                return Transcription(
                    num_paginas=num_paginas,
                    error="rasterize_failed",
                    error_message=f"could not rasterize page {numero} of {num_paginas}",
                )
            textos[numero] = await analyze(
                img,
                self._ocr_prompt,
                model=self._ocr_model,
                provider=self._provider,
                org_id=self._org_id,
                max_tokens=4096,
            )
            logger.info("transcription: page %d/%d done", numero, num_paginas)

        por_visao = set(paginas_para_visao)
        return Transcription(
            pages=tuple(
                TranscribedPage(
                    number=n,
                    text=textos[n],
                    source=TextSource.OCR if n in por_visao else TextSource.TEXT_LAYER,
                )
                for n in sorted(textos)
            ),
            num_paginas=num_paginas,
        )

    def _get_analyze(self):
        """Resolve the vision entry point, or None when unusable.

        Returning None rather than raising is what lets `missing_credentials`
        reach the consumer as a value it can render.

        The key checked is the SELECTED provider's (`anthropic_api_key` when
        the operator switched to Claude), through the same
        `f"{provider}_api_key"` naming `LLMConfig.key_provider` uses — so
        one saved credential satisfies both this pre-check and the call
        itself. Checking OpenAI's key regardless of provider would refuse
        work the configured vendor can do.
        """
        if self._analyze is not None:
            return self._analyze
        from noctusai_lib.config.credentials import resolve_credential

        if not resolve_credential(f"{self._provider}_api_key", self._org_id):
            return None
        from noctusai_lib.integrations.llm import analyze_image

        self._analyze = analyze_image
        return self._analyze


def _contar_paginas(pdf_bytes: bytes) -> int:
    """Page count without rendering anything. 0 for bytes we cannot open."""
    try:
        import fitz  # type: ignore  # PyMuPDF

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception:
        logger.debug("transcription: could not open PDF", exc_info=True)
        return 0
    try:
        return doc.page_count
    finally:
        doc.close()


def _texto_confiavel_por_pagina(camada, num_paginas: int) -> dict[int, str]:
    """Page number → text we can trust without a vision call.

    Per-page routing only works when the classifier actually saw every page.
    Without PyMuPDF it degrades to one synthetic page covering the whole
    document (documented on `classify_pdf_text_layer`), and mixing that with
    page-scoped OCR would attribute the entire document's text to page 1. So
    when the counts disagree we take nothing for free and send every page to
    vision — costlier, but never wrong.
    """
    if len(camada.pages) != num_paginas:
        return {}
    return {p.number: p.text for p in camada.pages if p.is_substantive}


def _pdf_to_images(
    pdf_bytes: bytes, paginas: list[int], render_dpi: int
) -> dict[int, bytes]:
    """Rasterize the requested pages to PNG, keyed by 1-based page number.

    Rendering only what rung 2 needs matters twice: a page we already read is
    wasted CPU here and wasted money one call later. Keying by page number is
    what lets the caller interleave OCR'd and text-layer pages in order.
    """
    import fitz  # type: ignore  # PyMuPDF

    images: dict[int, bytes] = {}
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        zoom = render_dpi / 72  # 72 is the default PDF DPI
        matrix = fitz.Matrix(zoom, zoom)
        alvo = set(paginas)
        for index in range(doc.page_count):
            numero = index + 1
            if numero not in alvo:
                continue
            images[numero] = doc[index].get_pixmap(matrix=matrix).tobytes("png")
    finally:
        doc.close()
    return images


def make_document_transcriber(
    *,
    real: bool = False,
    org_id: Optional[str] = None,
    provider: Optional[str] = None,
    ocr_model: Optional[str] = None,
    ocr_prompt: str = OCR_PROMPT,
    render_dpi: int = RENDER_DPI,
    max_vision_pages: int = MAX_VISION_PAGES,
) -> DocumentTranscriber:
    """Return a document transcriber.

    Fake-by-default is the posture every seed IO module takes: a consumer
    that forgets to configure the real adapter gets deterministic behaviour,
    not a surprise LLM bill or an import error in a slim image.

    Args:
        real: Select `LadderDocumentTranscriber` (text layer → vision, per
            page). Imported lazily so the Fake path stays importable without
            PyMuPDF or the LLM stack.
        org_id: Forwarded to the LLM entry points for per-org key resolution
            and budget accounting.
        provider: Which vendor reads the scanned pages (`"openai"` /
            `"anthropic"`). `None` keeps `DEFAULT_VISION_PROVIDER`. This is a
            MANUAL selection — nothing here fails over to the other vendor,
            because a silent switch would change which model transcribed a
            legal document without anyone being told.
        ocr_model / ocr_prompt / render_dpi: Vision-rung overrides. The
            defaults are the canonical answer for dense registry documents,
            not one consumer's preference. Leave `ocr_model` as `None` unless
            you are pinning a model deliberately — it then follows `provider`
            through `OCR_MODELS`, which is what keeps the two in step.
        max_vision_pages: Cap on vision calls for a single document.
    """
    if not real:
        return FakeDocumentTranscriber()

    return LadderDocumentTranscriber(
        org_id=org_id,
        provider=provider,
        ocr_model=ocr_model,
        ocr_prompt=ocr_prompt,
        render_dpi=render_dpi,
        max_vision_pages=max_vision_pages,
    )


__all__ = [
    "DEFAULT_VISION_PROVIDER",
    "DocumentTranscriber",
    "FakeDocumentTranscriber",
    "LadderDocumentTranscriber",
    "MAX_VISION_PAGES",
    "OCR_MODEL",
    "OCR_MODELS",
    "OCR_PROMPT",
    "RENDER_DPI",
    "TranscribedPage",
    "Transcription",
    "make_document_transcriber",
]
