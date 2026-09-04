"""PDF text-layer extraction — `extract_pdf_text(bytes) -> str`.

Lifted 2026-05-19 by `social-wiring-google-seed-consume` Phase 6a-drive
from the social-wiring `media_service._extract_pdf_text` + reconciled
with `OpenAIMediaResolver._pdf_text_layer` (the existing private
implementation inside this seed module — same logic, now single-sourced
and public). Becomes the canonical PDF→text helper for both the
multimodal `OpenAIMediaResolver` document path AND non-resolver
consumers (e.g. `DriveFileContent.text` for `application/pdf`).

Implementation order (matches the absorbed product + ERP `certidoes_service`
convention):

1. **PyMuPDF (`fitz`) `page.get_text()` per page**, joined with newlines
   between non-empty pages. Faster than pdfminer for the text-layer case
   and we already depend on it for the rasterize fallback inside
   `OpenAIMediaResolver`.
2. **`pdfminer.high_level.extract_text(...)` fallback** when PyMuPDF
   is unavailable (slim envs) — defensive: both ship in social-wiring's
   `requirements.txt`. Used to be the primary in the absorbed product;
   demoted per the W1.E5 reconcile (commit `61d684f`).
3. **Returns `""` on any failure** (no PyMuPDF *and* no pdfminer; corrupted
   PDF; empty text layer of a scanned doc). Callers can fall through to
   rasterize-then-vision (`OpenAIMediaResolver._pdf_rasterize` +
   `analyze_image_with_refusal_retry`).

Tooling-availability signal: `pdf_text_tooling_available()` returns
False when both libs are absent so a consumer can distinguish
"extraction returned empty because the doc has no text" from
"extraction returned empty because we have no extractor."
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from io import BytesIO

logger = logging.getLogger(__name__)


def extract_pdf_text(pdf_bytes: bytes) -> str:
    """Extract text from a PDF using PyMuPDF, falling back to pdfminer.

    Returns the joined page text (one newline between non-empty pages)
    or `""` on any failure. Never raises into the caller — failures
    are logged at `debug` and the caller falls through to other
    extraction paths (rasterize + vision)."""
    text, _ok = _extract_pdf_text_with_signal(pdf_bytes)
    return text


def pdf_text_tooling_available() -> bool:
    """True iff at least one of PyMuPDF or pdfminer.six can be imported.

    Use this to distinguish "extractor unavailable" from "extractor
    returned empty for this doc" in degraded-mode error messages."""
    try:
        import fitz  # type: ignore  # noqa: F401  # PyMuPDF
        return True
    except ImportError:
        pass
    try:
        import pdfminer.high_level  # type: ignore  # noqa: F401
        return True
    except ImportError:
        return False


def _extract_pdf_text_with_signal(pdf_bytes: bytes) -> tuple[str, bool]:
    """Return `(text, tooling_available)`.

    The `tooling_available` bool is True when at least one extractor
    library was importable (text may still be empty for scanned docs);
    False only when neither PyMuPDF nor pdfminer is installed."""
    if not pdf_bytes:
        return ("", pdf_text_tooling_available())

    # Try PyMuPDF first — faster + matches noc's certidoes_service
    # convention. ModuleNotFoundError falls through to pdfminer;
    # any other exception logs at debug and falls through too (so a
    # corrupt PDF doesn't crash the caller; pdfminer may handle it).
    try:
        import fitz  # type: ignore  # PyMuPDF

        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        except Exception:
            logger.debug("PyMuPDF: failed to open document", exc_info=True)
        else:
            try:
                chunks = [doc[i].get_text().strip() for i in range(len(doc))]
            except Exception:
                logger.debug("PyMuPDF: get_text failed", exc_info=True)
                chunks = []
            finally:
                doc.close()
            joined = "\n".join(c for c in chunks if c)
            if joined:
                return (joined, True)
            # PyMuPDF available but yielded no text — try pdfminer
            # (different parser may handle some text-layer encodings
            # PyMuPDF struggles with).
    except ImportError:
        pass

    try:
        from pdfminer.high_level import extract_text  # type: ignore
    except ImportError:
        # Neither lib available — caller may fall through to rasterize.
        return ("", False)

    try:
        return (extract_text(BytesIO(pdf_bytes)) or "", True)
    except Exception:
        logger.debug("pdfminer extract_text failed", exc_info=True)
        return ("", True)


