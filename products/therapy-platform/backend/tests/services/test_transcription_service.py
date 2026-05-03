"""
Tests for the Transcription Service.

Covers: single segment transcription (OpenAI configured/unconfigured,
mock URLs, download errors, Whisper errors), full transcript assembly
(multiple segments, contextual markers, empty segments, segment updates),
and time formatting.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from tests.conftest import MockSupabaseClient
from app.services import transcription_service


# ---------------------------------------------------------------------------
# _format_time
# ---------------------------------------------------------------------------

class TestFormatTime:
    def test_format_valid_iso(self):
        result = transcription_service._format_time("2026-04-01T14:30:00Z")
        assert result == "14:30"

    def test_format_iso_with_offset(self):
        result = transcription_service._format_time("2026-04-01T14:30:00-03:00")
        assert result == "14:30"

    def test_format_empty_string(self):
        result = transcription_service._format_time("")
        assert result == "--:--"

    def test_format_none_like(self):
        result = transcription_service._format_time("")
        assert result == "--:--"

    def test_format_invalid_string(self):
        result = transcription_service._format_time("not-a-date")
        assert result == "--:--"


# ---------------------------------------------------------------------------
# transcribe_segment
# ---------------------------------------------------------------------------

class TestTranscribeSegment:
    @pytest.mark.asyncio
    async def test_returns_placeholder_when_openai_not_configured(self):
        """Returns placeholder text when openai_api_key is not set."""
        with patch.object(transcription_service, "_openai_configured", return_value=False):
            result = await transcription_service.transcribe_segment(
                audio_url="https://example.com/audio.ogg",
                segment_number=1,
            )
        assert "não disponível" in result
        assert "OpenAI API Key não configurada" in result

    @pytest.mark.asyncio
    async def test_returns_mock_placeholder_for_mock_url(self):
        """Returns special placeholder for mock:// URLs."""
        with patch.object(transcription_service, "_openai_configured", return_value=True):
            result = await transcription_service.transcribe_segment(
                audio_url="mock://test-audio.ogg",
                segment_number=3,
            )
        assert "mock" in result.lower()
        assert "3" in result

    @pytest.mark.asyncio
    async def test_transcription_success(self):
        """Happy path: downloads audio and delegates to shared-lib transcribe_audio."""
        import httpx as _httpx

        mock_http_response = MagicMock()
        mock_http_response.content = b"fake-audio-data"
        mock_http_response.raise_for_status = MagicMock()

        mock_http_client = AsyncMock()
        mock_http_client.get = AsyncMock(return_value=mock_http_response)
        mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
        mock_http_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch.object(transcription_service, "_openai_configured", return_value=True),
            patch.object(_httpx, "AsyncClient", return_value=mock_http_client),
            patch(
                "noctusai_lib.integrations.llm.transcribe_audio",
                new=AsyncMock(return_value="Paciente relatou melhora significativa."),
            ),
        ):
            result = await transcription_service.transcribe_segment(
                audio_url="https://storage.example.com/audio/seg1.ogg",
                segment_number=1,
            )

        assert result == "Paciente relatou melhora significativa."

    @pytest.mark.asyncio
    async def test_transcription_download_failure(self):
        """Returns error message when audio download fails."""
        import httpx as _httpx

        mock_http_client = AsyncMock()
        mock_http_client.get = AsyncMock(side_effect=Exception("Connection timeout"))
        mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
        mock_http_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch.object(transcription_service, "_openai_configured", return_value=True),
            patch.object(_httpx, "AsyncClient", return_value=mock_http_client),
        ):
            result = await transcription_service.transcribe_segment(
                audio_url="https://storage.example.com/audio/seg1.ogg",
                segment_number=2,
            )

        assert "Erro na transcrição" in result
        assert "2" in result

    @pytest.mark.asyncio
    async def test_transcription_whisper_failure(self):
        """Returns error message when shared-lib transcribe_audio raises."""
        import httpx as _httpx

        mock_http_response = MagicMock()
        mock_http_response.content = b"fake-audio-data"
        mock_http_response.raise_for_status = MagicMock()

        mock_http_client = AsyncMock()
        mock_http_client.get = AsyncMock(return_value=mock_http_response)
        mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
        mock_http_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch.object(transcription_service, "_openai_configured", return_value=True),
            patch.object(_httpx, "AsyncClient", return_value=mock_http_client),
            patch(
                "noctusai_lib.integrations.llm.transcribe_audio",
                new=AsyncMock(side_effect=Exception("Rate limit exceeded")),
            ),
        ):
            result = await transcription_service.transcribe_segment(
                audio_url="https://storage.example.com/audio/seg1.ogg",
                segment_number=5,
            )

        assert "Erro na transcrição" in result
        assert "5" in result


# ---------------------------------------------------------------------------
# assemble_transcript
# ---------------------------------------------------------------------------

