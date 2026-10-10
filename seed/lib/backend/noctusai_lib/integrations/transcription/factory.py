"""`make_transcriber()` — backend chosen by `TRANSCRIPTION_BACKEND`."""

from __future__ import annotations

import os
from typing import Optional

from noctusai_lib.integrations.transcription.fake import FakeTranscriber
from noctusai_lib.integrations.transcription.local_whisper_http import LocalWhisperTranscriber
from noctusai_lib.integrations.transcription.openai_whisper import OpenAIWhisperTranscriber
from noctusai_lib.integrations.transcription.types import Transcriber, TranscriptionError
from noctusai_lib.primitives.not_configured import IntegrationNotConfigured

BACKEND_ENV = "TRANSCRIPTION_BACKEND"
URL_ENV = "TRANSCRIBER_URL"
TOKEN_ENV = "TRANSCRIBER_TOKEN"


class TranscriptionNotConfigured(TranscriptionError, IntegrationNotConfigured):
    """Backend unset/unknown or `local_whisper` missing URL/token. Never
    falls back to another backend."""


def make_transcriber(kind: Optional[str] = None, **kwargs) -> Transcriber:
    kind = (kind or os.environ.get(BACKEND_ENV) or "").strip().lower()
    if kind == "fake":
        return FakeTranscriber(**kwargs)
    if kind == "openai":
        return OpenAIWhisperTranscriber(**kwargs)
    if kind == "local_whisper":
        url = os.environ.get(URL_ENV, "").strip()
        token = os.environ.get(TOKEN_ENV, "").strip()
        if not url or not token:
            raise TranscriptionNotConfigured(
                f"{BACKEND_ENV}=local_whisper requires {URL_ENV} and {TOKEN_ENV}"
            )
        return LocalWhisperTranscriber(base_url=url, token=token, **kwargs)
    raise TranscriptionNotConfigured(
        f"{BACKEND_ENV} must be one of local_whisper|openai|fake (got {kind!r})"
    )
