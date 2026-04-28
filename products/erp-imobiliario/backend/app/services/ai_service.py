"""
AI Service — multi-provider LLM features for property descriptions, lead
scoring, and pricing.

Dispatches via `noctusai_lib.llm` — the provider, model, and credential chain
are all inherited from the seed-injector. Product code stays free of provider
SDKs and HTTP plumbing.
"""
import logging
from typing import Any, Optional

from noctusai_lib.credentials import resolve_credential
from noctusai_lib.llm import chat_completion

logger = logging.getLogger(__name__)

# Chat model for the ERP copywriter / scoring / pricing flows. The seed
# default is `gpt-4o-mini` — we pin it explicitly here so tuning this
# service's model doesn't accidentally shift the rest of the platform.
MODEL = "gpt-4o-mini"


def check_openai_configured(org_id: Optional[str] = None) -> bool:
    """Check if OpenAI API key is available without raising."""
    return bool(resolve_credential("openai_api_key", org_id))


async def generate_description(imovel_data: dict) -> dict:
    """
    Generate a marketing description for a property listing.
    Returns {descricao, titulo_sugerido}.
    """
    tipo = imovel_data.get("tipo_imovel", "Imóvel")
    cidade = imovel_data.get("cidade", "")
    bairro = imovel_data.get("bairro", "")
    area = imovel_data.get("area_privativa") or imovel_data.get("area_total", "")
    quartos = imovel_data.get("quartos", "")
    suites = imovel_data.get("suites", "")
    vagas = imovel_data.get("vagas", "")
    valor = imovel_data.get("valor", "")
    condominio = imovel_data.get("condominio_nome", "")
    observacoes = imovel_data.get("observacoes", "")

    details = []
    if tipo:
        details.append(f"Tipo: {tipo}")
    if bairro or cidade:
        details.append(f"Localização: {', '.join(filter(None, [bairro, cidade]))}")
    if area:
        details.append(f"Área: {area}m²")
    if quartos:
        details.append(f"Quartos: {quartos}")
    if suites:
        details.append(f"Suítes: {suites}")
    if vagas:
        details.append(f"Vagas: {vagas}")
    if valor:
        details.append(f"Valor: R$ {valor:,.2f}" if isinstance(valor, (int, float)) else f"Valor: R$ {valor}")
    if condominio:
        details.append(f"Condomínio: {condominio}")
    if observacoes:
        details.append(f"Observações: {observacoes}")

    prompt = f"""Você é um copywriter especializado em imóveis no Brasil.
Crie uma descrição atrativa e profissional para o seguinte imóvel, em português brasileiro.
A descrição deve ter entre 3 e 5 parágrafos, destacando os pontos fortes do imóvel.
Também sugira um título de anúncio curto (máximo 80 caracteres).

Dados do imóvel:
{chr(10).join(details)}

Responda no formato:
TÍTULO: [título sugerido]
DESCRIÇÃO:
[descrição completa]"""

    messages = [
        {"role": "system", "content": "Você é um copywriter imobiliário brasileiro especializado."},
        {"role": "user", "content": prompt},
    ]

    content = await chat_completion(messages, model=MODEL, temperature=0.7, max_tokens=1024)

    # Parse response
    titulo = ""
    descricao = content
    if "TÍTULO:" in content and "DESCRIÇÃO:" in content:
        parts = content.split("DESCRIÇÃO:", 1)
        titulo_part = parts[0].replace("TÍTULO:", "").strip()
        titulo = titulo_part[:80]
        descricao = parts[1].strip()

    return {
        "titulo_sugerido": titulo,
        "descricao": descricao,
    }


