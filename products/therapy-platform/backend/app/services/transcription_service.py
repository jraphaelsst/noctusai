"""
Transcription Service — Audio-to-text via OpenAI Whisper.

Handles downloading audio files and transcribing them, with graceful
degradation when the OpenAI API key is not configured.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from app.config import settings
from app.dependencies import first_or_none

logger = logging.getLogger(__name__)

_PLACEHOLDER_TEXT = (
    "[Transcrição não disponível — OpenAI API Key não configurada. "
    "Configure em Configurações > Chaves de API]"
)


def _openai_configured() -> bool:
    return bool(settings.openai_api_key)


# ---------------------------------------------------------------------------
# Single Segment Transcription
# ---------------------------------------------------------------------------

async def transcribe_segment(
    audio_url: str,
    segment_number: int,
    clinic_id: Optional[str] = None,
) -> str:
    """Transcribe a single audio segment via OpenAI Whisper.

    Downloads the audio file and sends it to the Whisper API.
    Returns placeholder text if the OpenAI key is not configured or the
    call fails.
    """
    if not _openai_configured():
        logger.warning(
            "OpenAI não configurada — retornando placeholder para segmento %d",
            segment_number,
        )
        return _PLACEHOLDER_TEXT

    try:
        import httpx

        from noctusai_lib.integrations.llm import LLMNotConfigured, transcribe_audio

        if audio_url.startswith("mock://"):
            logger.info("Mock audio URL — retornando placeholder para segmento %d", segment_number)
            return f"[Segmento {segment_number} — áudio mock, sem transcrição real]"

        # Download audio file. (httpx here is generic HTTP, not an OpenAI call —
        # shared-lib LLM handles the Whisper side.)
        async with httpx.AsyncClient(timeout=120) as http:
            resp = await http.get(audio_url)
            resp.raise_for_status()
            audio_data = resp.content

        # LGPD: raw patient audio. Whisper is a 3rd-party egress; the outbound
        # is unavoidable for the feature but the response is never cached
        # (transcribe_audio doesn't go through the cache layer).
        transcript = await transcribe_audio(
            audio_data,
            model="whisper-1",
            filename="segment.ogg",
            language="pt",
            response_format="text",
            org_id=clinic_id,
        )
        return str(transcript).strip()

    except LLMNotConfigured as exc:
        logger.warning(
            "transcription: LLM not configured (%s); returning placeholder for segment %d (clinic_id=%s)",
            exc, segment_number, clinic_id,
        )
        return _PLACEHOLDER_TEXT
    except Exception as e:
        logger.error(
            "Erro ao transcrever segmento %d: %s",
            segment_number,
            e,
        )
        return f"[Erro na transcrição do segmento {segment_number}]"


# ---------------------------------------------------------------------------
# Full Transcript Assembly
# ---------------------------------------------------------------------------

async def assemble_transcript(
    appointment_id: str,
    db: Any,
    clinic_id: Optional[str] = None,
    *,
    transcribe_segment_fn: Optional[Any] = None,
) -> str:
    """Assemble the full transcript from all audio segments.

    Transcribes each segment individually and concatenates them with
    contextual markers indicating pauses, resumes, and reopens.

    Updates each segment's transcription_text and is_transcribed flag.

    Args:
        appointment_id: appointment whose segments to transcribe.
        db: Supabase client.
        clinic_id: optional clinic scope for credential lookup.
        transcribe_segment_fn: DI seam for tests — defaults to
            `transcribe_segment`. Production code should never pass it.
    """
    if transcribe_segment_fn is None:
        transcribe_segment_fn = transcribe_segment
    segments_result = (
        db.table("session_audio_segments")
        .select("*")
        .eq("appointment_id", appointment_id)
        .order("segment_number")
        .execute()
    )
    segments = segments_result.data or []

    if not segments:
        logger.warning(
            "Nenhum segmento de áudio encontrado para appointment %s",
            appointment_id,
        )
        return "[Nenhum áudio gravado nesta sessão]"

    transcript_parts: list[str] = []

    for i, segment in enumerate(segments):
        seg_type = segment.get("segment_type", "initial")
        seg_number = segment.get("segment_number", i + 1)
        audio_url = segment.get("audio_url") or segment.get("recording_url")

        # Insert contextual markers between segments
        if i > 0:
            prev_segment = segments[i - 1]
            pause_time = prev_segment.get("ended_at", "")
            resume_time = segment.get("started_at", "")

            pause_display = _format_time(pause_time)
            resume_display = _format_time(resume_time)

            if seg_type == "reopened":
                transcript_parts.append(
                    f"\n[Sessão reaberta às {resume_display}]\n"
                )
            else:
                transcript_parts.append(
                    f"\n[Sessão pausada às {pause_display}]\n"
                    f"[Sessão retomada às {resume_display}]\n"
                )

        # Transcribe
        if audio_url:
            text = await transcribe_segment_fn(audio_url, seg_number, clinic_id=clinic_id)
        else:
            text = f"[Segmento {seg_number} — áudio não disponível]"

        transcript_parts.append(text)

        # Update segment record
        db.table("session_audio_segments").update({
            "transcription_text": text,
            "is_transcribed": True,
        }).eq("id", segment["id"]).execute()

    return "\n".join(transcript_parts)


def _format_time(iso_str: str) -> str:
    """Extract HH:MM from an ISO datetime string."""
    if not iso_str:
        return "--:--"
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%H:%M")
    except (ValueError, AttributeError) as exc:
        logger.warning("transcription: cannot format time from %r (%s); using placeholder '--:--'", iso_str, exc)
        return "--:--"
