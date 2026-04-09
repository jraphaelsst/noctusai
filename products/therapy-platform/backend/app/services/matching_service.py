"""
Matching Service — Therapist-patient matching with composite scoring.

Composite score: embedding similarity (40%) + rule-based (60%).
Rule-based components: specialty overlap, approach compatibility,
price range, availability overlap.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.dependencies import first_or_none

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Cosine similarity
# ---------------------------------------------------------------------------

def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two embedding vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# ---------------------------------------------------------------------------
# Rule-based scoring components (max 100 pts each, normalized to 0-1)
# ---------------------------------------------------------------------------

def _score_specialty_overlap(patient: dict, therapist: dict) -> float:
    """Score based on overlap between patient's desired specialties and therapist's specialties.

    Returns 0.0–1.0.
    """
    patient_specialties = set(s.lower() for s in (patient.get("preferred_specialties") or []))
    therapist_specialties = set(s.lower() for s in (therapist.get("specialties") or []))

    if not patient_specialties or not therapist_specialties:
        return 0.5  # No preference = neutral

    overlap = patient_specialties & therapist_specialties
    if not overlap:
        return 0.0
    return len(overlap) / len(patient_specialties)


def _score_approach_compatibility(patient: dict, therapist: dict) -> float:
    """Score based on overlap between preferred and offered approaches.

    Returns 0.0–1.0.
    """
    patient_approaches = set(a.lower() for a in (patient.get("preferred_approaches") or []))
    therapist_approaches = set(a.lower() for a in (therapist.get("approaches") or []))

    if not patient_approaches or not therapist_approaches:
        return 0.5  # No preference = neutral

    overlap = patient_approaches & therapist_approaches
    if not overlap:
        return 0.0
    return len(overlap) / len(patient_approaches)


def _score_price_range(patient: dict, therapist: dict) -> float:
    """Score based on whether therapist price is within patient budget.

    Returns 0.0–1.0.
    """
    max_budget = float(patient.get("max_budget") or 0)
    session_price = float(therapist.get("default_session_price") or 0)

    if max_budget <= 0 or session_price <= 0:
        return 0.5  # Unknown = neutral

    if session_price <= max_budget:
        return 1.0
    # Graceful degradation: up to 20% over budget still scores partially
    overage_pct = (session_price - max_budget) / max_budget
    if overage_pct <= 0.2:
        return 0.5
    return 0.0


def _score_availability_overlap(patient: dict, therapist: dict) -> float:
    """Score based on overlap between patient preferred times and therapist availability.

    Returns 0.0–1.0. Simplified: checks if preferred_days overlap with
    therapist's availability days.
    """
    patient_days = set(patient.get("preferred_days") or [])
    therapist_days = set(therapist.get("availability_days") or [])

    if not patient_days or not therapist_days:
        return 0.5  # No preference = neutral

    overlap = patient_days & therapist_days
    if not overlap:
        return 0.0
    return len(overlap) / len(patient_days)


# ---------------------------------------------------------------------------
# Composite scoring
# ---------------------------------------------------------------------------

def _compute_composite_score(
    embedding_similarity: float,
    specialty_score: float,
    approach_score: float,
    price_score: float,
    availability_score: float,
) -> float:
    """Compute final composite score.

    Weights:
    - Embedding similarity: 40%
    - Specialty overlap: 20%
    - Approach compatibility: 15%
    - Price range: 15%
    - Availability overlap: 10%
    """
    composite = (
        0.40 * embedding_similarity
        + 0.20 * specialty_score
        + 0.15 * approach_score
        + 0.15 * price_score
        + 0.10 * availability_score
    )
    return round(min(max(composite, 0.0), 1.0), 4)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def find_matches(
    patient_id: str,
    db: Any,
    threshold: float = 0.5,
    limit: int = 10,
) -> List[Dict]:
    """Find matching therapists for a patient.

    Composite score: embedding similarity (40%) + rule-based (60%).
    Returns top matches above threshold, sorted by score descending.
    """
    # Fetch patient profile
    patient_result = (
        db.table("patient_profiles")
        .select("*")
        .eq("user_id", patient_id)
        .execute()
    )
    patient = first_or_none(patient_result)
    if not patient:
        logger.warning("Patient profile not found for %s", patient_id)
        return []

    patient_embedding = patient.get("embedding")

    # Fetch all active therapist profiles
    therapists_result = (
        db.table("therapist_profiles")
        .select("*")
        .eq("is_active", True)
        .execute()
    )
    therapists = therapists_result.data or []

    if not therapists:
        return []

    matches: List[Dict] = []

    for therapist in therapists:
        # Embedding similarity
        therapist_embedding = therapist.get("embedding")
        if patient_embedding and therapist_embedding:
            embedding_sim = _cosine_similarity(patient_embedding, therapist_embedding)
        else:
            embedding_sim = 0.0

        # Rule-based scores
        specialty = _score_specialty_overlap(patient, therapist)
        approach = _score_approach_compatibility(patient, therapist)
        price = _score_price_range(patient, therapist)
        availability = _score_availability_overlap(patient, therapist)

        composite = _compute_composite_score(
            embedding_sim, specialty, approach, price, availability,
        )

        if composite >= threshold:
            matches.append({
                "therapist_id": therapist["user_id"],
                "score": composite,
                "breakdown": {
                    "embedding_similarity": round(embedding_sim, 4),
                    "specialty_overlap": round(specialty, 4),
                    "approach_compatibility": round(approach, 4),
                    "price_range": round(price, 4),
                    "availability_overlap": round(availability, 4),
                },
                "therapist_nome": therapist.get("nome"),
                "therapist_specialties": therapist.get("specialties"),
                "therapist_approaches": therapist.get("approaches"),
                "therapist_price": therapist.get("default_session_price"),
            })

    matches.sort(key=lambda m: m["score"], reverse=True)
    return matches[:limit]


async def get_match_details(
    therapist_id: str,
    patient_id: str,
    db: Any,
) -> Optional[Dict]:
    """Get detailed match breakdown between a specific therapist and patient."""
    # Fetch both profiles
    patient_result = (
        db.table("patient_profiles")
        .select("*")
        .eq("user_id", patient_id)
        .execute()
    )
    patient = first_or_none(patient_result)
    if not patient:
        return None

    therapist_result = (
        db.table("therapist_profiles")
        .select("*")
        .eq("user_id", therapist_id)
        .execute()
    )
    therapist = first_or_none(therapist_result)
    if not therapist:
        return None

    # Compute all scores
    patient_embedding = patient.get("embedding")
    therapist_embedding = therapist.get("embedding")
    if patient_embedding and therapist_embedding:
        embedding_sim = _cosine_similarity(patient_embedding, therapist_embedding)
    else:
        embedding_sim = 0.0

    specialty = _score_specialty_overlap(patient, therapist)
    approach = _score_approach_compatibility(patient, therapist)
    price = _score_price_range(patient, therapist)
    availability = _score_availability_overlap(patient, therapist)

    composite = _compute_composite_score(
        embedding_sim, specialty, approach, price, availability,
    )

    # Build justificativa
    justificativa_parts = []
    if specialty >= 0.7:
        justificativa_parts.append("Especialidades muito compatíveis")
    elif specialty >= 0.4:
        justificativa_parts.append("Especialidades parcialmente compatíveis")
    if approach >= 0.7:
        justificativa_parts.append("Abordagens alinhadas")
    if price >= 0.8:
        justificativa_parts.append("Preço dentro do orçamento")
    elif price < 0.3:
        justificativa_parts.append("Preço acima do orçamento")
    if availability >= 0.7:
        justificativa_parts.append("Boa disponibilidade de horários")

    return {
        "therapist_id": therapist_id,
        "patient_id": patient_id,
        "score": composite,
        "justificativa": ". ".join(justificativa_parts) if justificativa_parts else "Match parcial",
        "breakdown": {
            "embedding_similarity": round(embedding_sim, 4),
            "specialty_overlap": round(specialty, 4),
            "approach_compatibility": round(approach, 4),
            "price_range": round(price, 4),
            "availability_overlap": round(availability, 4),
        },
        "patient_preferences": {
            "preferred_specialties": patient.get("preferred_specialties"),
            "preferred_approaches": patient.get("preferred_approaches"),
            "max_budget": patient.get("max_budget"),
        },
        "therapist_profile": {
            "specialties": therapist.get("specialties"),
            "approaches": therapist.get("approaches"),
            "default_session_price": therapist.get("default_session_price"),
            "avg_rating": therapist.get("avg_rating"),
        },
    }
