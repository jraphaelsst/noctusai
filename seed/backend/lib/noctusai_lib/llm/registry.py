"""
Provider registry — maps provider name (`"openai"`, `"anthropic"`, ...) to the
class implementing the `LLMProvider` protocol.

Explicit registration only: each provider module calls `register(name, cls)`
at import time. No dynamic discovery, no reflection — if a provider isn't
imported, it isn't available.

Phase 2 adds the actual provider classes and their registrations. Phase 1
ships the registry scaffolding so everything that depends on it has a
stable API.
"""
from __future__ import annotations

from typing import Type

from noctusai_lib.llm.providers.base import LLMProvider

_PROVIDERS: dict[str, Type[LLMProvider]] = {}


def register(name: str, cls: Type[LLMProvider]) -> None:
    """Register a provider class under a name.

    Safe to call multiple times with the same name — the last registration
    wins. This lets tests swap in a FakeProvider without tearing down
    anything.
    """
    _PROVIDERS[name] = cls


def get_provider_class(name: str) -> Type[LLMProvider]:
    """Look up a registered provider class by name. Raises KeyError if absent."""
    if name not in _PROVIDERS:
        raise KeyError(
            f"Provider {name!r} not registered. "
            f"Known providers: {sorted(_PROVIDERS) or '<none yet — Phase 2 adds them>'}"
        )
    return _PROVIDERS[name]


def list_providers() -> list[str]:
    """All currently registered provider names (sorted)."""
    return sorted(_PROVIDERS)


def _reset_for_testing() -> None:
    """Test-only hook to clear the registry between test cases."""
    _PROVIDERS.clear()
