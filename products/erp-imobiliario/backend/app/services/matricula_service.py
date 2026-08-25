"""
Matrícula Text Extractor Service — property registration PDFs to text.

THE LADDER, PAGE BY PAGE
------------------------
1. **The PDF's own text layer** — free, exact, no API key required.
   Cartórios issue digitally-generated matrículas, and those carry a
   perfectly good text layer.
2. **Rasterize → vision** for the pages that rung 1 cannot read.

The rungs are decided PER PAGE, not per document, because Brazilian
matrículas are genuinely mixed: a digitally-issued body with a scanned
averbação stapled on the end is ordinary. Whole-document routing has to
pick one rung for both halves and pays for vision on pages it could have
read for free.

🔴 WHAT COUNTS AS "HAS A TEXT LAYER" IS THE WHOLE PROBLEM.
A cartório scan is a page-sized JPEG with a digital-signature stamp
overlaid as real, selectable text. So `extract_pdf_text` returns
something non-empty and completely worthless. This service used to accept
any page averaging 100+ characters, and a 3-page CERTIDÃO DE MATRÍCULA
(137 chars/page of ONR validation stamp) cleared that bar — the user got
"Valide este documento clicando no link a seguir: ..." three times over
and none of the actual matrícula, because the content never left the JPEG.

The verdict now comes from `noctusai_lib.integrations.media.
classify_pdf_text_layer`, which leads with a STRUCTURAL signal — a page
whose raster images cover the page area is a rendered scan, however chatty
its stamp — rather than a character count that any longer boilerplate
defeats. That predicate lives in the seed because four call sites across
the fleet were each answering this same question with their own wrong
threshold.

Note what none of this changes: the vision rung stays PAGE-BY-PAGE. Vision
models consume images, so a page must be rasterized either way, and image
tokens dominate the bill whether they arrive in one request or several.
Page-scoped requests also drift and truncate less than one long multi-page
transcription.

Refactored 2026-05-11 (LLM-ERP rollout, Step A): replaced raw
`httpx.post("https://api.openai.com/v1/chat/completions", ...)` with
`noctusai_lib.integrations.llm.analyze_image`. Goes through the seed
provider registry → inherits seed cache / budget / (future) audit hooks
which the raw-httpx path bypassed.
"""
from __future__ import annotations

import logging
from typing import Optional

import fitz  # PyMuPDF

from noctusai_lib.config.credentials import resolve_credential
from noctusai_lib.integrations.llm import analyze_image
from noctusai_lib.integrations.media import classify_pdf_text_layer

logger = logging.getLogger(__name__)

# Image DPI for OCR quality — 200 balances quality vs. token cost
RENDER_DPI = 200

# Pinned model for OCR (separate from the chat-MODEL pin in ai_service.py).
# gpt-4.1-mini balances cost + page-throughput; tune here, not at the call site.
_OCR_MODEL = "gpt-4.1-mini"

_OCR_PROMPT = (
    "Extract the exact text from the provided image. "
    "Return only the text content exactly as it appears in the document, "
    "without corrections, formatting changes, or any modifications."
)


def _contar_paginas(pdf_bytes: bytes) -> int:
    """Page count without rendering anything.

    Returns 0 for bytes PyMuPDF cannot open at all, so a corrupt upload
    reaches the "PDF sem páginas" message the user can act on rather than
    the generic "Erro inesperado" from the outer handler.
    """
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception:
        logger.debug("matricula: could not open PDF", exc_info=True)
        return 0
    try:
        return doc.page_count
    finally:
        doc.close()


def _pdf_to_images(
    pdf_bytes: bytes, paginas: Optional[list[int]] = None
) -> dict[int, bytes]:
    """Rasterize pages to PNG, keyed by 1-based page number.

    `paginas` restricts the render to the pages that actually need vision.
    Rasterizing a page whose text we already read for free is wasted CPU,
    and once that image reaches `_ocr_page` it is wasted money too. Keying
    by page number (rather than returning a list) is what lets the caller
    interleave OCR'd pages with text-layer pages back in document order.
    """
    images: dict[int, bytes] = {}
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        zoom = RENDER_DPI / 72  # 72 is the default PDF DPI
        matrix = fitz.Matrix(zoom, zoom)
        alvo = set(paginas) if paginas is not None else None
        for index in range(doc.page_count):
            numero = index + 1
            if alvo is not None and numero not in alvo:
                continue
            pix = doc[index].get_pixmap(matrix=matrix)
            images[numero] = pix.tobytes("png")
    finally:
        doc.close()
    return images


def _texto_confiavel_por_pagina(camada, num_paginas: int) -> dict[int, str]:
    """Page number → text we can trust without a vision call.

    Per-page routing only works when the classifier actually saw every
    page. Without PyMuPDF the seed degrades to one synthetic page covering
    the whole document (documented on `classify_pdf_text_layer`), and
    mixing that with page-scoped OCR would attribute the entire document's
    text to page 1. So when the counts disagree we take nothing for free
    and send every page to vision — costlier, but never wrong.
    """
    if len(camada.pages) != num_paginas:
        return {}
    return {p.number: p.text for p in camada.pages if p.is_substantive}


