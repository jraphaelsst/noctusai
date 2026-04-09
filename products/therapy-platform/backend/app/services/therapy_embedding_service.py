"""
Therapy Embedding Service — Generate OpenAI embeddings for therapist and patient profiles.

Uses text-embedding-3-small (1536 dimensions) via httpx.
Ported from the ERP embedding service, adapted for therapy domain.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from app.dependencies import first_or_none

logger = logging.getLogger(__name__)

OPENAI_EMBEDDINGS_URL = "https://api.openai.com/v1/embeddings"
EMBEDDING_MODEL = "text-embedding-3-small"
TIMEOUT = 30.0


# ---------------------------------------------------------------------------
# Text builders
# ---------------------------------------------------------------------------

def build_therapist_text(profile: dict) -> str:
    """Combine therapist profile fields into embeddable text.

    Fields: specialties, approaches, bio, rating, session duration, price range.
    """
    parts: list[str] = []

    specialties = profile.get("specialties") or []
    if specialties:
        parts.append(f"Especialidades: {', '.join(specialties)}")

    approaches = profile.get("approaches") or []
    if approaches:
        parts.append(f"Abordagens: {', '.join(approaches)}")

    if profile.get("bio"):
        parts.append(f"Bio: {profile['bio']}")

    if profile.get("avg_rating"):
        parts.append(f"Avaliação média: {profile['avg_rating']}")

    if profile.get("session_duration_minutes"):
        parts.append(f"Duração da sessão: {profile['session_duration_minutes']} min")

    if profile.get("default_session_price"):
        parts.append(f"Preço da sessão: R$ {profile['default_session_price']}")

    if profile.get("accepts_convenio"):
        parts.append("Aceita convênio")

    if profile.get("online_available"):
        parts.append("Atendimento online disponível")

    if profile.get("in_person_available"):
        parts.append("Atendimento presencial disponível")

    return ". ".join(parts) if parts else ""


def build_patient_text(profile: dict) -> str:
    """Combine patient profile/preferences into embeddable text.

    Fields: therapy_needs, preferred_approaches, preferred_specialties, budget.
    """
    parts: list[str] = []

    therapy_needs = profile.get("therapy_needs") or profile.get("queixa_principal")
    if therapy_needs:
        parts.append(f"Necessidades: {therapy_needs}")

    preferred_approaches = profile.get("preferred_approaches") or []
    if preferred_approaches:
        parts.append(f"Abordagens preferidas: {', '.join(preferred_approaches)}")

    preferred_specialties = profile.get("preferred_specialties") or []
    if preferred_specialties:
        parts.append(f"Especialidades desejadas: {', '.join(preferred_specialties)}")

    if profile.get("max_budget"):
        parts.append(f"Orçamento máximo: R$ {profile['max_budget']}")

    if profile.get("prefers_online"):
        parts.append("Prefere atendimento online")
    elif profile.get("prefers_in_person"):
        parts.append("Prefere atendimento presencial")

    if profile.get("observacoes"):
        parts.append(f"Observações: {profile['observacoes']}")

    return ". ".join(parts) if parts else ""


# ---------------------------------------------------------------------------
# Embedding generation
# ---------------------------------------------------------------------------

async def generate_embedding(text: str, api_key: str) -> list[float]:
    """Call OpenAI text-embedding-3-small to generate a 1536-dim embedding.

    Args:
        text: Input text to embed.
        api_key: OpenAI API key.

    Raises:
        ValueError: If the API call fails.
    """
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
            logger.error("OpenAI Embeddings API error: %d — %s", response.status_code, response.text)
            raise ValueError(f"Erro na API OpenAI Embeddings: {response.status_code}")

        data = response.json()
        return data["data"][0]["embedding"]


# ---------------------------------------------------------------------------
# Profile embedding workflows
# ---------------------------------------------------------------------------

async def embed_therapist(
    therapist_id: str,
    db: Any,
    api_key: Optional[str] = None,
) -> bool:
    """Build text from therapist profile, generate embedding, store in DB.

    Returns True if embedding was generated successfully.
    """
    if not api_key:
        raise ValueError("OpenAI API Key não configurada")

    result = (
        db.table("therapist_profiles")
        .select("*")
        .eq("user_id", therapist_id)
        .execute()
    )
    profile = first_or_none(result)
    if not profile:
        logger.warning("Therapist profile not found for %s", therapist_id)
        return False

    text = build_therapist_text(profile)
    if not text:
        logger.warning("Therapist %s has no text to embed", therapist_id)
        return False

    embedding = await generate_embedding(text, api_key)
    db.table("therapist_profiles").update({
        "embedding": embedding,
    }).eq("user_id", therapist_id).execute()

    logger.info("Embedded therapist %s (%d dims)", therapist_id, len(embedding))
    return True


async def embed_patient(
    patient_id: str,
    db: Any,
    api_key: Optional[str] = None,
) -> bool:
    """Build text from patient profile/preferences, generate embedding, store in DB.

    Returns True if embedding was generated successfully.
    """
    if not api_key:
        raise ValueError("OpenAI API Key não configurada")

    result = (
        db.table("patient_profiles")
        .select("*")
        .eq("user_id", patient_id)
        .execute()
    )
    profile = first_or_none(result)
    if not profile:
        logger.warning("Patient profile not found for %s", patient_id)
        return False

    text = build_patient_text(profile)
    if not text:
        logger.warning("Patient %s has no text to embed", patient_id)
        return False

    embedding = await generate_embedding(text, api_key)
    db.table("patient_profiles").update({
        "embedding": embedding,
    }).eq("user_id", patient_id).execute()

    logger.info("Embedded patient %s (%d dims)", patient_id, len(embedding))
    return True
