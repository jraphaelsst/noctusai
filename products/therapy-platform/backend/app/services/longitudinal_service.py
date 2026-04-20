"""
Longitudinal Service — AI-generated longitudinal analyses across sessions.

Two independent tracks:
  - Clinical longitudinal: for therapist/clinic_admin — based on clinical
    summaries (Track 2) + observations across all sessions
  - Patient longitudinal: for patient — based on base summaries (Track 1) +
    patient notes; uses second-person tone ("Você tem explorado...")
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from app.config import settings
from app.dependencies import first_or_none

logger = logging.getLogger(__name__)

_PLACEHOLDER_ANALYSIS = (
    "[Análise longitudinal não disponível — OpenAI API Key não configurada. "
    "Configure em Configurações > Chaves de API]"
)

_DEFAULT_CLINICAL_LONGITUDINAL_PROMPT = (
    "Você é um assistente clínico especializado em psicoterapia. "
    "Com base nos resumos clínicos e observações de múltiplas sessões "
    "entre o terapeuta e o paciente, gere uma análise longitudinal contendo:\n"
    "1. narrative_summary: Narrativa integrada do progresso terapêutico (máx 1000 palavras)\n"
    "2. recurring_themes: Temas recorrentes identificados (lista)\n"
    "3. progress_timeline: Linha do tempo de progresso com marcos importantes (lista de objetos com 'session' e 'milestone')\n"
    "4. unresolved_topics: Tópicos não resolvidos que merecem atenção (lista)\n"
    "5. observation_insights: Insights derivados das observações do terapeuta (lista)\n\n"
    "Responda APENAS em JSON com as chaves acima."
)

_DEFAULT_PATIENT_LONGITUDINAL_PROMPT = (
    "Você é um assistente de bem-estar emocional. "
    "Com base nos resumos das sessões e nas anotações pessoais do paciente, "
    "gere uma reflexão longitudinal acolhedora usando segunda pessoa (\"Você\").\n"
    "Gere:\n"
    "1. narrative_summary: Reflexão narrativa sobre a jornada terapêutica (máx 800 palavras, tom acolhedor)\n"
    "2. recurring_themes: Temas que você tem explorado (lista)\n"
    "3. progress_reflection: Reflexão sobre seu progresso e conquistas (texto)\n"
    "4. ongoing_topics: Tópicos que continuam em desenvolvimento (lista)\n\n"
    "Responda APENAS em JSON com as chaves acima."
)


def _openai_configured() -> bool:
    return bool(settings.openai_api_key)


def _get_setting(db: Any, key: str, default: str) -> str:
    result = (
        db.table("platform_settings")
        .select("value")
        .eq("key", key)
        .execute()
    )
    row = first_or_none(result)
    return row["value"] if row else default


async def _call_openai(
    system_prompt: str,
    user_content: str,
    clinic_id: Optional[str] = None,
) -> Dict:
    """Call the configured LLM and parse its JSON response.

    **LGPD**: `user_content` aggregates multiple session summaries — Art. 11
    sensitive data. We pass `cache=False` so no response cache retains it.
    See `LGPD-WARNINGS.md` entry `longitudinal-clinical-aggregation`.

    `clinic_id` is threaded through as `org_id` so the lib picks up the
    clinic's own provider key (Tier 1) before falling back to platform / env.
    """
    from noctusai_lib.llm import LLMNotConfigured, chat_completion

    try:
        content = await chat_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            model="gpt-4o",
            temperature=0.4,
            max_tokens=3000,
            response_format={"type": "json_object"},
            cache=False,  # LGPD: longitudinal clinical aggregation
            org_id=clinic_id,
        )
        return json.loads(content or "{}")
    except LLMNotConfigured as e:
        logger.warning("LLM not configured for longitudinal call: %s", e)
        return {"error": str(e)}
    except Exception as e:
        logger.error("LLM longitudinal call failed: %s", e)
        return {"error": str(e)}


def _next_version(db: Any, table: str, patient_id: str, therapist_id: str) -> int:
    """Determine the next version number for a longitudinal analysis."""
    result = (
        db.table(table)
        .select("version_number")
        .eq("patient_id", patient_id)
        .eq("therapist_id", therapist_id)
        .order("version_number", desc=True)
        .execute()
    )
    latest = first_or_none(result)
    return (latest["version_number"] + 1) if latest else 1


# ---------------------------------------------------------------------------
# Clinical Longitudinal
# ---------------------------------------------------------------------------

async def generate_clinical_longitudinal(
    patient_id: str,
    therapist_id: str,
    db: Any,
    clinic_id: Optional[str] = None,
) -> Dict:
    """Generate a clinical longitudinal analysis.

    Fetches all clinical summary versions (Track 2) and all observations
    for the patient-therapist pair. Checks minimum sessions threshold.
    """
    min_sessions = int(_get_setting(db, "longitudinal_min_sessions", "4"))

    # Fetch session records for this patient-therapist pair
    # Session records are linked through appointments
    appointments_result = (
        db.table("appointments")
        .select("id")
        .eq("therapist_id", therapist_id)
        .eq("patient_id", patient_id)
        .eq("status", "completed")
        .execute()
    )
    appointment_ids = [a["id"] for a in (appointments_result.data or [])]

    if len(appointment_ids) < min_sessions:
        return {
            "status": "insufficient_sessions",
            "message": (
                f"São necessárias pelo menos {min_sessions} sessões concluídas "
                f"para gerar a análise longitudinal. Sessões atuais: {len(appointment_ids)}."
            ),
            "sessions_completed": len(appointment_ids),
            "sessions_required": min_sessions,
        }

    # Fetch session records
    session_records = (
        db.table("session_records")
        .select("*")
        .in_("appointment_id", appointment_ids)
        .order("created_at")
        .execute()
    )
    records = session_records.data or []
    if not records:
        return {"status": "no_records", "message": "Nenhum registro de sessão encontrado"}

    record_ids = [r["id"] for r in records]

    # Fetch latest clinical summaries for each session
    summaries_result = (
        db.table("session_summary_versions")
        .select("*")
        .in_("session_record_id", record_ids)
        .eq("track", "clinical")
        .order("version_number", desc=True)
        .execute()
    )
    # Deduplicate: keep only latest version per session_record_id
    seen_records: set[str] = set()
    clinical_summaries: list[Dict] = []
    for s in (summaries_result.data or []):
        if s["session_record_id"] not in seen_records:
            seen_records.add(s["session_record_id"])
            clinical_summaries.append(s)

    # Fetch all observations
    observations_result = (
        db.table("session_observations")
        .select("*")
        .in_("session_record_id", record_ids)
        .is_("deleted_at", "null")
        .order("created_at")
        .execute()
    )
    observations = observations_result.data or []

    if not _openai_configured():
        version_number = _next_version(db, "clinical_longitudinal_analyses", patient_id, therapist_id)
        placeholder = {
            "narrative_summary": _PLACEHOLDER_ANALYSIS,
            "recurring_themes": [],
            "progress_timeline": [],
            "unresolved_topics": [],
            "observation_insights": [],
        }
        db.table("clinical_longitudinal_analyses").insert({
            "patient_id": patient_id,
            "therapist_id": therapist_id,
            "version_number": version_number,
            **placeholder,
        }).execute()
        return placeholder

    # Build context for GPT
    prompt = _get_setting(db, "ai_prompt_longitudinal_clinical", _DEFAULT_CLINICAL_LONGITUDINAL_PROMPT)

    sessions_text_parts: list[str] = []
    for i, summary in enumerate(clinical_summaries, 1):
        sessions_text_parts.append(
            f"--- Sessão {i} ---\n"
            f"Resumo: {summary.get('summary', '')}\n"
            f"Pontos-chave: {', '.join(summary.get('key_points', []))}\n"
            f"Tags: {', '.join(summary.get('tags', []))}"
        )

    obs_text_parts: list[str] = []
    for obs in observations:
        obs_text_parts.append(f"- {obs.get('observation_text', '')}")

    user_content = (
        "RESUMOS CLÍNICOS DAS SESSÕES:\n"
        + "\n\n".join(sessions_text_parts)
    )
    if obs_text_parts:
        user_content += "\n\nOBSERVAÇÕES DO TERAPEUTA:\n" + "\n".join(obs_text_parts)

    result = await _call_openai(prompt, user_content, clinic_id=clinic_id)

    if "error" in result and len(result) == 1:
        return {"status": "error", "message": result["error"]}

    version_number = _next_version(db, "clinical_longitudinal_analyses", patient_id, therapist_id)
    row_data = {
        "patient_id": patient_id,
        "therapist_id": therapist_id,
        "version_number": version_number,
        "narrative_summary": result.get("narrative_summary", ""),
        "recurring_themes": result.get("recurring_themes", []),
        "progress_timeline": result.get("progress_timeline", []),
        "unresolved_topics": result.get("unresolved_topics", []),
        "observation_insights": result.get("observation_insights", []),
    }
    db.table("clinical_longitudinal_analyses").insert(row_data).execute()

    return result


# ---------------------------------------------------------------------------
# Patient Longitudinal
# ---------------------------------------------------------------------------

async def generate_patient_longitudinal(
    patient_id: str,
    therapist_id: str,
    db: Any,
    clinic_id: Optional[str] = None,
) -> Dict:
    """Generate a patient-facing longitudinal analysis.

    Uses base summaries (Track 1) and patient session notes.
    Second-person tone ("Você tem explorado...").
    """
    min_sessions = int(_get_setting(db, "longitudinal_min_sessions", "4"))

    # Fetch completed appointments
    appointments_result = (
        db.table("appointments")
        .select("id")
        .eq("therapist_id", therapist_id)
        .eq("patient_id", patient_id)
        .eq("status", "completed")
        .execute()
    )
    appointment_ids = [a["id"] for a in (appointments_result.data or [])]

    if len(appointment_ids) < min_sessions:
        return {
            "status": "insufficient_sessions",
            "message": (
                f"São necessárias pelo menos {min_sessions} sessões concluídas "
                f"para gerar sua reflexão de jornada. Sessões atuais: {len(appointment_ids)}."
            ),
            "sessions_completed": len(appointment_ids),
            "sessions_required": min_sessions,
        }

    # Fetch session records
    session_records = (
        db.table("session_records")
        .select("*")
        .in_("appointment_id", appointment_ids)
        .order("created_at")
        .execute()
    )
    records = session_records.data or []
    if not records:
        return {"status": "no_records", "message": "Nenhum registro de sessão encontrado"}

    record_ids = [r["id"] for r in records]

    # Fetch latest base summaries for each session
    summaries_result = (
        db.table("session_summary_versions")
        .select("*")
        .in_("session_record_id", record_ids)
        .eq("track", "base")
        .order("version_number", desc=True)
        .execute()
    )
    seen_records: set[str] = set()
    base_summaries: list[Dict] = []
    for s in (summaries_result.data or []):
        if s["session_record_id"] not in seen_records:
            seen_records.add(s["session_record_id"])
            base_summaries.append(s)

    # Fetch patient notes
    notes_result = (
        db.table("patient_session_notes")
        .select("*")
        .in_("session_record_id", record_ids)
        .order("created_at")
        .execute()
    )
    patient_notes = notes_result.data or []

    if not _openai_configured():
        version_number = _next_version(db, "patient_longitudinal_analyses", patient_id, therapist_id)
        placeholder = {
            "narrative_summary": _PLACEHOLDER_ANALYSIS,
            "recurring_themes": [],
            "progress_reflection": "",
            "ongoing_topics": [],
        }
        db.table("patient_longitudinal_analyses").insert({
            "patient_id": patient_id,
            "therapist_id": therapist_id,
            "version_number": version_number,
            **placeholder,
        }).execute()
        return placeholder

    prompt = _get_setting(db, "ai_prompt_longitudinal_patient", _DEFAULT_PATIENT_LONGITUDINAL_PROMPT)

    sessions_text_parts: list[str] = []
    for i, summary in enumerate(base_summaries, 1):
        sessions_text_parts.append(
            f"--- Sessão {i} ---\n"
            f"Resumo: {summary.get('summary', '')}\n"
            f"Pontos-chave: {', '.join(summary.get('key_points', []))}"
        )

    notes_text_parts: list[str] = []
    for note in patient_notes:
        notes_text_parts.append(f"- {note.get('note_text', '')}")

    user_content = (
        "RESUMOS DAS SESSÕES:\n"
        + "\n\n".join(sessions_text_parts)
    )
    if notes_text_parts:
        user_content += "\n\nSUAS ANOTAÇÕES PESSOAIS:\n" + "\n".join(notes_text_parts)

    result = await _call_openai(prompt, user_content, clinic_id=clinic_id)

    if "error" in result and len(result) == 1:
        return {"status": "error", "message": result["error"]}

    version_number = _next_version(db, "patient_longitudinal_analyses", patient_id, therapist_id)
    row_data = {
        "patient_id": patient_id,
        "therapist_id": therapist_id,
        "version_number": version_number,
        "narrative_summary": result.get("narrative_summary", ""),
        "recurring_themes": result.get("recurring_themes", []),
        "progress_reflection": result.get("progress_reflection", ""),
        "ongoing_topics": result.get("ongoing_topics", []),
    }
    db.table("patient_longitudinal_analyses").insert(row_data).execute()

    return result
