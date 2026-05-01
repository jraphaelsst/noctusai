"""Mailing AI wrappers — thin `chat_completion` calls for the Mailing UI.

Five features landed in `ai-expansion` Phase 14 (2026-04-24):
  * M1 — Subject-line generator (3–5 variants labeled by tone).
  * M2 — Template content draft (responsive-HTML-aware prompt).
  * M5 — Re-engagement copy (3 tone variants for inactive contacts).
  * M6 — Spam/deliverability review (flags risky phrasing, missing unsubscribe, link density).
  * M7 — Multilingual translation (PT↔EN/ES/FR; preserves template HTML).

All five are low-LGPD (no PII in prompts beyond the marketer's own email copy),
low-effort (thin wrappers), and use the shared `noctusai_lib.llm.chat_completion`
with `cache=True` for cacheable deterministic calls.

Prompt version: bump `PROMPT_VERSION` manually when prompt shape changes so
the response cache keys rotate (per `ai-expansion` §7 Q4).
"""
from __future__ import annotations

import logging
from typing import Optional

from noctusai_lib.integrations.llm import chat_completion
from noctusai_lib.integrations.llm.exceptions import LLMNotConfigured
from noctusai_lib.primitives.parsing import safe_json_loads as _safe_json_loads

logger = logging.getLogger(__name__)

PROMPT_VERSION = "mailing-ai@v1"


# ---------------------------------------------------------------------------
# M1 — Subject-line generator
# ---------------------------------------------------------------------------

_SUBJECT_SYSTEM = """Você é especialista em copy de email marketing em português.
Dado um resumo da campanha, gere 3 a 5 opções de assunto, cada uma rotulada com o tom:
- urgência: senso de prazo/agora
- curiosidade: desperta interesse sem revelar tudo
- direto: comunica benefício claramente
- social: usa prova social ou comunidade
- benefício: foca no ganho do destinatário

Responda SOMENTE JSON válido no formato:
[{"text": "...", "tone": "urgência|curiosidade|direto|social|benefício"}, ...]
Assuntos têm no máximo 60 caracteres. Não use emojis."""


async def generate_subjects(campaign_summary: str, *, org_id: Optional[str] = None) -> list[dict]:
    """Generate 3–5 subject-line variants for a campaign summary.

    Returns `[{"text": str, "tone": str}, ...]`. Empty list on LLM-not-configured
    so the UI can degrade to a manual-entry flow.
    """
    try:
        raw = await chat_completion(
            messages=[
                {"role": "system", "content": _SUBJECT_SYSTEM},
                {"role": "user", "content": f"Resumo da campanha:\n{campaign_summary}"},
            ],
            temperature=0.0,
            cache=True,
            org_id=org_id,
        )
    except (LLMNotConfigured, RuntimeError):
        logger.warning("mailing.ai.generate_subjects: LLM not configured — returning empty list")
        return []

    parsed = _safe_json_loads(raw)
    if not isinstance(parsed, list):
        return []
    return [
        {"text": str(item.get("text", "")), "tone": str(item.get("tone", "direto"))}
        for item in parsed
        if isinstance(item, dict) and item.get("text")
    ][:5]


# ---------------------------------------------------------------------------
# M2 — Template content draft
# ---------------------------------------------------------------------------

_TEMPLATE_SYSTEM = """Você é redator de email marketing em português.
Produza um corpo de email HTML responsivo (mobile-first) com:
- heading curto <h1>
- parágrafo de introdução <p>
- 1-2 bullets <ul><li>
- call-to-action <a> com estilo inline
- assinatura genérica
Máximo 200 palavras. Não inclua <html>/<head>/<body> — apenas o conteúdo central.
NÃO escreva texto fora do HTML. Responda APENAS o HTML."""


