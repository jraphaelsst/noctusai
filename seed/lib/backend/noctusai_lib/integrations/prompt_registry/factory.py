"""Factory + process-wide configuration of the registry."""
from __future__ import annotations

import sys
from typing import Any, Callable, Optional

from .protocol import PromptRegistry
from .real import SupabasePromptRegistry
from .types import RegistroIAIndisponivel

__all__ = ["configure_prompt_registry", "get_prompt_registry", "make_prompt_registry"]

_active: Optional[PromptRegistry] = None


def make_prompt_registry(core_client_factory: Callable[[], Any]) -> PromptRegistry:
    """The Real registry over a service-role ``public``-schema client factory (``DatabaseModule.get_core_client``).
    There is no implicit Fake: tests construct ``FakePromptRegistry`` and :func:`configure_prompt_registry` it."""
    if core_client_factory is None:
        raise ValueError("make_prompt_registry needs a service-role core client factory")
    return SupabasePromptRegistry(core_client_factory)


def configure_prompt_registry(registry: Optional[PromptRegistry]) -> None:
    """Install the process-wide registry (a product calls this once at startup; tests call it with a Fake / None)."""
    global _active
    _active = registry


def get_prompt_registry() -> PromptRegistry:
    """The configured registry. Unconfigured is a loud error, never a silent default."""
    if _active is None:
        raise RegistroIAIndisponivel(
            "no prompt registry configured: call configure_prompt_registry(make_prompt_registry(get_core_client))"
            + (" (pytest: configure a FakePromptRegistry)" if "pytest" in sys.modules else "")
        )
    return _active
