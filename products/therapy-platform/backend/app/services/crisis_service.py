"""
Crisis Service — Risk keyword detection, alert creation, and severity assessment.

Scans text (session transcripts, journal entries, chat messages) for
crisis-related keywords in Portuguese. Creates alerts for therapists
when risk indicators are detected.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from app.dependencies import first_or_none

logger = logging.getLogger(__name__)

SP_TZ = timezone(timedelta(hours=-3))

# Portuguese crisis/risk keywords — sorted by severity (most severe first)
RISK_KEYWORDS: list[str] = [
    "suicidio",
    "suicídio",
    "me matar",
    "quero morrer",
    "nao quero viver",
    "não quero viver",
    "acabar com tudo",
    "acabar com a vida",
    "tirar minha vida",
    "autolesao",
    "autolesão",
    "me machucar",
    "me cortar",
    "automutilação",
    "automutilacao",
    "nao aguento mais",
    "não aguento mais",
    "sem saida",
    "sem saída",
    "ninguem se importa",
    "ninguém se importa",
    "melhor sem mim",
    "pensamentos de morte",
    "ideacao suicida",
    "ideação suicida",
    "planejamento suicida",
    "tentativa de suicidio",
    "tentativa de suicídio",
    "overdose",
    "pular de",
]

# High-severity keywords that always flag as critica/alta
_HIGH_SEVERITY_KEYWORDS = {
    "suicidio", "suicídio", "me matar", "tirar minha vida",
    "tentativa de suicidio", "tentativa de suicídio",
    "planejamento suicida", "ideacao suicida", "ideação suicida",
    "overdose", "pular de",
}


def _normalize(text: str) -> str:
    """Lowercase and normalize whitespace for matching."""
    return re.sub(r"\s+", " ", text.lower().strip())


# ---------------------------------------------------------------------------
# Text scanning
# ---------------------------------------------------------------------------

def scan_text(
    text: str,
    patient_id: str,
    therapist_id: str,
    source_type: str,
    source_id: str,
    db: Any,
) -> Optional[Dict]:
    """Scan text for risk keywords and create an alert if found.

    Args:
        text: Text content to scan.
        patient_id: Patient who authored/is subject of the text.
        therapist_id: Responsible therapist.
        source_type: Origin type (e.g., 'session_transcript', 'journal', 'chat').
        source_id: ID of the source record.
        db: Supabase client.

    Returns:
        Alert dict if keywords found, None otherwise.
    """
    if not text or not text.strip():
        return None

    normalized = _normalize(text)
    found_keywords: list[str] = []

    for keyword in RISK_KEYWORDS:
        if keyword in normalized:
            found_keywords.append(keyword)

    if not found_keywords:
        return None

    severity = assess_severity(text, found_keywords)

    alert_data = {
        "patient_id": patient_id,
        "therapist_id": therapist_id,
        "source_type": source_type,
        "source_id": source_id,
        "keywords_found": found_keywords,
        "severity": severity,
        "status": "pendente",
        "detected_at": datetime.now(SP_TZ).isoformat(),
    }

    try:
        result = db.table("crisis_alerts").insert(alert_data).execute()
        alert = first_or_none(result)
        if alert:
            logger.warning(
                "Crisis alert created for patient %s (severity=%s, keywords=%d)",
                patient_id,
                severity,
                len(found_keywords),
            )
            return alert
    except Exception as e:
        logger.error("Failed to create crisis alert: %s", e)

    return None


# ---------------------------------------------------------------------------
# Severity assessment
# ---------------------------------------------------------------------------

def assess_severity(text: str, keywords_found: list[str]) -> str:
    """Determine alert severity based on keywords found and context.

    Returns: 'baixa', 'media', 'alta', or 'critica'.
    """
    # Check for high-severity keywords
    has_high_severity = any(kw in _HIGH_SEVERITY_KEYWORDS for kw in keywords_found)

    if has_high_severity and len(keywords_found) >= 3:
        return "critica"
    if has_high_severity:
        return "alta"
    if len(keywords_found) >= 3:
        return "alta"
    if len(keywords_found) >= 2:
        return "media"
    return "baixa"


# ---------------------------------------------------------------------------
# Alert management
# ---------------------------------------------------------------------------

async def list_alerts(
    therapist_id: str,
    db: Any,
    status_filter: Optional[str] = None,
) -> List[Dict]:
    """List crisis alerts for a therapist, optionally filtered by status."""
    query = (
        db.table("crisis_alerts")
        .select("*")
        .eq("therapist_id", therapist_id)
    )
    if status_filter:
        query = query.eq("status", status_filter)

    result = query.order("detected_at", desc=True).execute()
    return result.data or []


async def review_alert(
    alert_id: str,
    reviewer_id: str,
    data: Dict,
    db: Any,
) -> Dict:
    """Review a crisis alert (mark as reviewed, false positive, or referred)."""
    check = db.table("crisis_alerts").select("id, status").eq("id", alert_id).execute()
    alert = first_or_none(check)
    if not alert:
        raise HTTPException(status_code=404, detail="Alerta não encontrado")

    if alert["status"] != "pendente":
        raise HTTPException(status_code=400, detail="Alerta já foi revisado")

    update_data = {
        "status": data["status"],
        "reviewed_by": reviewer_id,
        "reviewed_at": datetime.now(SP_TZ).isoformat(),
    }
    result = (
        db.table("crisis_alerts")
        .update(update_data)
        .eq("id", alert_id)
        .execute()
    )
    row = first_or_none(result)
    logger.info("Crisis alert %s reviewed as '%s' by %s", alert_id, data["status"], reviewer_id)
    return row or {**alert, **update_data}


# ---------------------------------------------------------------------------
# Manual scan
# ---------------------------------------------------------------------------

async def manual_scan(db: Any) -> Dict:
    """Scan recent patient activity for crisis indicators.

    Checks mood entries and journal entries from the last 7 days
    for crisis keywords.
    """
    cutoff = (datetime.now(SP_TZ) - timedelta(days=7)).isoformat()
    alerts_created = 0

    # Scan recent mood entries
    mood_result = (
        db.table("mood_entries")
        .select("id, patient_id, nota")
        .gte("created_at", cutoff)
        .execute()
    )
    for entry in (mood_result.data or []):
        nota = entry.get("nota") or ""
        if nota:
            alert = scan_text(
                text=nota,
                patient_id=entry["patient_id"],
                therapist_id="system",
                source_type="mood_entry",
                source_id=entry["id"],
                db=db,
            )
            if alert:
                alerts_created += 1

    # Scan recent journal entries
    journal_result = (
        db.table("journal_entries")
        .select("id, patient_id, conteudo")
        .gte("created_at", cutoff)
        .execute()
    )
    for entry in (journal_result.data or []):
        conteudo = entry.get("conteudo") or ""
        if conteudo:
            alert = scan_text(
                text=conteudo,
                patient_id=entry["patient_id"],
                therapist_id="system",
                source_type="journal",
                source_id=entry["id"],
                db=db,
            )
            if alert:
                alerts_created += 1

    logger.info("Manual crisis scan complete: %d alerts created", alerts_created)
    return {"alerts_created": alerts_created}
