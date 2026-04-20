"""
Therapy Embedding Service — Generate embeddings for therapist and patient
profiles via the shared `noctusai_lib.llm` client.

Credential resolution and provider dispatch are inherited from the seed.
The `api_key` parameter on `generate_embedding` is kept for backward
compatibility with existing callers but now unused — the shared lib routes
through the configured `key_provider`.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from app.dependencies import first_or_none

from noctusai_lib.llm import generate_embedding as _lib_generate_embedding

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "text-embedding-3-small"


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

async def generate_embedding(
    text: str,
    api_key: Optional[str] = None,
    clinic_id: Optional[str] = None,
) -> list[float]:
    """Generate a 1536-dim embedding for therapist/patient profile text.

    The `api_key` param is kept for backward compatibility with existing
    callers but ignored — the shared lib resolves the key via the configured
    `key_provider`. `clinic_id` is threaded through as `org_id` so Tier 1
    (clinic-scoped) keys resolve correctly (see `task.md` §7, resolved in
    Phase 16).
    """
    return await _lib_generate_embedding(text, model=EMBEDDING_MODEL, org_id=clinic_id)


# ---------------------------------------------------------------------------
# Profile embedding workflows
# ---------------------------------------------------------------------------

async def embed_therapist(
    therapist_id: str,
    db: Any,
    api_key: Optional[str] = None,
    clinic_id: Optional[str] = None,
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

    embedding = await generate_embedding(text, api_key, clinic_id=clinic_id)
    db.table("therapist_profiles").update({
        "embedding": embedding,
    }).eq("user_id", therapist_id).execute()

    logger.info("Embedded therapist %s (%d dims)", therapist_id, len(embedding))
    return True


async def embed_patient(
    patient_id: str,
    db: Any,
    api_key: Optional[str] = None,
    clinic_id: Optional[str] = None,
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

    embedding = await generate_embedding(text, api_key, clinic_id=clinic_id)
    db.table("patient_profiles").update({
        "embedding": embedding,
    }).eq("user_id", patient_id).execute()

    logger.info("Embedded patient %s (%d dims)", patient_id, len(embedding))
    return True