# ---------------------------------------------------------------------------
# Is this text layer CONTENT, or a stamp printed on top of a scan?
# ---------------------------------------------------------------------------
#
# `extract_pdf_text` answers "what text is in this PDF". It does NOT answer
# the question every caller actually has: *should I trust it, or rasterize
# and pay for vision?* Four call sites used to answer that themselves, each
# with its own predicate, and all four got it wrong in the same direction —
# they treated ANY text as content:
#
#   - `matricula_service._texto_da_camada`  -> `>= 100 chars/page`
#   - `documents.real.LadderIdentityExtractor._to_text` -> `if text.strip()`
#   - `media.real_adapter._resolve_pdf`     -> `if text`
#   - ERP `certidoes_service._extract_pdf_text` -> `if parts`
#
# A Brazilian cartório scan is a page-sized JPEG with a digital-signature
# stamp overlaid as real text. So the text layer is non-empty and utterly
# worthless: a 3-page "CERTIDÃO DE MATRÍCULA" transcribed as nothing but
# "Valide este documento clicando no link a seguir: https://assinador-web.
# onr.org.br/docs/..." repeated once per page (137 chars/page — enough to
# clear every one of those four predicates). The document's actual content
# never left the JPEG.
#
# A character count alone cannot separate the two cases: boilerplate is
# unbounded (a longer disclaimer defeats any threshold you pick), so the
# primary signal here is STRUCTURAL — a page whose raster images cover the
# page area *is* a rendered scan, however chatty its stamp.
#
# 🔴 AND THE CHARACTER FLOOR IS NOT A BACKSTOP — IT IS THE HOLE ITSELF.
# ---------------------------------------------------------------------
# The structural signal was added on 2026-08-25 but `MIN_CHARS_PER_PAGE`
# stayed underneath it as a fallback, so a stamp still passes on any page
# the coverage rule does not reach. Measured on the documents this platform
# has actually been fed (2026-09-04):
#
#   file                                  stamp chars/page   coverage
#   CERTIDÃO DE MATRÍCULA - EUROVILLE          137            1.005
#   MATRICULA CANTAGALO (ONR certidão)  p1     137            0.562  ← passes
#   Visualização de Matrícula - Quebec          83            2.389
#   VISUALIZAÇÃO MATRICULA APTO 17 HARMONIA     83            1.443
#
# CANTAGALO page 1 is one scanned image inset at 446×632pt on a 595×842pt
# page. It is a scan by any reading, its whole content is in the JPEG, and
# it clears both rules: 0.562 < 0.80 coverage, 137 >= 100 chars. The page
# was silently transcribed as its own validation link.
#
# The same table explains the defect the user reported: a certidão failed
# where a visualização worked, and the ONLY difference between the two file
# types is that their provenance stamps land on opposite sides of the
# hard-coded 100. That is not a property of the documents — it is an
# accident of where the threshold was put.
#
# So the count that gets compared to a threshold must be a count of REAL
# characters. `strip_provenance_stamps` removes the known cartório stamps
# first; what remains is what the page actually says. A stamp-only page
# then measures 0 and fails every threshold, no matter how long the stamp
# grows or how little of the page its scan happens to cover.


#: A page whose images cover at least this fraction of the page area is a
#: rendered scan. Coverage routinely exceeds 1.0 (cartórios stack the scan,
#: a letterhead and signature glyphs), so this is a floor, not a ratio to
#: normalize. Measured: 1.01 on the ONR certidão, 2.39 on the Quebec
#: visualização — while a digitally-typeset PDF carries a logo at most.
#:
#: It is a SUFFICIENT condition, never a necessary one: CANTAGALO page 1 is
#: a full scan at 0.56. Lowering the number would only move the same
#: accident somewhere else, which is why the fix is the stamp stripper
#: above and not a re-tuned constant.
SCAN_IMAGE_COVERAGE_RATIO = 0.80

#: Characters on a single page that make it unmistakably real content,
#: regardless of coverage. This is the escape hatch for a digitally-typeset
#: document that happens to sit on a full-page background image or
#: watermark — its text is genuine and must not be thrown away for vision.
#: A real matrícula page runs to thousands of characters; a signature stamp
#: runs to ~140, so the gap is an order of magnitude wide.
TEXT_RICH_CHARS_PER_PAGE = 800

#: Floor for a page that is neither text-rich nor a rendered scan — catches
#: a near-blank page whose handful of characters is not worth trusting.
#: Applied to the count AFTER `strip_provenance_stamps`, so it can no longer
#: be cleared by boilerplate alone.
MIN_CHARS_PER_PAGE = 100