async def score_lead(cliente_data: dict) -> dict:
    """
    Generate a lead score (0-100) based on client profile data.
    Returns {score, justificativa, recomendacao}.
    """
    nome = cliente_data.get("nome", "")
    email = cliente_data.get("email", "")
    telefone = cliente_data.get("telefone", "")
    origem = cliente_data.get("origem", "")
    interesse = cliente_data.get("interesse", "")
    valor_estimado = cliente_data.get("valor_estimado", 0)
    etapa = cliente_data.get("etapa_atual", "")
    probabilidade = cliente_data.get("probabilidade", 0)
    observacoes = cliente_data.get("observacoes", "")

    prompt = f"""Você é um analista de vendas imobiliárias.
Analise o perfil do lead abaixo e atribua uma pontuação de 0 a 100 baseada na probabilidade de conversão.
Considere: completude dos dados, valor estimado, estágio no funil, probabilidade informada e interesse declarado.

Dados do lead:
- Nome: {nome}
- Email: {email or 'não informado'}
- Telefone: {telefone or 'não informado'}
- Origem: {origem or 'não informada'}
- Interesse: {interesse or 'não informado'}
- Valor estimado: R$ {valor_estimado or 0:,.2f}
- Etapa no funil: {etapa or 'não informada'}
- Probabilidade informada: {probabilidade or 0}%
- Observações: {observacoes or 'nenhuma'}

Responda EXATAMENTE no formato:
SCORE: [número de 0 a 100]
JUSTIFICATIVA: [2-3 frases explicando o score]
RECOMENDAÇÃO: [1 frase com próximo passo sugerido]"""

    messages = [
        {"role": "system", "content": "Você é um analista de vendas imobiliárias especializado em qualificação de leads."},
        {"role": "user", "content": prompt},
    ]

    content = await chat_completion(messages, model=MODEL, temperature=0.3, max_tokens=1024)

    # Parse response
    score = 50
    justificativa = ""
    recomendacao = ""

    for line in content.split("\n"):
        line = line.strip()
        if line.startswith("SCORE:"):
            try:
                score = int("".join(c for c in line.replace("SCORE:", "").strip() if c.isdigit())[:3])
                score = max(0, min(100, score))
            except ValueError:
                pass
        elif line.startswith("JUSTIFICATIVA:"):
            justificativa = line.replace("JUSTIFICATIVA:", "").strip()
        elif line.startswith("RECOMENDAÇÃO:") or line.startswith("RECOMENDACAO:"):
            recomendacao = line.split(":", 1)[1].strip()

    # If parsing failed, use the whole content as justificativa
    if not justificativa:
        justificativa = content

    return {
        "score": score,
        "justificativa": justificativa,
        "recomendacao": recomendacao,
    }


async def suggest_price(imovel_data: dict, comparables: list[dict]) -> dict:
    """
    Suggest pricing based on the property data and comparable properties.
    Returns {preco_sugerido, faixa_min, faixa_max, analise}.
    """
    tipo = imovel_data.get("tipo_imovel", "Imóvel")
    cidade = imovel_data.get("cidade", "")
    bairro = imovel_data.get("bairro", "")
    area = imovel_data.get("area_privativa") or imovel_data.get("area_total", "")
    quartos = imovel_data.get("quartos", "")
    vagas = imovel_data.get("vagas", "")

    comp_text = ""
    if comparables:
        lines = []
        for c in comparables[:10]:  # Limit to 10 comparables
            lines.append(
                f"  - {c.get('tipo_imovel', 'N/A')}, "
                f"{c.get('bairro', 'N/A')}/{c.get('cidade', 'N/A')}, "
                f"{c.get('area_privativa', 'N/A')}m², "
                f"{c.get('quartos', 'N/A')} quartos, "
                f"R$ {c.get('valor', 0):,.2f}" if isinstance(c.get('valor'), (int, float))
                else f"  - Valor: R$ {c.get('valor', 'N/A')}"
            )
        comp_text = "\n".join(lines)
    else:
        comp_text = "Nenhum imóvel comparável disponível."

    prompt = f"""Você é um avaliador imobiliário brasileiro experiente.
Com base nos dados do imóvel e nos comparáveis da região, sugira um preço justo de mercado.

Imóvel a avaliar:
- Tipo: {tipo}
- Localização: {bairro}, {cidade}
- Área: {area}m²
- Quartos: {quartos}
- Vagas: {vagas}

Imóveis comparáveis na região:
{comp_text}

Responda EXATAMENTE no formato:
PRECO_SUGERIDO: [valor em reais, apenas número]
FAIXA_MIN: [valor mínimo razoável]
FAIXA_MAX: [valor máximo razoável]
ANALISE: [2-3 frases justificando a sugestão]"""

    messages = [
        {"role": "system", "content": "Você é um avaliador imobiliário brasileiro com 20 anos de experiência."},
        {"role": "user", "content": prompt},
    ]

    content = await chat_completion(messages, model=MODEL, temperature=0.3, max_tokens=1024)

    # Parse response
    preco = 0.0
    faixa_min = 0.0
    faixa_max = 0.0
    analise = ""

    for line in content.split("\n"):
        line = line.strip()
        if line.startswith("PRECO_SUGERIDO:"):
            preco = _parse_money(line.replace("PRECO_SUGERIDO:", ""))
        elif line.startswith("FAIXA_MIN:"):
            faixa_min = _parse_money(line.replace("FAIXA_MIN:", ""))
        elif line.startswith("FAIXA_MAX:"):
            faixa_max = _parse_money(line.replace("FAIXA_MAX:", ""))
        elif line.startswith("ANALISE:") or line.startswith("ANÁLISE:"):
            analise = line.split(":", 1)[1].strip()

    if not analise:
        analise = content

    return {
        "preco_sugerido": preco,
        "faixa_min": faixa_min,
        "faixa_max": faixa_max,
        "analise": analise,
    }


