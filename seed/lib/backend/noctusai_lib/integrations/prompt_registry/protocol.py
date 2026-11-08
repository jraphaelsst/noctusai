"""The registry port. Sync (Real is PostgREST); async callers go through ``anyio.to_thread``."""
from __future__ import annotations

from typing import Optional, Protocol
from uuid import UUID

from .types import ChamadaMedida, PromptEntry

__all__ = ["PromptRegistry"]


class PromptRegistry(Protocol):
    def listar(self) -> list[PromptEntry]: ...

    def obter(self, chave: str) -> PromptEntry:
        """Raises :class:`ChaveNaoEncontrada`."""
        ...

    def atualizar(
        self, chave: str, *, prompt: Optional[str] = None, modelo: Optional[str] = None,
        vendor: Optional[str] = None, actor: Optional[UUID] = None,
    ) -> PromptEntry:
        """Raises :class:`ChaveNaoEncontrada`."""
        ...

    def registrar_chamada(self, chamada: ChamadaMedida) -> None: ...

    def estatisticas(self, chave: str) -> list[dict]: ...
