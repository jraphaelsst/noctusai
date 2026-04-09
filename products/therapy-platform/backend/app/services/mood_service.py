"""
Mood Service — Patient mood/emotion tracking and analytics.
"""
from __future__ import annotations

import logging
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException

from app.dependencies import first_or_none
from app.responses import calculate_pagination

logger = logging.getLogger(__name__)


async def create_entry(
    patient_id: str,
    data: Dict,
    db: Any,
) -> Dict:
    """Create a mood entry for a patient."""
    record = {
        "patient_id": patient_id,
        "rating": data["rating"],
        "emocoes": data.get("emocoes"),
        "nota": data.get("nota"),
    }
    result = db.table("mood_entries").insert(record).execute()
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=500, detail="Erro ao registrar humor")
    logger.info("Mood entry created for patient %s (rating=%d)", patient_id, data["rating"])
    return row


async def list_entries(
    patient_id: str,
    db: Any,
    data_inicio: Optional[str] = None,
    data_fim: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> Tuple[List[Dict], int]:
    """List mood entries for a patient with optional date range filter."""
    page, page_size, offset = calculate_pagination(page, page_size)

    query = db.table("mood_entries").select("*", count="exact").eq("patient_id", patient_id)

    if data_inicio:
        query = query.gte("created_at", data_inicio)
    if data_fim:
        query = query.lte("created_at", data_fim)

    result = query.order("created_at", desc=True).range(offset, offset + page_size - 1).execute()
    return result.data or [], result.count or 0


async def get_analytics(
    patient_id: str,
    db: Any,
    days: int = 30,
) -> Dict:
    """Compute mood analytics for a patient over the last N days.

    Returns:
        - avg_rating: average mood rating
        - emotion_frequency: dict of emotion -> count
        - trend: 'improving', 'declining', or 'stable'
        - total_entries: number of entries in the period
    """
    from datetime import datetime, timedelta, timezone

    sp_tz = timezone(timedelta(hours=-3))
    cutoff = (datetime.now(sp_tz) - timedelta(days=days)).isoformat()

    result = (
        db.table("mood_entries")
        .select("rating, emocoes, created_at")
        .eq("patient_id", patient_id)
        .gte("created_at", cutoff)
        .order("created_at")
        .execute()
    )
    entries = result.data or []

    if not entries:
        return {
            "avg_rating": None,
            "emotion_frequency": {},
            "trend": "stable",
            "total_entries": 0,
        }

    ratings = [e["rating"] for e in entries]
    avg_rating = round(sum(ratings) / len(ratings), 2)

    # Emotion frequency
    emotion_counter: Counter = Counter()
    for entry in entries:
        emocoes = entry.get("emocoes") or []
        for emocao in emocoes:
            emotion_counter[emocao] += 1

    # Trend: compare first half avg vs second half avg
    mid = len(ratings) // 2
    if mid > 0:
        first_half_avg = sum(ratings[:mid]) / mid
        second_half_avg = sum(ratings[mid:]) / len(ratings[mid:])
        diff = second_half_avg - first_half_avg
        if diff > 0.5:
            trend = "improving"
        elif diff < -0.5:
            trend = "declining"
        else:
            trend = "stable"
    else:
        trend = "stable"

    return {
        "avg_rating": avg_rating,
        "emotion_frequency": dict(emotion_counter),
        "trend": trend,
        "total_entries": len(entries),
    }