def _parse_money(text: str) -> float:
    """Parse a monetary string to float. Handles Brazilian formats."""
    cleaned = text.strip().replace("R$", "").replace(".", "").replace(",", ".").strip()
    # Remove non-numeric except decimal point
    cleaned = "".join(c for c in cleaned if c.isdigit() or c == ".")
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


# ---------------------------------------------------------------------------
# E4 — Client follow-up draft (ai-expansion Phase 15, 2026-04-24)
# ---------------------------------------------------------------------------

PROMPT_VERSION_FOLLOW_UP = "erp-followup@v1"


async def draft_follow_up(
    *,
    cliente_nome: str,
    last_interaction_days: int,
    etapa_atual: Optional[str] = None,
    imovel_interesse: Optional[str] = None,
    observacoes: Optional[str] = None,
    org_id: Optional[str] = None,
) -> dict:
    """Draft a personalized re-engagement WhatsApp/email message for a stalled lead.

    Returns `{"channel": "whatsapp"|"email", "subject": str|None, "body": str}`.
    Returns a fallback `{channel: "email", subject: "", body: ""}` on LLM-not-configured
    so the UI can degrade to a manual compose flow.

    Args:
        cliente_nome: Lead's display name.
        last_interaction_days: Days since last activity (> 14 triggers this flow).
        etapa_atual: Current pipeline stage (e.g., "negociação", "qualificação").
        imovel_interesse: Property the lead was considering, if known.
        observacoes: Free-text notes the broker recorded.
        org_id: Used for org-scoped API key resolution + response cache.
    """
    system = (
        "Você é um corretor de imóveis brasileiro experiente, redigindo uma "
        "mensagem de reengajamento para um lead parado. Tom: próximo mas "
        "profissional, sem pressão, sem emojis. Sempre em português do Brasil. "
        "Produza UMA mensagem curta (máximo 120 palavras) pensada para WhatsApp. "
        "NÃO invente informações sobre o imóvel ou a negociação. Se algum dado "
        "não foi fornecido, redija de forma genérica sem inventar."
    )
    lines = [
        f"Nome do cliente: {cliente_nome}",
        f"Dias sem interação: {last_interaction_days}",
    ]
    if etapa_atual:
        lines.append(f"Estágio atual: {etapa_atual}")
    if imovel_interesse:
        lines.append(f"Imóvel de interesse: {imovel_interesse}")
    if observacoes:
        lines.append(f"Observações do corretor: {observacoes}")
    user_prompt = "\n".join(lines) + "\n\nResponda APENAS com o corpo da mensagem."

    try:
        body = await chat_completion(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_prompt},
            ],
            model=MODEL,
            temperature=0.0,
            max_tokens=400,
            cache=True,
            org_id=org_id,
        )
    except Exception:
        # Both LLMNotConfigured (per-provider) and RuntimeError (configure_llm
        # never called) bubble up here — swallow and let the UI fall back.
        logger.warning("erp.ai.draft_follow_up: LLM unavailable — returning empty draft")
        return {"channel": "whatsapp", "subject": None, "body": ""}

    return {
        "channel": "whatsapp",
        "subject": None,  # WhatsApp has no subject line; UI uses body only
        "body": body.strip(),
    }


# ---------------------------------------------------------------------------
# P1 Indicator services (ai-expansion Phase 6)
#
# Each function returns an AIOutput-shaped dict (kind/label/...). The router
# wraps it in `noctusai_lib.ai.AIOutput(...)` and persists via persist_output.
# Services stay DB-free so they're trivially unit-testable with FakeProvider.
# ---------------------------------------------------------------------------

PROMPT_VERSION_WHATSAPP_INTENT = "erp-whatsapp-intent@v1"
PROMPT_VERSION_CERTIDOES_SCORE = "erp-certidoes-score@v1"
PROMPT_VERSION_METAS_COACH = "erp-metas-coach@v1"
PROMPT_VERSION_PHOTO_COMPLIANCE = "erp-photo-compliance@v1"
PROMPT_VERSION_SEARCH_RELEVANCE = "erp-search-relevance@v1"


