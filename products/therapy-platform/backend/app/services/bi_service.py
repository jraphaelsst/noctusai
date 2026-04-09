"""
BI Service — Business intelligence and analytics for therapists.

Provides dashboard summaries, session/revenue time series, and cancellation rates.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

SP_TZ = timezone(timedelta(hours=-3))


async def get_dashboard_resumo(
    therapist_id: str,
    db: Any,
) -> Dict:
    """Dashboard summary: total sessions, revenue, active patients, avg rating."""
    # Total completed sessions
    sessions_result = (
        db.table("appointments")
        .select("id", count="exact")
        .eq("therapist_id", therapist_id)
        .eq("status", "completed")
        .execute()
    )
    total_sessions = sessions_result.count or 0

    # Total revenue from completed appointments
    revenue_result = (
        db.table("appointments")
        .select("session_price_applied")
        .eq("therapist_id", therapist_id)
        .eq("status", "completed")
        .execute()
    )
    total_revenue = sum(
        float(a.get("session_price_applied") or 0)
        for a in (revenue_result.data or [])
    )

    # Active patients (distinct patients with future or recent appointments)
    cutoff = (datetime.now(SP_TZ) - timedelta(days=90)).isoformat()
    patients_result = (
        db.table("appointments")
        .select("patient_id")
        .eq("therapist_id", therapist_id)
        .gte("scheduled_start", cutoff)
        .not_.in_("status", ["cancelled", "late_cancelled"])
        .execute()
    )
    active_patients = len({a["patient_id"] for a in (patients_result.data or [])})

    # Average rating
    reviews_result = (
        db.table("reviews")
        .select("rating")
        .eq("therapist_id", therapist_id)
        .execute()
    )
    ratings = [r["rating"] for r in (reviews_result.data or []) if r.get("rating")]
    avg_rating = round(sum(ratings) / len(ratings), 2) if ratings else None

    return {
        "total_sessions": total_sessions,
        "total_revenue": round(total_revenue, 2),
        "active_patients": active_patients,
        "avg_rating": avg_rating,
    }


async def get_sessoes_por_periodo(
    therapist_id: str,
    db: Any,
    inicio: Optional[str] = None,
    fim: Optional[str] = None,
) -> List[Dict]:
    """Session counts grouped by week.

    Returns list of {period, count} dicts.
    """
    if not inicio:
        inicio = (datetime.now(SP_TZ) - timedelta(days=90)).isoformat()
    if not fim:
        fim = datetime.now(SP_TZ).isoformat()

    result = (
        db.table("appointments")
        .select("scheduled_start, status")
        .eq("therapist_id", therapist_id)
        .eq("status", "completed")
        .gte("scheduled_start", inicio)
        .lte("scheduled_start", fim)
        .order("scheduled_start")
        .execute()
    )

    weekly: Dict[str, int] = defaultdict(int)
    for appt in (result.data or []):
        try:
            dt = datetime.fromisoformat(appt["scheduled_start"].replace("Z", "+00:00"))
            # ISO week start (Monday)
            week_start = dt - timedelta(days=dt.weekday())
            week_key = week_start.strftime("%Y-%m-%d")
            weekly[week_key] += 1
        except (ValueError, TypeError):
            continue

    return [{"period": k, "count": v} for k, v in sorted(weekly.items())]


async def get_receita_por_periodo(
    therapist_id: str,
    db: Any,
    inicio: Optional[str] = None,
    fim: Optional[str] = None,
) -> List[Dict]:
    """Revenue grouped by month.

    Returns list of {period, total} dicts.
    """
    if not inicio:
        inicio = (datetime.now(SP_TZ) - timedelta(days=365)).isoformat()
    if not fim:
        fim = datetime.now(SP_TZ).isoformat()

    result = (
        db.table("appointments")
        .select("scheduled_start, session_price_applied")
        .eq("therapist_id", therapist_id)
        .eq("status", "completed")
        .gte("scheduled_start", inicio)
        .lte("scheduled_start", fim)
        .order("scheduled_start")
        .execute()
    )

    monthly: Dict[str, float] = defaultdict(float)
    for appt in (result.data or []):
        try:
            dt = datetime.fromisoformat(appt["scheduled_start"].replace("Z", "+00:00"))
            month_key = dt.strftime("%Y-%m")
            price = float(appt.get("session_price_applied") or 0)
            monthly[month_key] += price
        except (ValueError, TypeError):
            continue

    return [{"period": k, "total": round(v, 2)} for k, v in sorted(monthly.items())]


async def get_taxa_cancelamento(
    therapist_id: str,
    db: Any,
) -> Dict:
    """Cancellation and no-show rates for a therapist.

    Returns:
        - total_appointments: total non-waiting appointments
        - cancelled: free cancellations
        - late_cancelled: late cancellations
        - no_show: no-shows
        - completed: completed sessions
        - cancellation_rate: (cancelled + late_cancelled) / total
        - no_show_rate: no_show / total
    """
    result = (
        db.table("appointments")
        .select("status")
        .eq("therapist_id", therapist_id)
        .not_.in_("status", ["waiting"])
        .execute()
    )
    appointments = result.data or []
    total = len(appointments)

    if total == 0:
        return {
            "total_appointments": 0,
            "cancelled": 0,
            "late_cancelled": 0,
            "no_show": 0,
            "completed": 0,
            "cancellation_rate": 0.0,
            "no_show_rate": 0.0,
        }

    status_counts: Dict[str, int] = defaultdict(int)
    for appt in appointments:
        status_counts[appt.get("status", "unknown")] += 1

    cancelled = status_counts.get("cancelled", 0)
    late_cancelled = status_counts.get("late_cancelled", 0)
    no_show = status_counts.get("no_show", 0)
    completed = status_counts.get("completed", 0)

    return {
        "total_appointments": total,
        "cancelled": cancelled,
        "late_cancelled": late_cancelled,
        "no_show": no_show,
        "completed": completed,
        "cancellation_rate": round((cancelled + late_cancelled) / total, 4),
        "no_show_rate": round(no_show / total, 4),
    }
