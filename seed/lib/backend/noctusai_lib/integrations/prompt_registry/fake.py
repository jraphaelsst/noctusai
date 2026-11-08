"""In-memory :class:`PromptRegistry` for tests and dev."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from typing import Iterable, Optional
from uuid import UUID

from .types import ESTATISTICAS_JANELA, ChamadaMedida, ChaveNaoEncontrada, PromptEntry, calcular_estatisticas

__all__ = ["FakePromptRegistry"]


class FakePromptRegistry:
    def __init__(self, rows: Optional[Iterable[PromptEntry]] = None) -> None:
        self._rows: dict[str, PromptEntry] = {r.chave: r for r in rows or []}
        #: Set to an exception to simulate the registry being unreadable.
        self.falha: Optional[Exception] = None
        self.leituras = 0
        self.chamadas: list[ChamadaMedida] = []

    def listar(self) -> list[PromptEntry]:
        if self.falha is not None:
            raise self.falha
        return sorted(self._rows.values(), key=lambda r: r.chave)

    def obter(self, chave: str) -> PromptEntry:
        if self.falha is not None:
            raise self.falha
        self.leituras += 1
        try:
            return self._rows[chave]
        except KeyError:
            raise ChaveNaoEncontrada(chave) from None

    def atualizar(
        self, chave: str, *, prompt: Optional[str] = None, modelo: Optional[str] = None,
        vendor: Optional[str] = None, actor: Optional[UUID] = None,
    ) -> PromptEntry:
        atual = self.obter(chave)
        novo = replace(
            atual,
            vendor=atual.vendor if vendor is None else vendor,
            prompt=atual.prompt if prompt is None else prompt,
            modelo=atual.modelo if modelo is None else modelo,
            atualizado_em=datetime.now(timezone.utc), atualizado_por=actor,
        )
        self._rows[chave] = novo
        return novo

    def registrar_chamada(self, chamada: ChamadaMedida) -> None:
        if self.falha is not None:
            raise self.falha
        self.chamadas.append(chamada)

    def estatisticas(self, chave: str) -> list[dict]:
        return calcular_estatisticas([vars(c) for c in self.chamadas if c.chave == chave][-ESTATISTICAS_JANELA:])
