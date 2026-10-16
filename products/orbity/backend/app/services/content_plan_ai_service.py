"""
AI generation of content-plan items (preview only — nothing is persisted here).

Goes through the SEED LLM layer (`noctusai_lib.integrations.llm.chat_completion`):
provider abstraction + per-org key resolution + cost governance (budget
guardrail + usage sink). No product code talks to a provider directly and
there is no gateway of our own.

Contract:
  * The model must return JSON `{"items": [...]}`. The output is validated
    STRICTLY: exact item count, every post_date inside [start, start+period]
    and on an allowed weekday, platform among the requested ones, non-empty
    title, no repeat of an existing theme. One corrective retry is allowed;
    after that the request fails with ContentPlanAIInvalidOutput (502) —
    never a partial / invented result.
  * AI not configured (no key for the provider) -> ContentPlanAINotConfigured
    (the router answers an honest 503). Never fake output.
  * The final caption/copy is NOT generated here (same rule as upstream:
    "legenda é criada em outra etapa"); the model supplies title + operational
    description only.

Consent: agency-authored briefing about a business client, not personal data
of the logged user, so no per-user ai_consent feature is registered.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any, Optional

from noctusai_lib.integrations.llm import chat_completion
from noctusai_lib.integrations.llm.exceptions import LLMNotConfigured
from noctusai_lib.primitives.not_configured import IntegrationNotConfigured
from noctusai_lib.primitives.parsing import safe_json_loads

from app.schemas.content_plans import AIGenerateParams, AIGeneratedItem

logger = logging.getLogger(__name__)

PROMPT_VERSION = "orbity-content-plan-items@v1"
_WEEKDAY_NAMES = ["Domingo", "Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado"]

_SYSTEM = (
    "Você é um estrategista de conteúdo para redes sociais de uma agência de "
    "marketing digital. Gere itens de planejamento de conteúdo coerentes com a "
    "estratégia do plano e com o briefing. Cada item tem título curto e uma "
    "descrição operacional do que deve ser produzido (roteiro, headline, texto "
    "da arte, CTA). NUNCA escreva a legenda final. Responda em português do "
    "Brasil, SOMENTE com JSON válido no formato:\n"
    '{"items": [{"title": "...", "description": "...", "format": "...", '
    '"platform": "...", "post_date": "YYYY-MM-DD", "reference_notes": "..."|null}]}'
)


class ContentPlanAINotConfigured(RuntimeError, IntegrationNotConfigured):
    """No LLM credential available — honest 503, never fake output."""


class ContentPlanAIInvalidOutput(RuntimeError):
    """The model output failed strict validation even after the retry."""


def window_end(params: AIGenerateParams) -> date:
    return params.start_date + timedelta(days=params.period_days)


def js_weekday(d: date) -> int:
    """0 = Domingo ... 6 = Sábado (python's Monday=0 shifted)."""
    return (d.weekday() + 1) % 7


def build_user_prompt(
    params: AIGenerateParams,
    *,
    plan: dict[str, Any],
    client_name: Optional[str],
    existing_items: list[dict[str, Any]],
) -> str:
    end = window_end(params)
    allowed = ", ".join(_WEEKDAY_NAMES[d] for d in params.weekdays)
    ctx = plan.get("strategy_context") or {}
    tone = params.tone
    if tone and params.tone_custom:
        tone = f"{tone} ({params.tone_custom})"
    lines = [
        f'Plano: "{plan.get("title", "")}" (cliente: {client_name or "n/d"}, mês {plan.get("month", "")})',
        f"Estratégia do plano: {ctx['notes']}" if ctx.get("notes") else None,
        f"Foco estratégico do plano: {ctx['strategicFocus']}" if ctx.get("strategicFocus") else None,
        f"Público do plano: {ctx['targetAudience']}" if ctx.get("targetAudience") else None,
        "",
        "BRIEFING DESTA GERAÇÃO:",
        f"- Quantidade: EXATAMENTE {params.items_count} conteúdos",
        f"- Janela: {params.start_date.isoformat()} até {end.isoformat()} (inclusive)",
        f"- Dias permitidos: {allowed}",
        f"- Plataformas permitidas (use exatamente estes valores em `platform`): {', '.join(params.platforms)}",
        f"- Formatos preferidos: {', '.join(params.formats)}" if params.formats else None,
        f"- Objetivo principal: {params.objective}" if params.objective else None,
        f"- Tom de voz: {tone}" if tone else None,
        f"- Público-alvo: {params.audience}" if params.audience else None,
        f"- Pilares de conteúdo: {', '.join(params.pillars)}" if params.pillars else None,
        f"- Mix sugerido: {params.mix_distribution}" if params.mix_distribution else None,
        "- CTA de venda direta: "
        + ("permitido" if params.allow_sales_cta else "NÃO permitido - evite posts de venda direta"),
        f"- Tema desta leva: {params.focus}" if params.focus else None,
        f"- EVITAR: {params.avoid}" if params.avoid else None,
        f"- Referências: {params.references}" if params.references else None,
    ]
    if existing_items:
        lines.append("")
        lines.append("CONTEÚDOS JÁ PLANEJADOS (NÃO repita temas/títulos):")
        for it in existing_items[:60]:
            lines.append(
                f'- {it.get("title", "")} | {it.get("format") or "-"} | '
                f'{it.get("platform") or "-"} | {it.get("post_date") or "-"}'
            )
    return "\n".join(line for line in lines if line is not None)


def validate_output(
    raw: str,
    params: AIGenerateParams,
    existing_titles: set[str],
) -> tuple[list[AIGeneratedItem], list[str]]:
    """Return (items, errors). `errors` empty <=> output is acceptable."""
    parsed = safe_json_loads(raw)
    if not isinstance(parsed, dict) or not isinstance(parsed.get("items"), list):
        return [], ['A resposta não é um JSON no formato {"items": [...]}']
    errors: list[str] = []
    raw_items = parsed["items"]
    if len(raw_items) != params.items_count:
        errors.append(f"Esperados exatamente {params.items_count} itens, recebidos {len(raw_items)}")
    end = window_end(params)
    items: list[AIGeneratedItem] = []
    seen_titles: set[str] = set()
    for idx, entry in enumerate(raw_items, start=1):
        if not isinstance(entry, dict):
            errors.append(f"Item {idx} não é um objeto")
            continue
        try:
            item = AIGeneratedItem.model_validate(
                {
                    "title": str(entry.get("title") or "").strip()[:255],
                    "description": entry.get("description"),
                    "format": entry.get("format"),
                    "platform": str(entry.get("platform") or "").strip().lower(),
                    "post_date": entry.get("post_date"),
                    "reference_notes": entry.get("reference_notes"),
                }
            )
        except ValueError as exc:
            errors.append(f"Item {idx} inválido: {exc.__class__.__name__}")
            continue
        if not item.title:
            errors.append(f"Item {idx} sem título")
            continue
        if item.platform not in params.platforms:
            errors.append(f"Item {idx}: plataforma '{item.platform}' fora das permitidas")
        if not (params.start_date <= item.post_date <= end):
            errors.append(f"Item {idx}: data {item.post_date} fora da janela {params.start_date}..{end}")
        elif js_weekday(item.post_date) not in params.weekdays:
            errors.append(f"Item {idx}: data {item.post_date} em dia da semana não permitido")
        key = item.title.casefold()
        if key in existing_titles or key in seen_titles:
            errors.append(f"Item {idx}: título repetido '{item.title}'")
        seen_titles.add(key)
        items.append(item)
    return items, errors


async def generate_plan_items(
    params: AIGenerateParams,
    *,
    plan: dict[str, Any],
    client_name: Optional[str],
    existing_items: list[dict[str, Any]],
    org_id: str,
) -> list[AIGeneratedItem]:
    """Generate + strictly validate `params.items_count` new plan items."""
    prompt = build_user_prompt(
        params, plan=plan, client_name=client_name, existing_items=existing_items
    )
    existing_titles = {str(i.get("title", "")).casefold() for i in existing_items}
    messages: list[dict[str, str]] = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": prompt},
    ]
    errors: list[str] = []
    for attempt in (1, 2):
        try:
            raw = await chat_completion(
                messages=messages,
                temperature=0.7,
                response_format={"type": "json_object"},
                cache=False,
                org_id=org_id,
            )
        except LLMNotConfigured as exc:
            raise ContentPlanAINotConfigured(str(exc)) from exc
        items, errors = validate_output(raw, params, existing_titles)
        if not errors:
            return items
        logger.warning(
            "orbity.content_plan_ai invalid output org=%s attempt=%d prompt=%s errors=%s",
            org_id, attempt, PROMPT_VERSION, errors[:5],
        )
        messages = messages + [
            {"role": "assistant", "content": raw},
            {
                "role": "user",
                "content": "A resposta anterior foi rejeitada pelos seguintes motivos:\n- "
                + "\n- ".join(errors[:8])
                + "\nCorrija e responda novamente SOMENTE com o JSON completo.",
            },
        ]
    raise ContentPlanAIInvalidOutput("; ".join(errors[:5]))
