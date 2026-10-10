"""The transcription package (and its server/ subpackage) must import without the
LLM provider SDKs — the self-hosted transcriber image ships neither anthropic nor
openai. Regression for the build-transcriber import smoke failure (2026-10-10)."""
from __future__ import annotations

import subprocess
import sys
import textwrap


def test_transcription_server_imports_with_provider_sdks_blocked():
    code = textwrap.dedent(
        """
        import sys
        for name in ("anthropic", "openai", "google.genai", "google.generativeai"):
            sys.modules[name] = None  # any import of these now raises ImportError
        import noctusai_lib.integrations.transcription
        import noctusai_lib.integrations.transcription.server
        from noctusai_lib.integrations.transcription import make_transcriber, LocalWhisperTranscriber
        print("ok")
        """
    )
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert proc.returncode == 0 and proc.stdout.strip().endswith("ok"), proc.stderr