async def _ocr_page(
    image_bytes: bytes,
    page_num: int,
    total_pages: int,
    org_id: Optional[str],
) -> str:
    """Send a single page image to the seed vision wrapper for text extraction.

    Goes through `noctusai_lib.integrations.llm.analyze_image` so cache /
    budget / (future) audit hooks fire uniformly with the rest of the
    platform's LLM dispatches.
    """
    text = await analyze_image(
        image_bytes,
        _OCR_PROMPT,
        model=_OCR_MODEL,
        org_id=org_id,
        max_tokens=4096,
    )
    logger.info("OCR page %d/%d done (%d chars)", page_num, total_pages, len(text))
    return text


async def processar_extracao(extracao_id: str, pdf_bytes: bytes, org_id: Optional[str], db) -> None:
    """Full extraction pipeline — runs as a background task.

    1. Update status to processando
    2. Classify each page's text layer (free, exact where it is real)
    3. Rasterize + OCR only the pages the text layer cannot cover
    4. Reassemble in document order and store
    """
    try:
        db.table("matricula_extracoes").update({
            "status": "processando",
        }).eq("id", extracao_id).execute()

        num_paginas = _contar_paginas(pdf_bytes)
        if num_paginas == 0:
            db.table("matricula_extracoes").update({
                "status": "erro",
                "erro_mensagem": "PDF sem páginas — verifique se o arquivo não está corrompido.",
            }).eq("id", extracao_id).execute()
            return

        # ── Rung 1: the PDF's own text layer ─────────────────────────
        #
        # Deliberately BEFORE the API-key check: a digitally-issued matrícula
        # needs no key, no vision call and no rasterization, so an org that
        # has not configured OpenAI at all can still extract one. Checking the
        # key first would refuse work we are perfectly able to do.
        camada = classify_pdf_text_layer(pdf_bytes)

        if camada.is_substantive:
            texto = camada.text
            logger.info(
                "Matrícula %s: text layer used — %d pages, %d chars, 0 vision calls",
                extracao_id, num_paginas, len(texto),
            )
            db.table("matricula_extracoes").update({
                "status": "concluida",
                "texto_extraido": texto,
                "num_paginas": num_paginas,
            }).eq("id", extracao_id).execute()
            return

        # ── Rung 2: rasterize → vision, for the pages rung 1 missed ───
        textos: dict[int, str] = _texto_confiavel_por_pagina(camada, num_paginas)
        paginas_para_vision = [
            numero for numero in range(1, num_paginas + 1) if numero not in textos
        ]

        # Validate OpenAI key
        api_key = resolve_credential("openai_api_key", org_id)
        if not api_key:
            db.table("matricula_extracoes").update({
                "status": "erro",
                "erro_mensagem": (
                    "OpenAI API Key não configurada. "
                    "Acesse Configurações > Chaves de API para configurar."
                ),
            }).eq("id", extracao_id).execute()
            return

        logger.info(
            "Matrícula %s: %d pages — %d from text layer, %d to OCR",
            extracao_id, num_paginas, len(textos), len(paginas_para_vision),
        )

        db.table("matricula_extracoes").update({
            "num_paginas": num_paginas,
        }).eq("id", extracao_id).execute()

        # OCR each remaining page (sequential to respect rate limits).
        # Seed `analyze_image` owns its own httpx client + provider routing;
        # no per-call AsyncClient context needed here.
        images = _pdf_to_images(pdf_bytes, paginas_para_vision)
        for numero in paginas_para_vision:
            img = images.get(numero)
            if img is None:
                # Rasterization silently dropping a page would ship a
                # matrícula missing a page with status "concluida".
                raise RuntimeError(
                    f"não foi possível rasterizar a página {numero} de {num_paginas}"
                )
            textos[numero] = await _ocr_page(img, numero, num_paginas, org_id)

        # Reassemble in document order — text-layer and OCR'd pages interleaved
        full_text = "\n\n".join(
            textos[numero] for numero in sorted(textos) if textos[numero]
        )

        db.table("matricula_extracoes").update({
            "status": "concluida",
            "texto_extraido": full_text,
            "num_paginas": num_paginas,
        }).eq("id", extracao_id).execute()

        logger.info("Matrícula %s: extraction complete (%d chars)", extracao_id, len(full_text))

    except Exception as e:
        logger.error("Matrícula %s extraction failed: %s", extracao_id, e)
        db.table("matricula_extracoes").update({
            "status": "erro",
            "erro_mensagem": f"Erro inesperado: {e}",
        }).eq("id", extracao_id).execute()


def check_required_credentials(org_id: Optional[str] = None) -> list[str]:
    """Check which required credentials are missing for matrícula extraction.

    Still reports the key as required: it is needed for any SCANNED matrícula,
    and the caller cannot know in advance which kind will be uploaded. Since
    rung 1 landed, a digitally-issued PDF will extract without it — so this is
    a warning about what may fail, not a hard precondition for every document.
    """
    missing = []
    if not resolve_credential("openai_api_key", org_id):
        missing.append(
            "OpenAI API Key não configurada — necessária para extração de "
            "matrículas digitalizadas (PDFs com camada de texto não precisam)."
        )
    return missing
