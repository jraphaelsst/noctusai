"""``llm.audio.*`` — audio transcription via the active LLM provider."""

from __future__ import annotations


def register_all(server) -> None:
    from . import transcribe

    transcribe.register(server)


__all__ = ["register_all"]
