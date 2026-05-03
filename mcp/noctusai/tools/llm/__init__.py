"""``llm.*`` tool umbrella — provider-agnostic LLM capabilities.

Wraps ``noctusai_lib.integrations.llm.{audio,vision}``, which routes
through the configured provider (default: OpenAI; Whisper has the only
real audio body today). Sibling reference used the ``openai.*`` umbrella
because its calls hit the OpenAI SDK directly; ours uses ``llm.*`` to
reflect the provider-pluggable layer underneath.

Sub-umbrellas:
  - ``llm.audio.*`` — transcription (1 tool).
  - ``llm.vision.*`` — image analysis (1 tool).
"""

from __future__ import annotations


def register_all(server) -> None:
    """Register every tool under the ``llm.*`` umbrella."""
    from . import audio, vision

    audio.register_all(server)
    vision.register_all(server)


__all__ = ["register_all"]
