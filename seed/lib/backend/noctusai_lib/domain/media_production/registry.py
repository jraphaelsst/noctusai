"""Step handler registry."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from noctusai_lib.domain.media_production.types import StepContext, StepResult

StepHandler = Callable[[StepContext], Awaitable[StepResult]]


class StepRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, StepHandler] = {}

    def register_step(self, nome: str, handler: StepHandler) -> None:
        if nome in self._handlers:
            raise ValueError(f"step handler {nome!r} already registered")
        self._handlers[nome] = handler

    def get(self, nome: str) -> StepHandler | None:
        return self._handlers.get(nome)


_default = StepRegistry()


def register_step(nome: str, handler: StepHandler) -> None:
    """Register on the process-wide default registry."""
    _default.register_step(nome, handler)


def default_registry() -> StepRegistry:
    return _default
