"""
Summary Service — AI-powered session summary generation via OpenAI GPT.

Generates two independent tracks:
  - Track 1 (base): transcript-only summary (visible to patient)
  - Track 2 (clinical): transcript + observations (therapist/clinic_admin only)

Each regeneration creates a new version row, preserving full history.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from app.config import settings
from app.dependencies import first_or_none

logger = logging.getLogger(__name__)

_PLACEHOLDER_SUMMARY = (
    "[Resumo não disponível — OpenAI API Key não configurada. "
    "Configure em Configurações > Chaves de API]"
)

# Default prompts used when platform_settings entries are missing
_DEFAULT_BASE_PROMPT = (
    "Você é um assistente de saúde mental. Com base na transcrição da sessão "
    "de terapia abaixo, gere:\n"
    "1. Um resumo objetivo da sessão (máximo 500 palavras)\n"
    "2. Pontos-chave discutidos (lista)\n"
    "3. Tags temáticas relevantes (lista)\n\n"
    "Use linguagem acolhedora e em segunda pessoa (\"Você\").\n"
    "Responda APENAS em JSON com as chaves: summary, key_points, tags."
)

_DEFAULT_CLINICAL_PROMPT = (
    "Você é um assistente clínico para profissionais de saúde mental. "
    "Com base na transcrição da sessão e nas observações do terapeuta abaixo, gere:\n"
    "1. Um resumo clínico profissional (máximo 700 palavras)\n"
    "2. Pontos-chave clínicos (lista)\n"
    "3. Tags clínicas (lista)\n\n"
    "IMPORTANTE: Se as observações do terapeuta repetem informações já "
    "presentes na transcrição, reconheça-as sem duplicar. Foque no que "
    "as observações adicionam de novo.\n"
    "Responda APENAS em JSON com as chaves: summary, key_points, tags."
)

_DEFAULT_TAG_PROMPT = (
    "Com base no texto abaixo, extraia de 3 a 8 tags temáticas relevantes "
    "para o contexto de psicoterapia. Responda APENAS como JSON array de strings."
)


def _openai_configured() -> bool:
    return bool(settings.openai_api_key)


def _get_prompt(db: Any, key: str, default: str) -> str:
    """Read an AI prompt from platform_settings."""
    result = (
        db.table("platform_settings")
        .select("value")
        .eq("key", key)
        .execute()
    )
    row = first_or_none(result)
    return row["value"] if row else default


async def _call_openai(system_prompt: str, user_content: str) -> Dict:
    """Call OpenAI GPT and parse the JSON response.

    Returns parsed dict or a fallback structure on failure.
    """
    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.openai_api_key)
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=0.4,
            max_tokens=2000,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or "{}"
        return json.loads(content)
    except Exception as e:
        logger.error("OpenAI call failed: %s", e)
        return {
            "summary": f"[Erro ao gerar resumo: {e}]",
            "key_points": [],
            "tags": [],
        }


def _next_version_number(db: Any, session_record_id: str, track: str) -> int:
    """Determine the next version number for a summary track."""
    result = (
        db.table("session_summary_versions")
        .select("version_number")
        .eq("session_record_id", session_record_id)
        .eq("track", track)
        .order("version_number", desc=True)
        .execute()
    )
    latest = first_or_none(result)
    return (latest["version_number"] + 1) if latest else 1


# ---------------------------------------------------------------------------
# Generate Both Summary Tracks
# ---------------------------------------------------------------------------

async def generate_session_summaries(
    session_record_id: str,
    transcript: str,
    observations: List[Dict],
    source: str,
    org_ai_config: Optional[Dict],
    db: Any,
) -> Dict:
    """Generate Track 1 (base) and Track 2 (clinical) summaries.

    Creates session_summary_versions rows for both tracks.
    Returns both summaries.
    """
    if not _openai_configured():
        placeholder = {
            "summary": _PLACEHOLDER_SUMMARY,
            "key_points": [],
            "tags": [],
        }
        # Still create version rows with placeholder content
        for track in ("base", "clinical"):
            version_number = _next_version_number(db, session_record_id, track)
            db.table("session_summary_versions").insert({
                "session_record_id": session_record_id,
                "track": track,
                "version_number": version_number,
                "summary": placeholder["summary"],
                "key_points": placeholder["key_points"],
                "tags": placeholder["tags"],
                "source": source,
            }).execute()
        return {"base": placeholder, "clinical": placeholder}

    # --- Track 1: Base summary (transcript only) ---
    base_prompt = _get_prompt(db, "ai_prompt_base_summary", _DEFAULT_BASE_PROMPT)
    base_result = await _call_openai(base_prompt, f"TRANSCRIÇÃO:\n{transcript}")

    base_version = _next_version_number(db, session_record_id, "base")
    db.table("session_summary_versions").insert({
        "session_record_id": session_record_id,
        "track": "base",
        "version_number": base_version,
        "summary": base_result.get("summary", ""),
        "key_points": base_result.get("key_points", []),
        "tags": base_result.get("tags", []),
        "source": source,
    }).execute()

    # --- Track 2: Clinical summary (transcript + observations) ---
    clinical_prompt = _get_prompt(db, "ai_prompt_clinical_summary", _DEFAULT_CLINICAL_PROMPT)
    obs_text = ""
    if observations:
        obs_lines = [
            f"- {obs.get('observation_text', '')}" for obs in observations
        ]
        obs_text = "\n\nOBSERVAÇÕES DO TERAPEUTA:\n" + "\n".join(obs_lines)

    clinical_input = f"TRANSCRIÇÃO:\n{transcript}{obs_text}"
    clinical_result = await _call_openai(clinical_prompt, clinical_input)

    clinical_version = _next_version_number(db, session_record_id, "clinical")
    db.table("session_summary_versions").insert({
        "session_record_id": session_record_id,
        "track": "clinical",
        "version_number": clinical_version,
        "summary": clinical_result.get("summary", ""),
        "key_points": clinical_result.get("key_points", []),
        "tags": clinical_result.get("tags", []),
        "source": source,
    }).execute()

    return {
        "base": base_result,
        "clinical": clinical_result,
    }


# ---------------------------------------------------------------------------
# Regenerate Clinical Summary (Track 2 only)
# ---------------------------------------------------------------------------

async def regenerate_clinical_summary(session_record_id: str, db: Any) -> Dict:
    """Regenerate the clinical summary after observation changes.

    Fetches the latest transcript and all non-deleted observations,
    then generates a new Track 2 version. Track 1 is unaffected.
    """
    # Fetch session record for transcript
    sr_result = (
        db.table("session_records")
        .select("combined_transcript")
        .eq("id", session_record_id)
        .execute()
    )
    sr = first_or_none(sr_result)
    if not sr:
        logger.error("Session record %s not found for regeneration", session_record_id)
        return {"error": "Registro de sessão não encontrado"}

    transcript = sr.get("combined_transcript") or ""

    # Fetch non-deleted observations
    obs_result = (
        db.table("session_observations")
        .select("*")
        .eq("session_record_id", session_record_id)
        .is_("deleted_at", "null")
        .order("created_at")
        .execute()
    )
    observations = obs_result.data or []

    if not _openai_configured():
        return {
            "summary": _PLACEHOLDER_SUMMARY,
            "key_points": [],
            "tags": [],
        }

    clinical_prompt = _get_prompt(db, "ai_prompt_clinical_summary", _DEFAULT_CLINICAL_PROMPT)
    obs_text = ""
    if observations:
        obs_lines = [f"- {obs.get('observation_text', '')}" for obs in observations]
        obs_text = "\n\nOBSERVAÇÕES DO TERAPEUTA:\n" + "\n".join(obs_lines)

    clinical_input = f"TRANSCRIÇÃO:\n{transcript}{obs_text}"
    clinical_result = await _call_openai(clinical_prompt, clinical_input)

    version_number = _next_version_number(db, session_record_id, "clinical")
    db.table("session_summary_versions").insert({
        "session_record_id": session_record_id,
        "track": "clinical",
        "version_number": version_number,
        "summary": clinical_result.get("summary", ""),
        "key_points": clinical_result.get("key_points", []),
        "tags": clinical_result.get("tags", []),
        "source": "observation_change",
    }).execute()

    return clinical_result


# ---------------------------------------------------------------------------
# Manual Edit → New Version
# ---------------------------------------------------------------------------

async def edit_clinical_summary(
    summary_version_id: str,
    data: Dict,
    db: Any,
) -> Dict:
    """Create a new version from a manual edit by the therapist.

    Reads the existing version's session_record_id and track,
    then inserts a new version with source='manual_edit'.
    """
    existing = (
        db.table("session_summary_versions")
        .select("*")
        .eq("id", summary_version_id)
        .execute()
    )
    row = first_or_none(existing)
    if not row:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Versão do resumo não encontrada")

    session_record_id = row["session_record_id"]
    track = row["track"]
    version_number = _next_version_number(db, session_record_id, track)

    new_version = {
        "session_record_id": session_record_id,
        "track": track,
        "version_number": version_number,
        "summary": data.get("summary", row.get("summary", "")),
        "key_points": data.get("key_points", row.get("key_points", [])),
        "tags": data.get("tags", row.get("tags", [])),
        "source": "manual_edit",
    }
    result = db.table("session_summary_versions").insert(new_version).execute()
    return first_or_none(result) or new_version
