"""
Matrícula Text Extractor Service — Converts property registration PDFs to text
using PyMuPDF for page rendering and the seed vision wrapper for OCR.

Pipeline: PDF bytes → PNG per page (PyMuPDF) → seed `analyze_image` OCR → aggregated text.

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

_OCR_PROMPT = (
    "Extract the exact text from the provided image. "
    "Return only the text content exactly as it appears in the document, "
    "without corrections, formatting changes, or any modifications."
)


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
    2. Convert PDF to images
    3. OCR each page with OpenAI Vision
    4. Aggregate and store extracted text
    """
    try:
        db.table("matricula_extracoes").update({
            "status": "processando",
        }).eq("id", extracao_id).execute()

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

        if num_paginas == 0:
            db.table("matricula_extracoes").update({
                "status": "erro",
                "erro_mensagem": "PDF sem páginas — verifique se o arquivo não está corrompido.",
            }).eq("id", extracao_id).execute()
            return

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
    """Check which required credentials are missing for matrícula extraction."""
    missing = []
    if not resolve_credential("openai_api_key", org_id):
        missing.append(
            "OpenAI API Key não configurada — necessária para extração de texto via IA."
        )
    return missing
