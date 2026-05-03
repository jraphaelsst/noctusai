"""``llm.vision.*`` — image analysis via the active LLM provider."""

from __future__ import annotations


def register_all(server) -> None:
    from . import analyze

    analyze.register(server)


__all__ = ["register_all"]
