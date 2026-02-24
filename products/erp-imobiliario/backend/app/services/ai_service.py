"""
AI Service — OpenAI-powered features for property descriptions, lead scoring, and pricing.

Uses httpx to call the OpenAI API directly (no openai package dependency).
Gracefully falls back with descriptive errors if the API key is not configured.
"""
import logging
from typing import Any, Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
MODEL = "gpt-4o-mini"
TIMEOUT = 30.0


def _get_api_key() -> str:
    """Get OpenAI API key or raise."""
    key = settings.openai_api_key
    if not key:
        raise ValueError(
            "Chave da API OpenAI não configurada. "
            "Defina OPENAI_API_KEY no arquivo .env."
        )
    return key


async def _chat_completion(messages: list[dict], temperature: float = 0.7) -> str:
    """Call OpenAI Chat Completions API and return the assistant message content."""
    api_key = _get_api_key()

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.post(
            OPENAI_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": MODEL,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": 1024,
            },
        )

        if response.status_code != 200:
            logger.error(f"OpenAI API error: {response.status_code} — {response.text}")
            raise ValueError(f"Erro na API OpenAI: {response.status_code}")

        data = response.json()
        return data["choices"][0]["message"]["content"].strip()


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

    content = await _chat_completion(messages, temperature=0.7)

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

    content = await _chat_completion(messages, temperature=0.3)

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

    content = await _chat_completion(messages, temperature=0.3)

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