_WHATSAPP_INTENTS = {
    "interessado": "INTERESSADO",
    "agendamento": "AGENDAMENTO",
    "duvida": "DÚVIDA",
    "negociacao": "NEGOCIAÇÃO",
    "reclamacao": "RECLAMAÇÃO",
    "spam": "SPAM",
    "outros": "OUTROS",
}


def _empty_output(label: str = "indisponível") -> dict:
    """Fallback shape returned when LLM is not configured / unavailable."""
    return {
        "kind": "flag",
        "label": label,
        "chip": None,
        "explanation": "LLM indisponível — indicador não gerado.",
        "confidence": None,
        "score": None,
        "model_version": MODEL,
        "prompt_version": None,
    }


def _safe_float(text: str, default: float = 0.0) -> float:
    cleaned = "".join(c for c in text if c.isdigit() or c in ".-")
    try:
        return float(cleaned)
    except ValueError:
        return default


async def classify_whatsapp_intent(
    *,
    message_text: str,
    cliente_nome: Optional[str] = None,
    org_id: Optional[str] = None,
) -> dict:
    """E2 — classify a WhatsApp message into a sales intent.

    Returns an AIOutput-shaped dict with `kind="classification"`. The router
    wraps it in `AIOutput(ref_type="whatsapp_message", ref_id=..., **out)`
    and persists.
    """
    if not message_text or not message_text.strip():
        return _empty_output("vazio")

    system = (
        "Você é um analista de SDR imobiliário no Brasil. Classifique a "
        "intenção da mensagem do cliente em UMA das categorias:\n"
        "interessado | agendamento | duvida | negociacao | reclamacao | spam | outros\n"
        "Responda EXATAMENTE no formato:\n"
        "INTENT: <categoria>\n"
        "CONFIDENCE: <0 a 1>\n"
        "EXPLANATION: <até 12 palavras explicando>"
    )
    user_prompt = (
        f"Cliente: {cliente_nome or 'desconhecido'}\n"
        f"Mensagem: {message_text.strip()}"
    )
    try:
        content = await chat_completion(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_prompt},
            ],
            model=MODEL,
            temperature=0.0,
            max_tokens=120,
            cache=True,
            org_id=org_id,
        )
    except Exception:
        logger.warning("erp.ai.whatsapp_intent: LLM unavailable")
        return _empty_output()

    intent = "outros"
    confidence: Optional[float] = None
    explanation = ""
    for line in content.splitlines():
        s = line.strip()
        if s.upper().startswith("INTENT:"):
            raw = s.split(":", 1)[1].strip().lower()
            intent = next((k for k in _WHATSAPP_INTENTS if k in raw), "outros")
        elif s.upper().startswith("CONFIDENCE:"):
            confidence = _safe_float(s.split(":", 1)[1])
            if confidence is not None and (confidence < 0 or confidence > 1):
                confidence = max(0.0, min(1.0, confidence))
        elif s.upper().startswith("EXPLANATION:"):
            explanation = s.split(":", 1)[1].strip()

    return {
        "kind": "classification",
        "label": intent,
        "chip": _WHATSAPP_INTENTS[intent],
        "explanation": explanation or None,
        "confidence": confidence,
        "score": None,
        "model_version": MODEL,
        "prompt_version": PROMPT_VERSION_WHATSAPP_INTENT,
    }


