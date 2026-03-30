"""
Embedding Service — Generate and store OpenAI embeddings for ativos.

Uses text-embedding-3-small (1536 dimensions) via httpx.
Gracefully degrades when OPENAI_API_KEY is not configured.
"""
import logging
from typing import Any, Optional

import httpx

from app.services.credential_resolver import resolve_credential

logger = logging.getLogger(__name__)

OPENAI_EMBEDDINGS_URL = "https://api.openai.com/v1/embeddings"
EMBEDDING_MODEL = "text-embedding-3-small"
TIMEOUT = 30.0


def _get_api_key(org_id: Optional[str] = None) -> str:
    """Resolve OpenAI API key via org_settings → platform_settings → env."""
    key = resolve_credential("openai_api_key", org_id)
    if not key:
        raise ValueError(
            "OpenAI API Key não configurada. "
            "Acesse Configurações > Chaves de API para configurar."
        )
    return key


def build_ativo_text(ativo: dict) -> str:
    """
    Build a rich text representation of an ativo for embedding generation.
    Handles all natureza types: imovel, permuta_imovel, permuta_automovel.
    """
    natureza = ativo.get("natureza", "")
    parts: list[str] = []

    if natureza == "imovel":
        if ativo.get("tipo_imovel"):
            parts.append(f"Tipo: {ativo['tipo_imovel']}")

        location = _build_location(ativo)
        if location:
            parts.append(f"Localização: {location}")

        if ativo.get("area_total") or ativo.get("area_privativa"):
            area = ativo.get("area_privativa") or ativo.get("area_total")
            parts.append(f"Área: {area}m²")
        if ativo.get("quartos"):
            parts.append(f"Quartos: {ativo['quartos']}")
        if ativo.get("suites"):
            parts.append(f"Suítes: {ativo['suites']}")
        if ativo.get("vagas"):
            parts.append(f"Vagas: {ativo['vagas']}")
        if ativo.get("valor"):
            parts.append(f"Valor: R$ {ativo['valor']}")
        if ativo.get("titulo_anuncio"):
            parts.append(f"Título: {ativo['titulo_anuncio']}")
        if ativo.get("descricao_seo"):
            parts.append(f"Descrição: {ativo['descricao_seo']}")
        if ativo.get("pontos_de_interesse"):
            poi = ativo["pontos_de_interesse"]
            if isinstance(poi, list):
                parts.append(f"Pontos de interesse: {', '.join(str(p) for p in poi)}")
            else:
                parts.append(f"Pontos de interesse: {poi}")
        if ativo.get("condominio_nome"):
            parts.append(f"Condomínio: {ativo['condominio_nome']}")

    elif natureza == "permuta_imovel":
        if ativo.get("tipo_imovel"):
            parts.append(f"Tipo desejado: {ativo['tipo_imovel']}")

        location = _build_location(ativo)
        if location:
            parts.append(f"Localização preferida: {location}")

        if ativo.get("faixa_preco_min") or ativo.get("faixa_preco_max"):
            fmin = ativo.get("faixa_preco_min", "")
            fmax = ativo.get("faixa_preco_max", "")
            parts.append(f"Faixa de preço: R$ {fmin} - R$ {fmax}")
        if ativo.get("quartos_min") or ativo.get("quartos"):
            q = ativo.get("quartos_min") or ativo.get("quartos")
            parts.append(f"Quartos mínimos: {q}")
        if ativo.get("vagas_min") or ativo.get("vagas"):
            v = ativo.get("vagas_min") or ativo.get("vagas")
            parts.append(f"Vagas mínimas: {v}")
        if ativo.get("metragem_min") or ativo.get("metragem_max"):
            mmin = ativo.get("metragem_min", "")
            mmax = ativo.get("metragem_max", "")
            parts.append(f"Metragem: {mmin} - {mmax}m²")

    elif natureza == "permuta_automovel":
        if ativo.get("tipo_veiculo"):
            parts.append(f"Tipo veículo: {ativo['tipo_veiculo']}")
        if ativo.get("marca"):
            parts.append(f"Marca: {ativo['marca']}")
        if ativo.get("modelo"):
            parts.append(f"Modelo: {ativo['modelo']}")
        if ativo.get("motor"):
            parts.append(f"Motor: {ativo['motor']}")
        if ativo.get("ano"):
            parts.append(f"Ano: {ativo['ano']}")
        if ativo.get("km"):
            parts.append(f"Km: {ativo['km']}")
        if ativo.get("valor"):
            parts.append(f"Valor: R$ {ativo['valor']}")

    # Common field for all naturezas
    if ativo.get("interesses_descricao"):
        parts.append(f"Interesses: {ativo['interesses_descricao']}")

    return ". ".join(parts) if parts else ""


