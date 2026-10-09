"""Self-hosted transcription worker (the `noctus-transcriber` engine).

Runs ONLY inside the transcriber container (`deploy/services/transcriber/`);
products never import it. The optional extra `noctusai-lib[transcription-local]`
carries faster-whisper / numpy so no product image installs ctranslate2.

Importing this package is cheap: `faster_whisper` is imported lazily by
`FasterWhisperEngine.load()` only.

Contract: products/social-wiring/projects/core-studio/specs/transcription-contract.md
"""

from noctusai_lib.integrations.transcription.server.app import create_app
from noctusai_lib.integrations.transcription.server.engine import (
    EngineResult,
    EngineTimeout,
    FasterWhisperEngine,
    TranscriptionEngine,
)

__all__ = [
    "create_app",
    "EngineResult",
    "EngineTimeout",
    "FasterWhisperEngine",
    "TranscriptionEngine",
]