async def score_certidoes(
    *,
    cliente_nome: str,
    certidoes: list[dict],
    org_id: Optional[str] = None,
) -> dict:
    """E6 — summarize a client's certidões status into a 0-100 health score.

    `certidoes` is a list of `{tipo, status, data_emissao?, observacoes?}`
    dicts pulled from the `certidoes_negativas` table.
    """
    if not certidoes:
        return {
            "kind": "score",
            "label": "sem certidões",
            "score": 0.0,
            "chip": "0/100",
            "explanation": "Nenhuma certidão registrada para o cliente.",
            "confidence": 1.0,
            "model_version": MODEL,
            "prompt_version": PROMPT_VERSION_CERTIDOES_SCORE,
        }

    cert_lines = []
    for c in certidoes[:20]:
        cert_lines.append(
            f"- {c.get('tipo', '?')}: {c.get('status', '?')}"
            + (f" (emitida {c['data_emissao']})" if c.get("data_emissao") else "")
            + (f" — {c['observacoes']}" if c.get("observacoes") else "")
        )

    system = (
        "Você é um analista de crédito imobiliário. Atribua uma nota de 0 "
        "a 100 para a saúde documental do cliente, considerando certidões "
        "vencidas, pendências e protestos. Responda no formato:\n"
        "SCORE: <0-100>\n"
        "EXPLANATION: <até 18 palavras>"
    )
    user_prompt = f"Cliente: {cliente_nome}\nCertidões:\n" + "\n".join(cert_lines)

    try:
        content = await chat_completion(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_prompt},
            ],
            model=MODEL,
            temperature=0.0,
            max_tokens=160,
            cache=True,
            org_id=org_id,
        )
    except Exception:
        logger.warning("erp.ai.score_certidoes: LLM unavailable")
        return _empty_output()

    score = 50.0
    explanation = ""
    for line in content.splitlines():
        s = line.strip()
        if s.upper().startswith("SCORE:"):
            score = max(0.0, min(100.0, _safe_float(s.split(":", 1)[1], 50.0)))
        elif s.upper().startswith("EXPLANATION:"):
            explanation = s.split(":", 1)[1].strip()

    return {
        "kind": "score",
        "label": f"saúde documental {int(score)}/100",
        "score": score,
        "chip": f"{int(score)}/100",
        "explanation": explanation or None,
        "confidence": None,
        "model_version": MODEL,
        "prompt_version": PROMPT_VERSION_CERTIDOES_SCORE,
    }


async def generate_metas_coach_tip(
    *,
    user_nome: str,
    progresso_percent: float,
    dias_restantes: int,
    eventos_recentes: Optional[list[str]] = None,
    org_id: Optional[str] = None,
) -> dict:
    """E7 — produce a short Portuguese coaching tip based on metas progress."""
    eventos_recentes = eventos_recentes or []
    eventos_text = "\n".join(f"- {e}" for e in eventos_recentes[:8]) or "- (sem eventos recentes)"

    system = (
        "Você é um coach de vendas brasileiro experiente. Dê UMA dica curta "
        "(máx. 22 palavras) para o corretor melhorar seu desempenho na meta "
        "atual. Tom motivador mas concreto, sem clichês, sem emojis. Responda "
        "no formato:\n"
        "TIP: <dica>\n"
        "CHIP: <2-3 palavras maiúsculas resumindo a dica>"
    )
    user_prompt = (
        f"Corretor: {user_nome}\n"
        f"Progresso atual: {progresso_percent:.0f}%\n"
        f"Dias restantes no período: {dias_restantes}\n"
        f"Eventos recentes:\n{eventos_text}"
    )

    try:
        content = await chat_completion(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_prompt},
            ],
            model=MODEL,
            temperature=0.4,
            max_tokens=140,
            cache=True,
            org_id=org_id,
        )
    except Exception:
        logger.warning("erp.ai.metas_coach_tip: LLM unavailable")
        return _empty_output()

    tip = ""
    chip = ""
    for line in content.splitlines():
        s = line.strip()
        if s.upper().startswith("TIP:"):
            tip = s.split(":", 1)[1].strip()
        elif s.upper().startswith("CHIP:"):
            chip = s.split(":", 1)[1].strip()
    if not tip:
        tip = content.strip().splitlines()[0] if content.strip() else "Continue firme — progresso constante."

    return {
        "kind": "narrative",
        "label": tip[:140],
        "explanation": tip,
        "chip": chip or "DICA",
        "confidence": None,
        "score": progresso_percent,
        "model_version": MODEL,
        "prompt_version": PROMPT_VERSION_METAS_COACH,
    }


