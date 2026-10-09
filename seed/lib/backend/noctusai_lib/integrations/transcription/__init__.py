"""Transcription seam — Protocol + Fake + two Real backends + factory.

`make_transcriber()` picks the backend from `TRANSCRIPTION_BACKEND`
(`local_whisper` | `openai` | `fake`); a misconfigured `local_whisper`
raises, it never degrades to OpenAI.
"""

from __future__ import annotations

from noctusai_lib.integrations.transcription.factory import (
    TranscriptionNotConfigured,
    make_transcriber,
)
from noctusai_lib.integrations.transcription.fake import FakeTranscriber
from noctusai_lib.integrations.transcription.local_whisper_http import LocalWhisperTranscriber
from noctusai_lib.integrations.transcription.openai_whisper import OpenAIWhisperTranscriber
from noctusai_lib.integrations.transcription.types import (
    AudioProbe,
    ProbeNotSupported,
    Transcriber,
    TranscriberBusy,
    TranscriberUnavailable,
    TranscriptionError,
    TranscriptionRejected,
    TranscriptResult,
)
from noctusai_lib.integrations.transcription.validation import (
    DEFAULT_LIMITS,
    TranscriptionLimits,
    sniff_container,
)

__all__ = [
    "AudioProbe",
    "DEFAULT_LIMITS",
    "FakeTranscriber",
    "LocalWhisperTranscriber",
    "OpenAIWhisperTranscriber",
    "ProbeNotSupported",
    "Transcriber",
    "TranscriberBusy",
    "TranscriberUnavailable",
    "TranscriptResult",
    "TranscriptionError",
    "TranscriptionLimits",
    "TranscriptionNotConfigured",
    "TranscriptionRejected",
    "make_transcriber",
    "sniff_container",
]
