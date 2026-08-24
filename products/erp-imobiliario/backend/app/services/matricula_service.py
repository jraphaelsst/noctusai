"""
Matrícula Text Extractor Service — property registration PDFs to text.

THE LADDER
----------
1. **The PDF's own text layer** (`noctusai_lib.integrations.media.
   extract_pdf_text`) — free, exact, no API key required. Cartórios issue
   digitally-generated matrículas, and those carry a perfectly good text
   layer.
2. **Rasterize → vision**, one page at a time (PyMuPDF → seed
   `analyze_image`) — for scans and photographs, where there is no text
   layer to read.

🔴 RUNG 1 WAS MISSING UNTIL 2026-08-24, AND THAT WAS THE WHOLE COST PROBLEM.
This service used to rasterize every page of every PDF and pay for a vision
call on each one, including for documents whose text was already sitting
there in machine-readable form. Vision transcription is also *approximate*
where a text layer is exact, so the old path was paying money to make the
output worse.

Note what rung 1 does NOT change: the vision rung stays PAGE-BY-PAGE. That
is not the inefficiency. Vision models consume images, so a PDF must be
rasterized either way, and the image tokens dominate the bill whether they
arrive in one request or several. Page-scoped requests also drift and
truncate less than one long multi-page transcription. The waste was never
the batching; it was calling vision at all on a document that did not need
it.

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

logger = logging.getLogger(__name__)

# Image DPI for OCR quality — 200 balances quality vs. token cost
RENDER_DPI = 200

# Pinned model for OCR (separate from the chat-MODEL pin in ai_service.py).
# gpt-4.1-mini balances cost + page-throughput; tune here, not at the call site.
_OCR_MODEL = "gpt-4.1-mini"

#: A scanned page often carries a few dozen characters of junk text (a header
#: stamp, a digital-signature footer) without being machine-readable at all.
#: Requiring a real average per page is what separates "this PDF has a text
#: layer" from "this PDF has a smudge of text on it". A genuine matrícula page
#: runs to thousands of characters, so the bar is deliberately low and still
#: unambiguous.
MIN_CHARS_POR_PAGINA = 100

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


def _texto_da_camada(pdf_bytes: bytes, num_paginas: int) -> Optional[str]:
    """Rung 1: the PDF's own text layer, or None if it does not really have one.

    Never raises — a failure here must fall through to the vision rung rather
    than failing an extraction that rung 2 could have completed.
    """
    if num_paginas <= 0:
        return None
    try:
        from noctusai_lib.integrations.media import extract_pdf_text

        texto = extract_pdf_text(pdf_bytes) or ""
    except ImportError:
        logger.debug("matricula: extract_pdf_text unavailable — using vision")
        return None
    except Exception:
        logger.debug("matricula: text-layer extraction failed", exc_info=True)
        return None

    limpo = texto.strip()
    if len(limpo) < MIN_CHARS_POR_PAGINA * num_paginas:
        return None
    return limpo


def _pdf_to_images(pdf_bytes: bytes) -> list[bytes]:
    """Convert each PDF page to a PNG image using PyMuPDF.

    Returns a list of PNG byte arrays, one per page.
    """
    images: list[bytes] = []
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        zoom = RENDER_DPI / 72  # 72 is the default PDF DPI
        matrix = fitz.Matrix(zoom, zoom)
        for page in doc:
            pix = page.get_pixmap(matrix=matrix)
            images.append(pix.tobytes("png"))
    finally:
        doc.close()
    return images


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
    2. Try the PDF's own text layer — free, exact, no API key
    3. Failing that: convert to images and OCR each page with vision
    4. Aggregate and store extracted text
    """
    try:
        db.table("matricula_extracoes").update({
            "status": "processando",
        }).eq("id", extracao_id).execute()

        # ── Rung 1: the PDF's own text layer ─────────────────────────
        #
        # Deliberately BEFORE the API-key check: a digitally-issued matrícula
        # needs no key, no vision call and no rasterization, so an org that
        # has not configured OpenAI at all can still extract one. Checking the
        # key first would refuse work we are perfectly able to do.
        num_paginas = _contar_paginas(pdf_bytes)
        if num_paginas == 0:
            db.table("matricula_extracoes").update({
                "status": "erro",
                "erro_mensagem": "PDF sem páginas — verifique se o arquivo não está corrompido.",
            }).eq("id", extracao_id).execute()
            return

        texto_camada = _texto_da_camada(pdf_bytes, num_paginas)
        if texto_camada:
            logger.info(
                "Matrícula %s: text layer used — %d pages, %d chars, 0 vision calls",
                extracao_id, num_paginas, len(texto_camada),
            )
            db.table("matricula_extracoes").update({
                "status": "concluida",
                "texto_extraido": texto_camada,
                "num_paginas": num_paginas,
            }).eq("id", extracao_id).execute()
            return

        # ── Rung 2: rasterize → vision, one page at a time ────────────
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

        # PDF → images
        images = _pdf_to_images(pdf_bytes)
        num_paginas = len(images)
        logger.info("Matrícula %s: %d pages to OCR", extracao_id, num_paginas)

        db.table("matricula_extracoes").update({
            "num_paginas": num_paginas,
        }).eq("id", extracao_id).execute()

        # OCR each page (sequential to respect rate limits).
        # Seed `analyze_image` owns its own httpx client + provider routing;
        # no per-call AsyncClient context needed here.
        page_texts: list[str] = []
        for i, img in enumerate(images, 1):
            text = await _ocr_page(img, i, num_paginas, org_id)
            page_texts.append(text)

        # Aggregate
        full_text = "\n\n".join(page_texts)

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