#: The provenance stamps Brazilian registries print over a scan, verbatim
#: from documents this platform has ingested. Each one identifies WHO asked
#: for the document and HOW to verify it; none of them says anything about
#: the property, which is why removing them cannot remove content.
#:
#: Matched line-wise against a case-folded, accent-stripped copy of the
#: page, so a stamp that re-wraps or loses its accents in extraction still
#: matches. Anchored to the stamp's own opening words rather than to a
#: fragment that could occur mid-sentence — `find_matricula` and friends
#: read whatever survives this pass, so a pattern that ate real prose would
#: be a far worse defect than the one being fixed.
_PROVENANCE_STAMP_PATTERNS: tuple[str, ...] = (
    # ONR certidão (assinador-web) — the 137-char stamp from the 2026-08-25
    # ERP defect and from CERTIDÃO DE MATRÍCULA - EUROVILLE / CANTAGALO.
    r"^valide\s+est[ea]\s+documento\b.*$",
    r"^valide\s+aqui$",
    r"^este\s+documento$",
    # ONR "Visualização de Matrícula" — the 83-char requester stamp from
    # Quebec Casa 78 and APTO 17 HARMONIA.
    r"^solicitado\s+por\s*:.*$",
    # The vertical watermark the same ONR pipeline prints down the margin.
    r"^documento\s+gerado\s+oficialmente\s+pelo\b.*$",
    r"^registro\s+de\s+im[o0]veis\s+via\s+www\.[^\s]+$",
    r"^todos\s+os\s+registros\s+de\s+im[o0]veis$",
    r"^do\s+brasil\s+em\s+um\s+s[o0]\s+lugar$",
    # Bare verification URLs, which survive on their own when the sentence
    # around them lands on a different line.
    r"^https?://(assinador-web|[\w.-]*\.)?onr\.org\.br/\S*$",
    r"^https?://selodigital\.tjsp\.jus\.br/?\S*$",
    r"^www\.ridigital\.org\.br$",
)


def strip_provenance_stamps(text: str) -> str:
    """Drop the registry provenance boilerplate, keep everything else.

    Used to decide whether a page SAYS anything — not to rewrite what the
    caller receives. `PdfPage.text` keeps the page verbatim, because a page
    that is genuine content should be transcribed faithfully, stamp and all.

    Returns the surviving lines joined by newlines; a page that was nothing
    but boilerplate returns `""`.
    """
    if not text:
        return ""

    kept: list[str] = []
    for line in text.splitlines():
        limpo = line.strip()
        if not limpo:
            continue
        # Accent-strip + case-fold for MATCHING only; `line` is what we keep.
        chave = "".join(
            c
            for c in unicodedata.normalize("NFD", limpo.casefold())
            if unicodedata.category(c) != "Mn"
        )
        if any(re.match(p, chave) for p in _PROVENANCE_STAMP_PATTERNS):
            continue
        kept.append(limpo)
    return "\n".join(kept)


@dataclass(frozen=True)
class PdfPage:
    """One page's text layer plus the verdict on whether to trust it."""

    number: int  # 1-based, matches what a human sees in a PDF reader
    text: str
    is_substantive: bool
    reason: str  # why — carried so callers can log a decision, not a guess


@dataclass(frozen=True)
class PdfTextLayer:
    """Per-page classification of a PDF's text layer.

    `tooling_available` distinguishes "this PDF has no usable text" from
    "we have no extractor installed" — the same signal
    `_extract_pdf_text_with_signal` carries, preserved here so degraded
    environments still report truthfully instead of silently claiming the
    document was scanned.
    """

    pages: tuple[PdfPage, ...]
    tooling_available: bool

    @property
    def text(self) -> str:
        """The substantive text only, page order, blank pages dropped.

        Deliberately excludes non-substantive pages: concatenating a scan's
        signature stamp into the output is the exact defect this module
        exists to prevent.
        """
        return "\n".join(p.text for p in self.pages if p.is_substantive and p.text)

    @property
    def is_substantive(self) -> bool:
        """True iff EVERY page can be read from the text layer.

        All-or-nothing on purpose: a caller that gets True can skip vision
        entirely. A caller that gets False should consult `pages` and
        rasterize only the pages that need it, rather than paying for the
        whole document.
        """
        return bool(self.pages) and all(p.is_substantive for p in self.pages)

    @property
    def scanned_page_numbers(self) -> tuple[int, ...]:
        """Pages that need rasterize→vision, in order."""
        return tuple(p.number for p in self.pages if not p.is_substantive)