async def assess_photo_compliance(
    *,
    imovel_descricao: Optional[str],
    fotos: list[dict],
    org_id: Optional[str] = None,
) -> dict:
    """E8 — assess listing-photo compliance from photo metadata.

    `fotos` is a list of `{filename?, url?, alt_text?, dimensions?, has_watermark?}`
    dicts. Returns a flag + score 0-100.
    """
    if not fotos:
        return {
            "kind": "flag",
            "label": "sem fotos",
            "score": 0.0,
            "chip": "SEM FOTOS",
            "explanation": "Anúncio sem fotos cadastradas.",
            "confidence": 1.0,
            "model_version": MODEL,
            "prompt_version": PROMPT_VERSION_PHOTO_COMPLIANCE,
        }

    foto_lines = []
    for f in fotos[:20]:
        parts = []
        if f.get("filename"):
            parts.append(f"arquivo={f['filename']}")
        if f.get("dimensions"):
            parts.append(f"dim={f['dimensions']}")
        if f.get("alt_text"):
            parts.append(f"alt='{f['alt_text']}'")
        if f.get("has_watermark"):
            parts.append("watermark=sim")
        foto_lines.append("- " + ", ".join(parts) if parts else "- (foto sem metadados)")

    system = (
        "Você é um auditor de qualidade de anúncios imobiliários. Analise "
        "a compliance das fotos do anúncio (qualidade, alt-text, "
        "watermarks indevidas, resolução). Responda no formato:\n"
        "FLAG: ok | revisar | reprovado\n"
        "SCORE: <0-100>\n"
        "EXPLANATION: <até 18 palavras>"
    )
    user_prompt = (
        f"Descrição: {imovel_descricao or '(sem descrição)'}\n"
        f"Fotos ({len(fotos)} total):\n" + "\n".join(foto_lines)
    )

    try:
        content = await chat_completion(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_prompt},
            ],
            model=MODEL,
            temperature=0.0,
            max_tokens=140,
            cache=True,
            org_id=org_id,
        )
    except Exception:
        logger.warning("erp.ai.photo_compliance: LLM unavailable")
        return _empty_output()

    flag = "revisar"
    score = 50.0
    explanation = ""
    for line in content.splitlines():
        s = line.strip()
        if s.upper().startswith("FLAG:"):
            raw = s.split(":", 1)[1].strip().lower()
            if "ok" in raw:
                flag = "ok"
            elif "reprovad" in raw:
                flag = "reprovado"
            else:
                flag = "revisar"
        elif s.upper().startswith("SCORE:"):
            score = max(0.0, min(100.0, _safe_float(s.split(":", 1)[1], 50.0)))
        elif s.upper().startswith("EXPLANATION:"):
            explanation = s.split(":", 1)[1].strip()

    chip_map = {"ok": "OK", "revisar": "REVISAR", "reprovado": "REPROVADO"}

    return {
        "kind": "flag",
        "label": flag,
        "score": score,
        "chip": chip_map[flag],
        "explanation": explanation or None,
        "confidence": None,
        "model_version": MODEL,
        "prompt_version": PROMPT_VERSION_PHOTO_COMPLIANCE,
    }


async def score_search_relevance(
    *,
    query: str,
    imovel_data: dict,
    org_id: Optional[str] = None,
) -> dict:
    """E10 — score the relevance of a property to a free-text search query."""
    if not query or not query.strip():
        return _empty_output("query vazia")

    system = (
        "Você é um buscador semântico imobiliário. Avalie quão relevante o "
        "imóvel é para a busca livre do usuário. Responda no formato:\n"
        "RELEVANCE: <0 a 1>\n"
        "EXPLANATION: <até 14 palavras>"
    )
    fields = [
        f"tipo={imovel_data.get('tipo_imovel', '?')}",
        f"bairro={imovel_data.get('bairro', '?')}",
        f"cidade={imovel_data.get('cidade', '?')}",
        f"area={imovel_data.get('area_privativa') or imovel_data.get('area_total', '?')}",
        f"quartos={imovel_data.get('quartos', '?')}",
        f"valor={imovel_data.get('valor', '?')}",
    ]
    if imovel_data.get("descricao"):
        fields.append(f"descricao='{imovel_data['descricao'][:200]}'")
    user_prompt = f"Busca: {query.strip()}\nImóvel: " + "; ".join(fields)

    try:
        content = await chat_completion(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_prompt},
            ],
            model=MODEL,
            temperature=0.0,
            max_tokens=100,
            cache=True,
            org_id=org_id,
        )
    except Exception:
        logger.warning("erp.ai.search_relevance: LLM unavailable")
        return _empty_output()

    relevance = 0.5
    explanation = ""
    for line in content.splitlines():
        s = line.strip()
        if s.upper().startswith("RELEVANCE:"):
            relevance = max(0.0, min(1.0, _safe_float(s.split(":", 1)[1], 0.5)))
        elif s.upper().startswith("EXPLANATION:"):
            explanation = s.split(":", 1)[1].strip()

    pct = int(round(relevance * 100))
    return {
        "kind": "score",
        "label": f"relevância {pct}%",
        "score": relevance,
        "chip": f"{pct}%",
        "explanation": explanation or None,
        "confidence": relevance,
        "model_version": MODEL,
        "prompt_version": PROMPT_VERSION_SEARCH_RELEVANCE,
    }
