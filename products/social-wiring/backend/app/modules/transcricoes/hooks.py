"""Completion-hook registry keyed by ``contexto_tipo`` (transcription-contract.md).

A consumer module registers, per context type, how to (1) validate a
``contexto_ref`` at submit time (ownership — a user must not be able to point a
recording at someone else's record) and (2) apply the finished transcript.
``aplicar`` runs EXACTLY once per transcription: the worker claims
``hook_aplicado_em`` atomically before calling it and releases the claim if it
raises, so a retry re-runs it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

#: ``validar(db, org_id, user_id, contexto_ref)`` raises ``TranscricaoErro`` (404
#: for a foreign / unknown ref) when the ref is not usable by this caller.
Validar = Callable[[Any, str, str, str], None]
#: ``aplicar(db, row)`` — ``row`` is the finished ``transcricoes`` row.
Aplicar = Callable[[Any, dict], None]


@dataclass(frozen=True)
class ContextoHandler:
    validar: Validar
    aplicar: Aplicar


_REGISTRY: dict[str, ContextoHandler] = {}


def register_contexto(tipo: str, *, validar: Validar, aplicar: Aplicar) -> None:
    """Idempotent: re-registering a type replaces the handler."""
    _REGISTRY[tipo] = ContextoHandler(validar=validar, aplicar=aplicar)


def get_contexto(tipo: str) -> ContextoHandler | None:
    return _REGISTRY.get(tipo)


def registered_tipos() -> list[str]:
    return sorted(_REGISTRY)