def _classify_page(text: str, image_coverage: float) -> tuple[bool, str]:
    """Decide one page. Order matters.

    Takes the page TEXT rather than a character count on purpose: every
    threshold below must be compared against real characters, and a caller
    that had to remember to strip the stamps first would eventually forget
    — which is the whole history of this module.
    """
    conteudo = strip_provenance_stamps(text)
    chars = len(conteudo)

    # A page that carried text and has none left said nothing: it is a scan
    # with a verification stamp printed on it. Decided FIRST because it is
    # the only certain verdict here — the rest are thresholds.
    if text.strip() and not conteudo:
        return (False, "provenance stamp only")
    if chars >= TEXT_RICH_CHARS_PER_PAGE:
        return (True, "text-rich")
    if image_coverage >= SCAN_IMAGE_COVERAGE_RATIO:
        return (False, "rendered scan")
    if chars >= MIN_CHARS_PER_PAGE:
        return (True, "above char floor")
    return (False, "below char floor")


def _page_image_coverage(page) -> float:  # type: ignore[no-untyped-def]
    """Fraction of the page area covered by raster images.

    Never raises: a page whose images cannot be measured reports 0.0, which
    routes the decision back to the character count rather than guessing
    "scan" and spending money on vision.
    """
    try:
        area = abs(page.rect.width * page.rect.height)
    except Exception:
        return 0.0
    if area <= 0:
        return 0.0

    try:
        images = page.get_images(full=True)
    except Exception:
        logger.debug("PyMuPDF: get_images failed", exc_info=True)
        return 0.0

    covered = 0.0
    for img in images:
        try:
            for rect in page.get_image_rects(img[0]):
                covered += abs(rect.width * rect.height)
        except Exception:
            logger.debug("PyMuPDF: get_image_rects failed", exc_info=True)
            continue
    return covered / area


def classify_pdf_text_layer(pdf_bytes: bytes) -> PdfTextLayer:
    """Classify each page's text layer as content or scan-stamp noise.

    This is the canonical answer to "can I read this PDF for free, or do I
    need vision?" — prefer it over calling `extract_pdf_text` and testing
    the result for emptiness, which cannot tell a matrícula from the
    signature stamp printed over one.

    Never raises. Returns no pages when the PDF cannot be opened at all,
    which callers already treat as an unusable upload.

    Degraded mode: measuring image coverage needs PyMuPDF. Without it, the
    per-page structural signal is unavailable, so the whole document is
    classified as a single synthetic page against the character floor.
    That is weaker — it is the pre-existing behaviour — but it is reported
    honestly through `pages` having length 1 for a multi-page document, so
    a caller can tell that per-page routing is not on offer.
    """
    if not pdf_bytes:
        return PdfTextLayer(pages=(), tooling_available=pdf_text_tooling_available())

    try:
        import fitz  # type: ignore  # PyMuPDF
    except ImportError:
        return _classify_without_pymupdf(pdf_bytes)

    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception:
        logger.debug("PyMuPDF: failed to open document for classification", exc_info=True)
        return _classify_without_pymupdf(pdf_bytes)

    pages: list[PdfPage] = []
    try:
        for index in range(doc.page_count):
            page = doc[index]
            try:
                text = page.get_text().strip()
            except Exception:
                logger.debug("PyMuPDF: get_text failed on page %d", index + 1, exc_info=True)
                text = ""
            substantive, reason = _classify_page(text, _page_image_coverage(page))
            pages.append(
                PdfPage(
                    number=index + 1,
                    text=text,
                    is_substantive=substantive,
                    reason=reason,
                )
            )
    except Exception:
        logger.debug("PyMuPDF: page walk failed", exc_info=True)
    finally:
        doc.close()

    return PdfTextLayer(pages=tuple(pages), tooling_available=True)


def _classify_without_pymupdf(pdf_bytes: bytes) -> PdfTextLayer:
    """Whole-document fallback when per-page structure is unavailable."""
    text, tooling = _extract_pdf_text_with_signal(pdf_bytes)
    limpo = (text or "").strip()
    if not limpo:
        return PdfTextLayer(pages=(), tooling_available=tooling)
    substantive, reason = _classify_page(limpo, 0.0)
    return PdfTextLayer(
        pages=(PdfPage(number=1, text=limpo, is_substantive=substantive, reason=reason),),
        tooling_available=tooling,
    )


__all__ = [
    "PdfPage",
    "PdfTextLayer",
    "classify_pdf_text_layer",
    "extract_pdf_text",
    "pdf_text_tooling_available",
    "strip_provenance_stamps",
]
