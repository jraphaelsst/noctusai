"""Whole-document transcription — Protocol + Fake + Real + factory.

WHY THIS IS NOT `DocumentTextLadder`
------------------------------------
The ladder answers "what text is in these bytes, and how sure can you be of
it" for an EXTRACTOR — something that wants one field (a birthdate, a
matrícula number) and stops as soon as it can read it. Its vision rung
delegates to `RealMediaResolver`, which describes what a scanned page shows
rather than transcribing it verbatim. That is the right shape for "what is
this document", and the wrong shape for "give me every word of it": a
7-page matrícula needs its exact text, not a prose description of it.

🔴 AS OF 2026-09-20 `RealMediaResolver._resolve_pdf` DELEGATES ITS OWN
SCANNED-DOCUMENT BRANCH TO THIS MODULE (`make_document_transcriber`) —
see that method. The relationship above still holds for WHY the two
modules exist (a description vs. a transcription are different jobs); it
no longer means `RealMediaResolver` reads only its first page. Prefer THIS
module directly when a caller can (as `identity`/`matricula` extraction and
`certidoes`/`matriculas` already do) — going through the resolver adds an
extra hop for the identical result.

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
import re
from dataclasses import dataclass
from typing import Callable, Optional, Protocol, runtime_checkable

from noctusai_lib.integrations.documents.formatting import FormatRange
from noctusai_lib.integrations.documents.providers import (
    DEFAULT_DOCUMENT_PROVIDER,
    OCR_MODELS,
)
from noctusai_lib.integrations.llm.credit_probe import QUOTA_MARKERS
from noctusai_lib.integrations.documents.types import TextSource

logger = logging.getLogger(__name__)

#: Rasterization DPI for the vision rung. 200 balances legibility against
#: image-token cost — the canonical answer for registry documents, which are
#: dense small print. Override per-consumer only with a reason.
RENDER_DPI = 200

#: Which vendor's vision model reads a scanned page, when the consumer does
#: not say — the seed's canonical DOCUMENT provider (Anthropic since
#: 2026-09-22). The pins themselves live in ONE place,
#: `documents.providers` — see its docstring for the measurement behind them.
DEFAULT_VISION_PROVIDER = DEFAULT_DOCUMENT_PROVIDER

#: Back-compat alias for the OpenAI pin. Consumers that imported this before
#: provider selection existed keep working unchanged.
OCR_MODEL = OCR_MODELS["openai"]

#: Deliberately anti-helpful. A transcription prompt that invites the model
#: to tidy anything gets a tidied document, and a matrícula that has been
#: silently corrected is worse than one that is visibly hard to read.
#:
#: Asks for two markers ON TOP of the verbatim text, not instead of it —
#: `**bold**` and `<u>underline</u>`, combinable in either order. `parse_markup`
#: is this prompt's sole consumer: any change to the markers here must change
#: it too, or a scanned page starts rendering literal asterisks.
OCR_PROMPT = (
    "Extract the exact text from the provided image. "
    "Return only the text content exactly as it appears in the document, "
    "without corrections, formatting changes, or any modifications. "
    "In addition, mark bold text by wrapping it in double asterisks "
    "(**like this**) and underlined text by wrapping it in <u></u> tags "
    "(<u>like this</u>); text that is both bold and underlined may combine "
    "the two markers in either order (for example **<u>like this</u>**). "
    "Do not use any other markup, and do not mark text that is neither bold "
    "nor underlined."
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


@dataclass(frozen=True)
class RenderDpiPolicy:
    """Page-count-aware, byte-budget-capped render-DPI selection.

    `RENDER_DPI` (200, a flat int) is right for what this module was built
    for — dense registry print, where every page is worth the same care.
    It is measurably wrong for a document whose fields live in a SMALL
    region of one page (`identity_document_render_dpi_policy`'s docstring)
    — a document that would benefit from a sharper render exists alongside
    one for which a naive global bump 413s the provider. A policy replaces
    the single int with two rules instead of a bigger constant:

    - `dpi_for_page_count`: the document's page count -> a STARTING dpi. A
      ceiling, not a guarantee — see the next rule.
    - Each rendered page is checked against `max_encoded_bytes` (the
      base64-encoded size, matching what the vision call actually sends —
      `documents.transcription._encoded_size`) and stepped DOWN through
      `step_down_dpis` (only the candidates below the starting dpi are
      tried, in descending order) until it fits, or the floor is reached.
      NEVER silently sent oversized — see `_pdf_to_images_within_budget`.
    """

    dpi_for_page_count: Callable[[int], int]
    max_encoded_bytes: int
    step_down_dpis: tuple[int, ...] = (300, 200, 150, 100)


def identity_document_render_dpi_policy() -> RenderDpiPolicy:
    """The `NOC-REMEDIATE[identity-vision-render-dpi]` fix.

    Measured 2026-09-23 against a real "CNH Digital" (Detran/Serpro) PDF:
    the card's every field lives in a small embedded image on a page whose
    SELECTABLE text is a legal/signature disclaimer (see
    `pdf_text._PROVENANCE_STAMP_PATTERNS`'s Serpro/SENATRAN block, added
    2026-09-07 for the same document family) — at the seed-wide canonical
    `RENDER_DPI` (200, tuned for dense registry print, not a thumbnail-
    sized card graphic), the rasterized page is too coarse for the vision
    model to read the card. A single-page document can afford a much
    sharper render; a longer one cannot (bandwidth, and the identity fields
    do not live past page 1 anyway) — hence the step-down by page count,
    floored at the seed-wide default rather than going lower still.

    `max_encoded_bytes` is Anthropic's own documented per-image ceiling
    (`llm.providers.anthropic_provider.MAX_IMAGE_BYTES`) — imported lazily
    so `documents.transcription` never drags the `anthropic` SDK into a
    caller that only ever reads a text layer. A naive GLOBAL DPI=400 (no
    per-page step-down, no budget check) is exactly what 413'd a 2-page
    certidão in the same measurement; `step_down_dpis` is what this policy
    uses instead of repeating that mistake.
    """
    from noctusai_lib.integrations.llm.providers.anthropic_provider import (
        MAX_IMAGE_BYTES,
    )

    def _dpi_for_page_count(num_pages: int) -> int:
        if num_pages <= 1:
            return 400
        if num_pages <= 3:
            return 300
        # Longer documents keep the unchanged canonical default: the
        # identity fields this rung exists for do not live past page 1,
        # and a longer document is more likely to be dense print anyway.
        return RENDER_DPI

    return RenderDpiPolicy(
        dpi_for_page_count=_dpi_for_page_count,
        max_encoded_bytes=MAX_IMAGE_BYTES,
        step_down_dpis=(300, 200, 150, 100),
    )


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

    🔴 THE MARKERS ARE PER-VENDOR AND MUST GROW WITH THE PROVIDER LIST.
    Anthropic does not say `insufficient_quota`; it answers HTTP 400 with
    `credit_balance_too_low` / "credit balance is too low". Adding the
    provider without adding its marker would have re-created the exact 2026-
    09-03 defect on the other vendor — an unpaid account surfacing as a
    generic "Erro inesperado" with no mention of billing. Caught 2026-09-04
    by asserting the mapping directly rather than by waiting for prod.
    """
    # A key that vanished between the pre-check and the call (or that the
    # call-site `key_provider` resolves differently from `resolve_credential`)
    # raises `LLMNotConfigured`. That is "no credential for the selected
    # vendor", not an unexpected failure — named as such so the consumer tells
    # the operator which key to configure instead of "Erro inesperado".
    from noctusai_lib.integrations.llm.exceptions import LLMNotConfigured

    if isinstance(exc, LLMNotConfigured):
        return "missing_credentials"
    text = f"{type(exc).__name__}: {exc}".lower()
    # The 6 vendor-agnostic quota markers are the seed's single canonical
    # list (`noctusai_lib.integrations.llm.credit_probe.QUOTA_MARKERS`) — this
    # module and `social-wiring/app/routers/settings_router.py` used to each
    # hand-maintain their own copy of the same tuple (N=3; DRY N≥3 rule).
    # `"billing"` stays local: it is a looser, transcription-specific catch
    # not shared by the other two call sites.
    if any(s in text for s in QUOTA_MARKERS) or "billing" in text:
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
    #: Bold/underline ranges into THIS page's `text` — `()` when the page
    #: carries no formatting, or a span could not be aligned (rung 1; see
    #: `_extract_text_layer_formatting`). A `FormatRange` here never implies
    #: `text` changed: that invariant is what lets existing consumers keep
    #: their offsets into it (matrícula acts, migration 109).
    formatting: tuple[FormatRange, ...] = ()


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
    def formatting(self) -> tuple[FormatRange, ...]:
        """Document-level ranges, re-based onto `text`.

        Uses the EXACT join `text` uses above — "\\n\\n" between pages,
        blank pages dropped — so an offset from here is valid against `text`
        without the caller re-deriving how the pages were joined.
        """
        ranges: list[FormatRange] = []
        offset = 0
        primeira = True
        for page in self.pages:
            if not page.text:
                continue
            if not primeira:
                offset += 2  # the "\n\n" join
            for r in page.formatting:
                ranges.append(
                    FormatRange(
                        start=r.start + offset,
                        end=r.end + offset,
                        bold=r.bold,
                        underline=r.underline,
                    )
                )
            offset += len(page.text)
            primeira = False
        return tuple(ranges)

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
        render_dpi_policy: Optional[RenderDpiPolicy] = None,
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
        # `None` (the default) keeps EVERY existing consumer's behaviour
        # byte-for-byte: a flat `self._render_dpi` int, no per-page budget
        # check — see `_pdf_to_images` below. Set only by
        # `identity_document_render_dpi_policy()` today (via
        # `LadderIdentityExtractor`); a caller that supplies one opts INTO
        # the page-count + byte-budget-aware rasterization in
        # `_pdf_to_images_within_budget`, which then takes over from
        # `render_dpi` entirely for the vision rung.
        self._render_dpi_policy = render_dpi_policy
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

        # Bold/underline for the free pages, from the PDF's own spans and
        # drawings — never from re-deriving `textos`, which stays untouched
        # (rung-1 invariant: `page.text` is byte-identical either way).
        formatacao_camada = _extrair_formatacao_camada_texto(
            content, textos, sorted(textos)
        )

        if not paginas_para_visao:
            return Transcription(
                pages=tuple(
                    TranscribedPage(
                        number=n,
                        text=textos[n],
                        source=TextSource.TEXT_LAYER,
                        formatting=formatacao_camada.get(n, ()),
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
                        number=n,
                        text=textos[n],
                        source=TextSource.TEXT_LAYER,
                        formatting=formatacao_camada.get(n, ()),
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

        if self._render_dpi_policy is not None:
            images = _pdf_to_images_within_budget(
                content, paginas_para_visao, self._render_dpi_policy, num_paginas, camada
            )
        else:
            images = _pdf_to_images(content, paginas_para_visao, self._render_dpi)
        formatacao_visao: dict[int, tuple[FormatRange, ...]] = {}
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
            marcado = await analyze(
                img,
                self._ocr_prompt,
                model=self._ocr_model,
                provider=self._provider,
                org_id=self._org_id,
                max_tokens=4096,
            )
            # The vision reply carries `**bold**` / `<u>underline</u>` markers
            # per `OCR_PROMPT` — `textos[numero]` is the STRIPPED text (the
            # page's `text`, same as every other rung), and the ranges are
            # kept alongside it, exactly like rung 1.
            texto, ranges = parse_markup(marcado)
            textos[numero] = texto
            formatacao_visao[numero] = ranges
            logger.info("transcription: page %d/%d done", numero, num_paginas)

        por_visao = set(paginas_para_visao)
        return Transcription(
            pages=tuple(
                TranscribedPage(
                    number=n,
                    text=textos[n],
                    source=TextSource.OCR if n in por_visao else TextSource.TEXT_LAYER,
                    formatting=(
                        formatacao_visao.get(n, ())
                        if n in por_visao
                        else formatacao_camada.get(n, ())
                    ),
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

        # `.strip()`: a whitespace-only saved key is as absent as a missing
        # one, and must surface as `missing_credentials`, not as a vendor 401.
        chave = resolve_credential(f"{self._provider}_api_key", self._org_id)
        if not (chave or "").strip():
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


def _encoded_size(raw: bytes) -> int:
    """Base64-encoded byte length, without doing the encoding.

    This is the size that actually crosses the wire in a vision content
    block (`source.data` in `AnthropicProvider.analyze_image`) — ~4/3 the
    raw size — and the number `RenderDpiPolicy.max_encoded_bytes` is
    compared against. Computed rather than encoded: a policy may try
    several DPI candidates per page, and `base64.b64encode` on a
    multi-megabyte PNG per candidate is wasted work the arithmetic avoids.
    """
    return 4 * ((len(raw) + 2) // 3)


#: A page's largest embedded image must be at least this many times the
#: area of the next-largest to count as "the document" rather than one of
#: several images of comparable importance (a card graphic next to an
#: issuer logo of similar size, say — ambiguous, so the ordinary
#: page-raster rung answers instead).
_DOMINANT_IMAGE_AREA_RATIO = 3.0


def _dominant_embedded_image(pdf_bytes: bytes, numero: int) -> Optional[bytes]:
    """The ONE embedded raster image on this page, at ITS OWN resolution.

    The `identity-vision-render-dpi` shape measured 2026-09-23: a card's
    every field lives in a small embedded image; the page's SELECTABLE
    text is a disclaimer that swamps it. Sending the issuer's own pixels,
    uncropped and unscaled, beats rasterizing the WHOLE page at any DPI —
    sharper on the part that matters and smaller in bytes (a thumbnail-
    sized card graphic vs. a full A4 raster), so the DPI/budget trade-off
    in `_pdf_to_images_within_budget` does not even arise for this page.

    Never raises, and returns `None` — the ordinary page-raster rung then
    answers instead — when: the page cannot be opened; it has no embedded
    image; or it has more than one and none is unambiguously dominant
    (`_DOMINANT_IMAGE_AREA_RATIO`). Deliberately does NOT try to pick "the
    best" image among several comparable ones — a wrong guess there would
    silently send the wrong picture, which is worse than falling back to
    the page raster this function's caller already has to support anyway.
    """
    try:
        import fitz  # type: ignore  # PyMuPDF

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception:
        logger.debug("dominant-image: could not open PDF", exc_info=True)
        return None
    try:
        if numero < 1 or numero > doc.page_count:
            return None
        page = doc[numero - 1]
        try:
            imagens = page.get_images(full=True)
        except Exception:
            logger.debug("dominant-image: get_images failed on page %d", numero, exc_info=True)
            return None
        if not imagens:
            return None

        areas: list[tuple[float, int]] = []
        for img in imagens:
            xref = img[0]
            try:
                maior = max(
                    (abs(r.width * r.height) for r in page.get_image_rects(xref)),
                    default=0.0,
                )
            except Exception:
                maior = 0.0
            areas.append((maior, xref))
        areas.sort(key=lambda par: par[0], reverse=True)

        if len(areas) > 1 and areas[0][0] < areas[1][0] * _DOMINANT_IMAGE_AREA_RATIO:
            return None  # no single image clearly IS the document

        xref = areas[0][1]
        try:
            extraido = doc.extract_image(xref)
        except Exception:
            logger.debug("dominant-image: extract_image failed on page %d", numero, exc_info=True)
            return None
        dados = (extraido or {}).get("image")
        return dados or None
    finally:
        doc.close()


def _pdf_to_images_within_budget(
    pdf_bytes: bytes,
    paginas: list[int],
    policy: RenderDpiPolicy,
    num_paginas: int,
    camada,
) -> dict[int, bytes]:
    """Rasterize each page for vision, honouring `policy` — the
    `identity-vision-render-dpi` fix. Per page, independently:

    1. If the page's text layer classified as pure provenance boilerplate
       (`reason == "provenance stamp only"` — see `pdf_text._classify_page`)
       and it carries one dominant embedded image, send that image at its
       own resolution (`_dominant_embedded_image`) — cheaper AND sharper
       than any page raster, so the DPI/budget question below is skipped
       entirely for this page.
    2. Otherwise, rasterize the whole page starting at
       `policy.dpi_for_page_count(num_paginas)`, stepping DOWN through
       `policy.step_down_dpis` (only the candidates below the starting DPI,
       descending) whenever the base64-encoded image would exceed
       `policy.max_encoded_bytes` — the fix for the naive-global-DPI 413.
       Independent per page on purpose: a document whose card sits on page
       1 and whose page 2 is a dense full-page scan should not have its
       sharp page-1 render dragged down by page 2's size, nor vice versa.

    Never sends a page silently over budget: if even the floor DPI does
    not fit, the floor render is still used (a document must not lose a
    page because it is dense) but logged at `error` so the near-413 is
    visible rather than discovered downstream as a vendor failure.
    """
    razoes = {p.number: p.reason for p in camada.pages} if camada is not None else {}
    starting_dpi = policy.dpi_for_page_count(num_paginas)
    candidatos = [starting_dpi] + sorted(
        {d for d in policy.step_down_dpis if d < starting_dpi}, reverse=True
    )

    images: dict[int, bytes] = {}
    for numero in paginas:
        if razoes.get(numero) == "provenance stamp only":
            nativo = _dominant_embedded_image(pdf_bytes, numero)
            if nativo is not None and _encoded_size(nativo) <= policy.max_encoded_bytes:
                images[numero] = nativo
                continue

        escolhido: Optional[bytes] = None
        dpi_usado: Optional[int] = None
        for dpi in candidatos:
            pagina_imgs = _pdf_to_images(pdf_bytes, [numero], dpi)
            img = pagina_imgs.get(numero)
            if img is None:
                continue
            escolhido = img
            dpi_usado = dpi
            if _encoded_size(img) <= policy.max_encoded_bytes:
                break

        if escolhido is None:
            # Rasterize failed at every candidate DPI — the caller's
            # existing `rasterize_failed` handling covers a missing page.
            continue

        if dpi_usado < candidatos[0]:
            logger.warning(
                "transcription: page %d rendered at %d DPI (policy asked "
                "for %d) to stay under the %d-byte vision request budget",
                numero, dpi_usado, candidatos[0], policy.max_encoded_bytes,
            )
        if _encoded_size(escolhido) > policy.max_encoded_bytes:
            logger.error(
                "transcription: page %d still exceeds the %d-byte vision "
                "request budget even at the floor DPI (%d) — sending it "
                "anyway; the provider call may reject it as too large",
                numero, policy.max_encoded_bytes, dpi_usado,
            )
        images[numero] = escolhido
    return images


# ── Rung 1: bold/underline from the PDF's own spans and drawings ─────────
#
# Thresholds validated 2026-09-14 against ~180 real text-layer PDFs stored
# in prod (social-wiring certidões + client/imóvel documents + the ERP
# certidões bucket) — see `formatting-samples.md` (not committed: it quotes
# short excerpts of real documents). Two findings from that pass:
#
# - Bold: `flags & 16` and a bold-family font name NEVER disagreed across
#   the whole corpus. Either signal alone would have been enough; both are
#   kept because they cost nothing extra.
# - Underline geometry alone produced 36 FALSE positives on one certidão
#   template (`trt2_fisico`): a table/box rule 82-229x wider than the text
#   it ran through, which also satisfied the old overlap+baseline check.
#   `_UNDERLINE_MAX_LINE_WIDTH_RATIO` below is the fix — a real underline is
#   comparable in length to the text it underlines; a table rule is not.
#
# 🔴 NOC-REMEDIATE[transcricao-underline-charflags]: the sample corpus also
# recommends PyMuPDF's per-CHARACTER style bits (`get_text("dict", flags=
# TEXTFLAGS_DICT | TEXT_COLLECT_STYLES)`, then `span["char_flags"] & 2`) as
# the PRIMARY underline signal, confirmed by geometry — 18/26 were the
# observed values on real hyperlink underlines. This module does NOT wire
# that signal in: probed locally against the installed PyMuPDF (1.27.2.2,
# vs. prod's 1.28.2), that build's own exposed constants
# (`TEXT_FONT_ITALIC = 2`) show bit 2 is documented as ITALIC at the
# `flags`/font-style level, and an HTML-authored `<u>`/`<s>` decoration
# produced no distinct `char_flags` bit at all on this build — so an
# unqualified `char_flags & 2` risks reading "italic" as "underlined" here.
# Every real underline this pass found was a hyperlink decoration; there is
# still no real matrícula PDF in prod to validate a hand-drawn underline
# against (2026-09-14). Geometry (now with the width-ratio guard) is kept
# as the sole signal until `char_flags`'s meaning is confirmed against the
# EXACT PyMuPDF build this module runs under — 2026-09-14.
#
# 2026-09-14 also confirmed a DIFFERENT existing defect worth flagging for
# the backfill (not this slice): 5 of 8 `matricula_extracoes.texto_extraido`
# rows already contain literal `**bold**` markdown from the current vision
# model (despite the plain-verbatim prompt in production today) — exactly
# the shape `parse_markup` below is built to read, which is a point in
# favour of this design, but those existing rows predate `formatacao` and
# still carry the raw asterisks IN `texto_extraido` itself.

#: Font-name substrings (case-insensitive) that mark a bold family even when
#: PyMuPDF's own `flags & 16` bit is unset — happens with some embedded or
#: subsetted fonts whose weight lives only in the PostScript name.
_BOLD_FONT_NAME_MARKERS = ("bold", "black", "heavy", "semibold")

#: A drawn stroke/rect thicker than this is a rule or a table border, not an
#: underline.
_UNDERLINE_MAX_THICKNESS = 2.5

#: A stroke shorter than this (points) is noise — a serif terminal, a dot on
#: an "i", a stray hairline — not a deliberate underline.
_UNDERLINE_MIN_LENGTH = 3.0

#: A stroke up to this far ABOVE a span's baseline still counts (the artist
#: does not always draw exactly on the baseline). Real underlines observed
#: sat 1.05-1.41pt BELOW the baseline, comfortably inside this window.
_UNDERLINE_BASELINE_TOLERANCE = 1.0

#: ...and up to this fraction of the font size BELOW the baseline.
_UNDERLINE_BASELINE_BELOW_RATIO = 0.35

#: The stroke must cover at least this fraction of the span's width to count
#: as underlining that span (as opposed to, say, the next word's underline
#: brushing its edge).
_UNDERLINE_MIN_OVERLAP_RATIO = 0.5

#: 🔴 A stroke longer than this multiple of its LINE's own text width is a
#: table/box rule, not an underline — the `trt2_fisico` false-positive fix.
#: A real underline is comparable in length to the text it marks; a rule
#: crossing a whole table cell or page width is not, even when it happens
#: to overlap a short span by more than `_UNDERLINE_MIN_OVERLAP_RATIO`.
_UNDERLINE_MAX_LINE_WIDTH_RATIO = 1.5


def _is_bold_span(span: dict) -> bool:
    """PyMuPDF's bold bit, OR a bold-family font name.

    `flags & 16` is PyMuPDF's own bold flag; checked first because it needs
    no string matching. Some scanned-then-reflowed text layers carry a bold
    FONT without that bit set, which is what the font-name fallback catches.
    Validated against ~180 real text-layer PDFs 2026-09-14: the two signals
    never disagreed.
    """
    if bool(span.get("flags", 0) & 16):
        return True
    fonte = (span.get("font") or "").lower()
    return any(marcador in fonte for marcador in _BOLD_FONT_NAME_MARKERS)


def _page_text_spans(page) -> list[tuple[dict, float]]:
    """Every text span on the page, paired with its LINE's own text width —
    the denominator `_has_underline`'s width-ratio guard needs to tell a
    real underline from a table rule — in the order PyMuPDF's dict mode
    returns them (the same reading order `page.get_text()`, used for
    `page.text`, reconstructs its output from)."""
    spans: list[tuple[dict, float]] = []
    d = page.get_text("dict")
    for block in d.get("blocks", ()):
        for line in block.get("lines", ()):
            bbox = line.get("bbox") or (0.0, 0.0, 0.0, 0.0)
            largura_linha = bbox[2] - bbox[0]
            for span in line.get("spans", ()):
                spans.append((span, largura_linha))
    return spans


def _underline_segments(page) -> list[tuple[float, float, float]]:
    """Thin, roughly-horizontal vector strokes on the page, as
    `(x0, x1, y)` — a straight line or a thin filled rectangle, the two
    shapes a registry actually draws an underline with. Never raises: a page
    whose drawings cannot be read contributes no segments, which can only
    ever under-detect underline, never invent text.
    """
    segmentos: list[tuple[float, float, float]] = []
    try:
        desenhos = page.get_drawings()
    except Exception:
        logger.debug("transcription: get_drawings failed", exc_info=True)
        return segmentos
    for desenho in desenhos:
        for item in desenho.get("items", ()):
            tipo = item[0]
            if tipo == "l":
                p1, p2 = item[1], item[2]
                if (
                    abs(p1.y - p2.y) <= 1.0
                    and abs(p1.x - p2.x) >= _UNDERLINE_MIN_LENGTH
                ):
                    segmentos.append(
                        (min(p1.x, p2.x), max(p1.x, p2.x), (p1.y + p2.y) / 2)
                    )
            elif tipo == "re":
                rect = item[1]
                if (
                    rect.height <= _UNDERLINE_MAX_THICKNESS
                    and rect.width >= _UNDERLINE_MIN_LENGTH
                ):
                    segmentos.append((rect.x0, rect.x1, (rect.y0 + rect.y1) / 2))
    return segmentos


def _has_underline(
    span: dict,
    line_width: float,
    segmentos: list[tuple[float, float, float]],
) -> bool:
    """Does any drawn segment sit under THIS span, per the thresholds above.

    `line_width` gates a segment far longer than the text it runs
    through — a table/box rule, not an underline (`trt2_fisico`, 36 false
    positives on the geometry-only check; see the module comment above).
    """
    x0, y0, x1, y1 = span["bbox"]
    origem = span.get("origin") or (x0, y1)
    baseline = origem[1]
    tamanho = span.get("size", 0.0) or 0.0
    largura = max(x1 - x0, 1e-3)
    largura_linha = max(line_width, largura)
    limite_inferior = baseline - _UNDERLINE_BASELINE_TOLERANCE
    limite_superior = (
        baseline
        + _UNDERLINE_BASELINE_BELOW_RATIO * tamanho
        + _UNDERLINE_BASELINE_TOLERANCE
    )
    for sx0, sx1, sy in segmentos:
        largura_segmento = sx1 - sx0
        if largura_segmento > _UNDERLINE_MAX_LINE_WIDTH_RATIO * largura_linha:
            continue  # a table/box rule spanning far more than the line
        sobreposicao = min(x1, sx1) - max(x0, sx0)
        if sobreposicao < _UNDERLINE_MIN_OVERLAP_RATIO * largura:
            continue
        if limite_inferior <= sy <= limite_superior:
            return True
    return False


def _merge_adjacent_ranges(ranges: list[FormatRange]) -> tuple[FormatRange, ...]:
    """Merge same-formatting ranges that touch with no gap between them.

    PyMuPDF sometimes splits one visually-continuous bold or underlined run
    into two spans (a font-metric quirk, or two words joined by a single
    drawn underline stroke); a caller re-rendering `formatting` should see
    ONE range for that run, not two it has to notice are adjacent.
    """
    ordenados = sorted(ranges, key=lambda r: (r.start, r.end))
    mesclados: list[FormatRange] = []
    for r in ordenados:
        if (
            mesclados
            and mesclados[-1].end == r.start
            and mesclados[-1].bold == r.bold
            and mesclados[-1].underline == r.underline
        ):
            anterior = mesclados.pop()
            mesclados.append(
                FormatRange(
                    start=anterior.start,
                    end=r.end,
                    bold=anterior.bold,
                    underline=anterior.underline,
                )
            )
        else:
            mesclados.append(r)
    return tuple(mesclados)


def _extract_text_layer_formatting(page, text: str) -> tuple[FormatRange, ...]:
    """Bold + underline ranges for one text-layer page, aligned onto `text`.

    `text` is the SAME string `classify_pdf_text_layer` already trusts
    (`page.get_text().strip()` — see that module) — never re-derived here,
    so `page.text` cannot shift by a single character because of this
    function. A span whose text cannot be located inside `text` is dropped
    and logged at debug: dropping a formatting range loses styling, dropping
    nothing ever loses or moves TEXT, which is the one invariant this whole
    feature is not allowed to break.
    """
    try:
        spans = _page_text_spans(page)
    except Exception:
        logger.debug("transcription: get_text(dict) failed", exc_info=True)
        return ()

    segmentos = _underline_segments(page)

    ranges: list[FormatRange] = []
    cursor = 0
    for span, largura_linha in spans:
        bruto = span.get("text", "")
        recortado = bruto.strip()
        if not recortado:
            continue
        negrito = _is_bold_span(span)
        sublinhado = _has_underline(span, largura_linha, segmentos)
        if not (negrito or sublinhado):
            continue
        # Search forward from the last match first (keeps spans in order and
        # handles a repeated word correctly); fall back to a global search
        # for the rare case a span is not encountered in reading order.
        idx = text.find(recortado, cursor)
        if idx == -1:
            idx = text.find(recortado)
        if idx == -1:
            logger.debug(
                "transcription: could not align span %r onto page text", recortado
            )
            continue
        fim = idx + len(recortado)
        if fim > cursor:
            cursor = fim
        ranges.append(FormatRange(start=idx, end=fim, bold=negrito, underline=sublinhado))

    return _merge_adjacent_ranges(ranges)


def _extrair_formatacao_camada_texto(
    pdf_bytes: bytes, textos: dict[int, str], paginas: list[int]
) -> dict[int, tuple[FormatRange, ...]]:
    """Bold/underline for the text-layer pages, keyed by 1-based page number.

    Opens its OWN `fitz.Document` — deliberately separate from
    `classify_pdf_text_layer`'s (this module does not own that function and
    must not change it to add formatting extraction). Never raises: a
    document or a page whose formatting cannot be read comes back with `()`
    for that page, and `textos` — the trusted text — is never touched here.
    """
    resultado: dict[int, tuple[FormatRange, ...]] = {n: () for n in paginas}
    if not paginas:
        return resultado
    try:
        import fitz  # type: ignore  # PyMuPDF

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception:
        logger.debug(
            "transcription: could not reopen PDF for formatting", exc_info=True
        )
        return resultado
    try:
        alvo = set(paginas)
        for index in range(doc.page_count):
            numero = index + 1
            if numero not in alvo:
                continue
            texto = textos.get(numero, "")
            if not texto:
                continue
            try:
                resultado[numero] = _extract_text_layer_formatting(doc[index], texto)
            except Exception:
                logger.debug(
                    "transcription: formatting extraction failed on page %d",
                    numero,
                    exc_info=True,
                )
    finally:
        doc.close()
    return resultado


# ── Rung 2: the vision markup parser ──────────────────────────────────────

#: Recognises exactly the three markers `OCR_PROMPT` asks the model for.
#: A change to the prompt's marker syntax must change this together with it.
_MARKUP_TOKEN_RE = re.compile(r"\*\*|<u>|</u>", re.IGNORECASE)

#: Any OTHER angle-bracket tag — logged (never acted on) so an unexpected
#: marker shows up in the logs instead of silently vanishing into the text.
_UNKNOWN_TAG_RE = re.compile(r"</?(?!u\b)[a-zA-Z][^>]*>", re.IGNORECASE)


def _unmatched_toggle_index(tokens: list[tuple[str, int, int]], kind: str) -> set[int]:
    """`**` toggles bold on each occurrence; an ODD total means the LAST one
    never found its pair. That one token index is returned so the caller
    renders it as two literal asterisks instead of toggling — an unbalanced
    marker is not a formatting instruction, it is a typo in the model's
    reply."""
    indices = [i for i, t in enumerate(tokens) if t[0] == kind]
    if len(indices) % 2 == 0:
        return set()
    return {indices[-1]}


def _unmatched_pair_indices(
    tokens: list[tuple[str, int, int]], open_kind: str, close_kind: str
) -> tuple[set[int], set[int]]:
    """Stack-match `<u>`/`</u>`. A `</u>` with nothing open is stray; any
    `<u>` still open at the end never closed. Both come back as literal."""
    abertos: list[int] = []
    fechamentos_invalidos: set[int] = set()
    for i, t in enumerate(tokens):
        if t[0] == open_kind:
            abertos.append(i)
        elif t[0] == close_kind:
            if abertos:
                abertos.pop()
            else:
                fechamentos_invalidos.add(i)
    return set(abertos), fechamentos_invalidos


def parse_markup(markup: str) -> tuple[str, tuple[FormatRange, ...]]:
    """OCR markup (`**bold**`, `<u>underline</u>`, combined/nested freely) →
    `(plain text, format ranges)`.

    Strips the markers and returns offsets into the STRIPPED text, so the
    result slots directly into `TranscribedPage.text` / `.formatting`.

    Never raises. An unbalanced `**`, a stray or unclosed `<u>`/`</u>`, or
    any other bracketed marker the model was not asked for is kept as
    LITERAL text (and logged) rather than guessed at — a malformed vision
    reply must still produce a document, and a formatting range built from a
    guess would be worse than none.
    """
    tokens: list[tuple[str, int, int]] = []
    pos = 0
    for m in _MARKUP_TOKEN_RE.finditer(markup):
        if m.start() > pos:
            tokens.append(("text", pos, m.start()))
        bruto = m.group()
        if bruto == "**":
            kind = "bold"
        elif bruto.lower() == "<u>":
            kind = "u_open"
        else:
            kind = "u_close"
        tokens.append((kind, m.start(), m.end()))
        pos = m.end()
    if pos < len(markup):
        tokens.append(("text", pos, len(markup)))

    for m in _UNKNOWN_TAG_RE.finditer(markup):
        logger.warning(
            "transcription: unrecognised markup tag %r in vision reply — kept literal",
            m.group(),
        )

    bold_invalido = _unmatched_toggle_index(tokens, "bold")
    if bold_invalido:
        logger.warning(
            "transcription: unbalanced ** marker in vision reply — kept literal"
        )
    u_abertos_invalidos, u_fechamentos_invalidos = _unmatched_pair_indices(
        tokens, "u_open", "u_close"
    )
    if u_abertos_invalidos or u_fechamentos_invalidos:
        logger.warning(
            "transcription: unbalanced <u>/</u> marker in vision reply — kept literal"
        )

    saida: list[str] = []
    comprimento = 0
    ranges: list[FormatRange] = []
    negrito = False
    profundidade_sublinhado = 0
    inicio_trecho = 0
    trecho_negrito = False
    trecho_sublinhado = False

    def fechar_trecho(fim: int) -> None:
        nonlocal inicio_trecho
        if fim > inicio_trecho and (trecho_negrito or trecho_sublinhado):
            ranges.append(
                FormatRange(
                    start=inicio_trecho,
                    end=fim,
                    bold=trecho_negrito,
                    underline=trecho_sublinhado,
                )
            )
        inicio_trecho = fim

    for i, (kind, s, e) in enumerate(tokens):
        bruto = markup[s:e]
        if kind == "text":
            saida.append(bruto)
            comprimento += len(bruto)
            continue
        if kind == "bold" and i not in bold_invalido:
            fechar_trecho(comprimento)
            negrito = not negrito
            trecho_negrito, trecho_sublinhado = negrito, profundidade_sublinhado > 0
            continue
        if kind == "u_open" and i not in u_abertos_invalidos:
            fechar_trecho(comprimento)
            profundidade_sublinhado += 1
            trecho_negrito, trecho_sublinhado = negrito, profundidade_sublinhado > 0
            continue
        if kind == "u_close" and i not in u_fechamentos_invalidos:
            fechar_trecho(comprimento)
            profundidade_sublinhado -= 1
            trecho_negrito, trecho_sublinhado = negrito, profundidade_sublinhado > 0
            continue
        # Unbalanced/stray marker — kept as literal text.
        saida.append(bruto)
        comprimento += len(bruto)

    fechar_trecho(comprimento)
    texto = "".join(saida)
    return texto, _merge_adjacent_ranges(ranges)


def has_raw_markup(text: Optional[str]) -> bool:
    """Does `text` still carry a literal `**`/`<u>`/`</u>` marker?

    The SAME token `_MARKUP_TOKEN_RE` `parse_markup` strips — exposed
    separately because a caller downstream of transcription (a contract
    generator, a legibility flag on a listing) needs to ask "was this text
    ever run through `parse_markup`, or is it pre-migration-113 raw vision
    output with the markers still baked in" without re-deriving the pattern.
    `**`/`<u>`/`</u>` reaching a signed legal instrument verbatim is the
    actual harm `parse_markup` exists to prevent; a caller that only reads
    `texto_extraido` back out (never re-transcribes) needs its own way to
    catch a row `parse_markup` never got to run on. `None`/empty → `False`.
    """
    return bool(_MARKUP_TOKEN_RE.search(text or ""))


def make_document_transcriber(
    *,
    real: bool = False,
    org_id: Optional[str] = None,
    provider: Optional[str] = None,
    ocr_model: Optional[str] = None,
    ocr_prompt: str = OCR_PROMPT,
    render_dpi: int = RENDER_DPI,
    render_dpi_policy: Optional[RenderDpiPolicy] = None,
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
        provider: Which vendor reads the scanned pages — any key of
            `OCR_MODELS` (`"openai"` / `"anthropic"` / `"gemini"`).
            `None` keeps `DEFAULT_VISION_PROVIDER`. This is a
            MANUAL selection — nothing here fails over to the other vendor,
            because a silent switch would change which model transcribed a
            legal document without anyone being told.
        ocr_model / ocr_prompt / render_dpi: Vision-rung overrides. The
            defaults are the canonical answer for dense registry documents,
            not one consumer's preference. Leave `ocr_model` as `None` unless
            you are pinning a model deliberately — it then follows `provider`
            through `OCR_MODELS`, which is what keeps the two in step.
        render_dpi_policy: `None` (the default) leaves `render_dpi` in sole
            charge, unchanged, for every existing consumer (media
            generation, matrícula, certidão-estrutura). Pass a
            `RenderDpiPolicy` (see `identity_document_render_dpi_policy`)
            to opt a caller INTO page-count + byte-budget-aware
            rasterization instead — it then takes over from `render_dpi`
            entirely for the vision rung.
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
        render_dpi_policy=render_dpi_policy,
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
    "RenderDpiPolicy",
    "TranscribedPage",
    "Transcription",
    "identity_document_render_dpi_policy",
    "make_document_transcriber",
    "has_raw_markup",
    "parse_markup",
]
