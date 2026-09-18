"""
Matrícula Text Extractor Service — the product's half of transcription.

The ladder itself now lives in the seed:
`noctusai_lib.integrations.documents.make_document_transcriber` decides,
per page, whether the PDF's own text layer is real content or a scan's
signature stamp, and rasterizes → vision only for the pages it cannot
read. That module carries the history this file used to carry alone.

WHAT STAYS HERE
---------------
The `matricula_extracoes` row and its status lifecycle, and the mapping
from a machine error code to a sentence this product's users can act on.
That mapping is the reason the seed returns codes rather than prose: a
chatbot surfacing the same failure over WhatsApp needs different words
than a settings screen does.

WHY THE LADDER LEFT
-------------------
It was here, product-local, and every lesson the seed's document family
learned had to be re-learned here one incident at a time — rung 1 on
2026-08-24, then per-page routing and the scan-stamp defect on
2026-08-25, when a CERTIDÃO DE MATRÍCULA came back transcribed as three
copies of its own ONR validation stamp. `certidoes_service` needed the
same ladder, and social-wiring's inbound-document path will make three.
"""
from __future__ import annotations

import logging
from typing import Callable, Optional

from noctusai_lib.config.credentials import resolve_credential
from noctusai_lib.integrations.documents import make_document_transcriber
from noctusai_lib.integrations.documents.transcription import OCR_MODELS
from noctusai_lib.integrations.llm import resolve_llm_provider

logger = logging.getLogger(__name__)

#: Machine error code → what this product's users should read.
#:
#: Anything not listed here is a bug rather than a condition the user can
#: act on, so it falls through to `_MENSAGEM_PADRAO` WITH the developer
#: message attached — a generic apology that hides the cause is how a
#: silent error survives to production.
_MENSAGENS: dict[str, str] = {
    "no_pages": "PDF sem páginas — verifique se o arquivo não está corrompido.",
    "empty_document": "Arquivo vazio — envie o PDF da matrícula novamente.",
    "missing_credentials": (
        "OpenAI API Key não configurada. "
        "Acesse Configurações > Chaves de API para configurar."
    ),
    "too_many_vision_pages": (
        "Documento muito longo para transcrição automática. "
        "Envie a matrícula em partes menores."
    ),
    "rasterize_failed": (
        "Não foi possível ler todas as páginas do PDF. "
        "Verifique se o arquivo não está corrompido."
    ),
}

_MENSAGEM_PADRAO = "Erro inesperado: {detalhe}"


def _mensagem_de_erro(resultado) -> str:
    """Render a transcription failure for this product's users."""
    conhecida = _MENSAGENS.get(resultado.error or "")
    if conhecida:
        return conhecida
    return _MENSAGEM_PADRAO.format(
        detalhe=resultado.error_message or resultado.error or "desconhecido"
    )


async def processar_extracao(
    extracao_id: str,
    pdf_bytes: bytes,
    org_id: Optional[str],
    db,
    transcriber=None,
    provider_resolver: Callable[..., str] = resolve_llm_provider,
    transcriber_factory: Callable[..., object] = make_document_transcriber,
) -> None:
    """Full extraction pipeline — runs as a background task.

    `transcriber` is a test seam: pass one directly to skip construction
    (and provider resolution) entirely.

    `provider_resolver` / `transcriber_factory` are two narrower test seams
    — bound defaults (per `KB § PATTERNS/backend/di-test-seam.md` Class-B),
    never patched — so a test can assert the vision-provider switch is
    wired without faking `transcriber` itself. `provider_resolver` defaults
    to `resolve_llm_provider`, which reads `org_settings`'s
    `llm_vision_provider` row (unset today for every org, so this call is
    behaviour-preserving); `transcriber_factory` defaults to the real seed
    `make_document_transcriber`.
    """
    try:
        db.table("matricula_extracoes").update({
            "status": "processando",
        }).eq("id", extracao_id).execute()

        if transcriber is None:
            # 🔴 Manual switch, not a fallback — see `resolve_llm_provider`'s
            # module docstring. Unset (the default state for every org today)
            # resolves to "openai", so this is behaviour-preserving; an
            # operator flips a single `org_settings` row
            # (`llm_vision_provider`) to move THIS org's matrícula reading to
            # Anthropic without a code change, the same lever already used
            # for social-wiring on 2026-09-17.
            provider = provider_resolver(
                "vision", org_id, allowed=tuple(OCR_MODELS)
            )
            transcriber = transcriber_factory(
                real=True, org_id=org_id, provider=provider
            )

        resultado = await transcriber.transcribe(
            pdf_bytes, mimetype="application/pdf"
        )

        if not resultado.ok:
            logger.warning(
                "Matrícula %s: transcription failed (%s) %s",
                extracao_id, resultado.error, resultado.error_message or "",
            )
            db.table("matricula_extracoes").update({
                "status": "erro",
                "erro_mensagem": _mensagem_de_erro(resultado),
            }).eq("id", extracao_id).execute()
            return

        logger.info(
            "Matrícula %s: %d pages — %d from text layer, %d via vision",
            extracao_id,
            resultado.num_paginas,
            len(resultado.paginas_por_camada),
            len(resultado.paginas_por_visao),
        )

        db.table("matricula_extracoes").update({
            "status": "concluida",
            "texto_extraido": resultado.text,
            "num_paginas": resultado.num_paginas,
        }).eq("id", extracao_id).execute()

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