def build_interesses_text(ativo: dict) -> str:
    """
    Build a text representation of what an ativo WANTS in exchange.

    For imóveis: uses the `interesses` JSONB array (e.g., wants apartamento in SP, R$300-600k).
    For permutas: uses the `interesses` JSONB array (e.g., wants casa in Campinas, R$500-900k).

    This is the counterpart to build_ativo_text() which describes what an ativo IS.
    Matching compares profile↔interest embeddings, not profile↔profile.
    """
    interesses = ativo.get("interesses") or []
    if not interesses:
        # Fallback: use interesses_descricao free-text if available
        desc = ativo.get("interesses_descricao") or ""
        return desc.strip()

    parts: list[str] = []
    for interesse in interesses:
        sub: list[str] = []
        tipo = interesse.get("tipo", "")

        if tipo == "imovel":
            sub.append("Busca imóvel")
            if interesse.get("tipo_imovel"):
                sub.append(f"tipo: {interesse['tipo_imovel']}")
            if interesse.get("cidade"):
                sub.append(f"cidade: {interesse['cidade']}")
            if interesse.get("estado"):
                sub.append(f"estado: {interesse['estado']}")
            if interesse.get("bairro"):
                sub.append(f"bairro: {interesse['bairro']}")
            valor_min = interesse.get("valor_min")
            valor_max = interesse.get("valor_max")
            if valor_min or valor_max:
                sub.append(f"faixa: R$ {valor_min or '?'} - R$ {valor_max or '?'}")
            if interesse.get("quartos_min"):
                sub.append(f"quartos mínimos: {interesse['quartos_min']}")
            if interesse.get("area_min"):
                sub.append(f"área mínima: {interesse['area_min']}m²")

        elif tipo == "automovel":
            sub.append("Busca automóvel")
            if interesse.get("marca"):
                sub.append(f"marca: {interesse['marca']}")
            if interesse.get("modelo"):
                sub.append(f"modelo: {interesse['modelo']}")
            valor_min = interesse.get("valor_min")
            valor_max = interesse.get("valor_max")
            if valor_min or valor_max:
                sub.append(f"faixa: R$ {valor_min or '?'} - R$ {valor_max or '?'}")

        if sub:
            parts.append(", ".join(sub))

    return ". ".join(parts) if parts else ""


def _build_location(ativo: dict) -> str:
    """Build location string from bairro, cidade, estado, zona."""
    location_parts = filter(None, [
        ativo.get("bairro"),
        ativo.get("cidade"),
        ativo.get("estado"),
        ativo.get("zona"),
    ])
    return ", ".join(location_parts)


async def generate_embedding(text: str, org_id: Optional[str] = None) -> list[float]:
    """
    Call OpenAI text-embedding-3-small to generate a 1536-dim embedding.
    Raises ValueError if API key is not configured or API call fails.
    """
    api_key = _get_api_key(org_id)

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.post(
            OPENAI_EMBEDDINGS_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": EMBEDDING_MODEL,
                "input": text,
            },
        )

        if response.status_code != 200:
            logger.error(f"OpenAI Embeddings API error: {response.status_code} — {response.text}")
            raise ValueError(f"Erro na API OpenAI Embeddings: {response.status_code}")

        data = response.json()
        return data["data"][0]["embedding"]


async def embed_ativo(ativo: dict, db) -> bool:
    """
    Generate embeddings for an ativo and store them in the database.

    Generates two embeddings:
      - `embedding`: the ativo's PROFILE (what it IS)
      - `embedding_interesses`: what the ativo WANTS in exchange

    Matching compares profile↔interest across pairs (not profile↔profile).
    Returns True if at least the profile embedding was generated.
    """
    text = build_ativo_text(ativo)
    if not text:
        logger.warning(f"Ativo {ativo.get('id')} has no text to embed")
        return False

    update_data = {}

    # Profile embedding (what the ativo IS)
    embedding = await generate_embedding(text)
    update_data["embedding"] = embedding

    # Interest embedding (what the ativo WANTS)
    interesses_text = build_interesses_text(ativo)
    if interesses_text:
        embedding_interesses = await generate_embedding(interesses_text)
        update_data["embedding_interesses"] = embedding_interesses
        logger.info(f"Embedded ativo {ativo['id']} profile + interesses ({len(embedding)} dims)")
    else:
        logger.info(f"Embedded ativo {ativo['id']} profile only ({len(embedding)} dims, no interesses)")

    db.table("ativos").update(update_data).eq("id", ativo["id"]).execute()
    return True


async def embed_ativos_batch(ativo_ids: list[str], db) -> dict:
    """
    Batch embed multiple ativos. Returns summary dict.
    """
    total = len(ativo_ids)
    embedded = 0
    errors = 0

    # Batch fetch all ativos in one query
    res = db.table("ativos").select("*").in_("id", ativo_ids).execute()
    ativos_by_id = {a["id"]: a for a in (res.data or [])}

    for ativo_id in ativo_ids:
        ativo = ativos_by_id.get(ativo_id)
        if not ativo:
            errors += 1
            continue
        try:
            success = await embed_ativo(ativo, db)
            if success:
                embedded += 1
            else:
                errors += 1
        except Exception as e:
            logger.error(f"Error embedding ativo {ativo_id}: {e}")
            errors += 1

    return {"total": total, "embedded": embedded, "errors": errors}
