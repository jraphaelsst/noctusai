"""
Matrícula Text Extractor Service — Converts property registration PDFs to text
using PyMuPDF for page rendering and OpenAI Vision for OCR.

Pipeline: PDF bytes → PNG per page (PyMuPDF) → OpenAI Vision OCR → aggregated text.
"""
from __future__ import annotations

import asyncio
import base64
import io
import logging
from typing import Optional

import fitz  # PyMuPDF
import httpx

from noctusai_lib.credentials import resolve_credential

logger = logging.getLogger(__name__)

# Image DPI for OCR quality — 200 balances quality vs. token cost
RENDER_DPI = 200


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
    api_key: str,
    client: httpx.AsyncClient,
) -> str:
    """Send a single page image to OpenAI Vision for text extraction."""
    b64 = base64.b64encode(image_bytes).decode()
    resp = await client.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": "gpt-4.1-mini",
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Extract the exact text from the provided image. "
                        "Return only the text content exactly as it appears in the document, "
                        "without corrections, formatting changes, or any modifications."
                    ),
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{b64}",
                                "detail": "high",
                            },
                        },
                    ],
                },
            ],
            "max_tokens": 4096,
        },
        timeout=120.0,
    )
    data = resp.json()
    text = data["choices"][0]["message"]["content"]
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

        # OCR each page (sequential to respect rate limits)
        page_texts: list[str] = []
        async with httpx.AsyncClient() as client:
            for i, img in enumerate(images, 1):
                text = await _ocr_page(img, i, num_paginas, api_key, client)
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