VIDEO_ROOM = {"id": "vr-001", "appointment_id": "appt-001"}

SEGMENT_INITIAL = {
    "id": "seg-001",
    "video_room_id": "vr-001",
    "segment_number": 1,
    "segment_type": "initial",
    "audio_url": "mock://audio-1.ogg",
    "started_at": "2026-04-01T14:00:00Z",
    "ended_at": "2026-04-01T14:25:00Z",
}

SEGMENT_RESUMED = {
    "id": "seg-002",
    "video_room_id": "vr-001",
    "segment_number": 2,
    "segment_type": "resumed",
    "audio_url": "mock://audio-2.ogg",
    "started_at": "2026-04-01T14:30:00Z",
    "ended_at": "2026-04-01T14:50:00Z",
}

SEGMENT_REOPENED = {
    "id": "seg-003",
    "video_room_id": "vr-001",
    "segment_number": 3,
    "segment_type": "reopened",
    "audio_url": "mock://audio-3.ogg",
    "started_at": "2026-04-01T15:10:00Z",
    "ended_at": "2026-04-01T15:30:00Z",
}


def _seed_room_and_segments(db, segments):
    """Seed `video_rooms` (single room appt-001 ↔ vr-001) + segments.

    Mirrors the live schema chain: appointments → video_rooms → session_audio_segments.
    Tests that only care about transcription assembly use this helper to avoid
    repeating both seeds. Co-located here (not in the seed-lib) until N≥3 across
    the platform — recurrence-rule trigger.
    """
    db.set_table_data("video_rooms", [VIDEO_ROOM])
    db.set_table_data("session_audio_segments", segments)


class TestAssembleTranscript:
    @pytest.mark.asyncio
    async def test_no_segments(self):
        """Returns placeholder when no audio segments found."""
        db = MockSupabaseClient()
        db.set_table_data("session_audio_segments", [])
        result = await transcription_service.assemble_transcript("appt-001", db)
        assert "Nenhum áudio gravado" in result

    @pytest.mark.asyncio
    async def test_single_segment(self):
        """Pattern 1 (DI): pass `transcribe_segment_fn` instead of patching
        the module-level helper. Real `assemble_transcript` runs end-to-end
        against MockSupabase + the fake transcriber."""
        db = MockSupabaseClient()
        _seed_room_and_segments(db, [SEGMENT_INITIAL])

        transcribe_fn = AsyncMock(return_value="Texto do segmento 1.")
        result = await transcription_service.assemble_transcript(
            "appt-001", db, transcribe_segment_fn=transcribe_fn,
        )

        assert "Texto do segmento 1." in result

    @pytest.mark.asyncio
    async def test_multiple_segments_with_pause_marker(self):
        """Inserts pause/resume markers between regular segments."""
        db = MockSupabaseClient()
        _seed_room_and_segments(db, [SEGMENT_INITIAL, SEGMENT_RESUMED])

        async def transcribe_fn(url, num, **kwargs):
            return f"Texto segmento {num}."

        result = await transcription_service.assemble_transcript(
            "appt-001", db, transcribe_segment_fn=transcribe_fn,
        )

        assert "pausada" in result
        assert "retomada" in result
        assert "Texto segmento 1." in result
        assert "Texto segmento 2." in result

    @pytest.mark.asyncio
    async def test_reopened_segment_marker(self):
        """Inserts reopen marker for reopened segments."""
        db = MockSupabaseClient()
        _seed_room_and_segments(db, [SEGMENT_INITIAL, SEGMENT_REOPENED])

        async def transcribe_fn(url, num, **kwargs):
            return f"Texto segmento {num}."

        result = await transcription_service.assemble_transcript(
            "appt-001", db, transcribe_segment_fn=transcribe_fn,
        )

        assert "reaberta" in result

    @pytest.mark.asyncio
    async def test_segment_without_audio_url(self):
        """Handles segment with no audio URL gracefully."""
        db = MockSupabaseClient()
        no_audio_segment = {**SEGMENT_INITIAL, "audio_url": None, "recording_url": None}
        _seed_room_and_segments(db, [no_audio_segment])

        result = await transcription_service.assemble_transcript("appt-001", db)
        assert "não disponível" in result

    @pytest.mark.asyncio
    async def test_uses_recording_url_fallback(self):
        """Falls back to recording_url if audio_url is missing."""
        db = MockSupabaseClient()
        fallback_segment = {
            **SEGMENT_INITIAL,
            "audio_url": None,
            "recording_url": "mock://fallback.ogg",
        }
        _seed_room_and_segments(db, [fallback_segment])

        transcribe_fn = AsyncMock(return_value="Fallback transcription.")
        result = await transcription_service.assemble_transcript(
            "appt-001", db, transcribe_segment_fn=transcribe_fn,
        )

        assert "Fallback transcription." in result