async def draft_template(prompt: str, *, org_id: Optional[str] = None) -> str:
    """Generate an HTML email body for a given prompt.

    Returns an empty string on LLM-not-configured; UI can fall back to blank
    editor.
    """
    try:
        raw = await chat_completion(
            messages=[
                {"role": "system", "content": _TEMPLATE_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            cache=True,
            org_id=org_id,
        )
    except (LLMNotConfigured, RuntimeError):
        logger.warning("mailing.ai.draft_template: LLM not configured — returning empty string")
        return ""
    return raw.strip()


# ---------------------------------------------------------------------------
# M5 — Re-engagement copy variants
# ---------------------------------------------------------------------------

_REENG_SYSTEM = """Você é especialista em reengajamento de email marketing.
Produza 3 variantes de email de reengajamento em português para um segmento
de contatos inativos há 90+ dias. Cada variante usa um tom diferente:
- leve/humor
- direto/transparente
- valor/oferta

Responda SOMENTE JSON válido:
[{"tone": "leve|direto|valor", "subject": "...", "body_html": "<p>...</p>"}, ...]
Assunto ≤ 60 caracteres. Corpo ≤ 150 palavras, HTML com <p> e <a> apenas."""


async def reengagement_variants(context: str, *, org_id: Optional[str] = None) -> list[dict]:
    """Generate 3 re-engagement email variants (tone: leve/direto/valor).

    `context` describes the segment (e.g., "clientes que compraram há 6-12 meses").
    Returns list of `{tone, subject, body_html}`; empty on LLMNotConfigured.
    """
    try:
        raw = await chat_completion(
            messages=[
                {"role": "system", "content": _REENG_SYSTEM},
                {"role": "user", "content": f"Contexto do segmento:\n{context}"},
            ],
            temperature=0.0,
            cache=True,
            org_id=org_id,
        )
    except (LLMNotConfigured, RuntimeError):
        logger.warning("mailing.ai.reengagement_variants: LLM not configured — returning empty list")
        return []
    parsed = _safe_json_loads(raw)
    if not isinstance(parsed, list):
        return []
    return [
        {
            "tone": str(item.get("tone", "direto")),
            "subject": str(item.get("subject", "")),
            "body_html": str(item.get("body_html", "")),
        }
        for item in parsed
        if isinstance(item, dict) and item.get("subject")
    ][:3]


# ---------------------------------------------------------------------------
# M6 — Spam / deliverability review
# ---------------------------------------------------------------------------

_DELIVERABILITY_SYSTEM = """Você é auditor de entregabilidade de email marketing.
Analise o HTML fornecido e retorne uma lista de achados.

Para cada achado: severity in ["info", "warning", "error"]; codigo pertencente a um destes:
- risky_phrasing: palavras/frases spammy em português
- missing_unsubscribe: sem link/trecho claro de descadastro
- link_heavy: mais de 5 links no corpo
- all_caps: texto em caixa-alta exagerada
- misleading_subject: assunto não casa com o corpo (só se `subject` for fornecido)
- tracking_only_urls: muitos links de tracking obscuros

Responda SOMENTE JSON válido:
{"findings": [{"code": "...", "severity": "...", "message": "..."}, ...]}
Se nada for encontrado, `findings` é []."""


async def review_deliverability(
    html: str, *, subject: Optional[str] = None, org_id: Optional[str] = None
) -> dict:
    """Return `{"findings": [{code, severity, message}, ...]}` for an email body."""
    user_block = f"Subject: {subject or ''}\n\nHTML:\n{html}"
    try:
        raw = await chat_completion(
            messages=[
                {"role": "system", "content": _DELIVERABILITY_SYSTEM},
                {"role": "user", "content": user_block},
            ],
            temperature=0.0,
            cache=True,
            org_id=org_id,
        )
    except (LLMNotConfigured, RuntimeError):
        logger.warning("mailing.ai.review_deliverability: LLM not configured")
        return {"findings": []}
    parsed = _safe_json_loads(raw)
    if not isinstance(parsed, dict) or not isinstance(parsed.get("findings"), list):
        return {"findings": []}
    return {
        "findings": [
            {
                "code": str(f.get("code", "")),
                "severity": str(f.get("severity", "info")),
                "message": str(f.get("message", "")),
            }
            for f in parsed["findings"]
            if isinstance(f, dict) and f.get("code")
        ]
    }


# ---------------------------------------------------------------------------
# M7 — Multilingual translation
# ---------------------------------------------------------------------------

_TRANSLATE_SYSTEM_FMT = """Você traduz email marketing de português para {target_lang}.
Preserve EXATAMENTE a estrutura HTML (tags, atributos, classes, estilos inline).
Traduza APENAS conteúdo de texto dentro das tags. Mantenha placeholders como {{nome}}, {{empresa}} intactos.
NÃO adicione texto fora do HTML original. Responda APENAS o HTML traduzido."""

_SUPPORTED_LANGS = {
    "en": "inglês (American English)",
    "es": "espanhol (Spanish, neutro)",
    "fr": "francês (French, de France)",
}


async def translate_template(html: str, target_lang: str, *, org_id: Optional[str] = None) -> str:
    """Translate HTML email body from PT to a supported target language.

    Supported targets: 'en', 'es', 'fr'. Returns original html unchanged on
    unsupported target or LLMNotConfigured.
    """
    if target_lang not in _SUPPORTED_LANGS:
        logger.warning("mailing.ai.translate_template: unsupported target_lang=%r", target_lang)
        return html
    system_prompt = _TRANSLATE_SYSTEM_FMT.format(target_lang=_SUPPORTED_LANGS[target_lang])
    try:
        raw = await chat_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": html},
            ],
            temperature=0.0,
            cache=True,
            org_id=org_id,
        )
    except (LLMNotConfigured, RuntimeError):
        logger.warning("mailing.ai.translate_template: LLM not configured — returning original")
        return html
    return raw.strip()


__all__ = [
    "PROMPT_VERSION",
    "generate_subjects",
    "draft_template",
    "reengagement_variants",
    "review_deliverability",
    "translate_template",
]
