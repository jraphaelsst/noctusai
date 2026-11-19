"""The steps of the criação jobs: label (pt-BR gerund shown on the card), progress weight, and which have a handler.

The ROUTES themselves (which steps, in order, which stages are skipped) are S5's data (:mod:`criacao_rotas`, keyed by
``(formato, modo_producao)``); this table adds what only the worker needs per step name. A route runs automatically only
when EVERY one of its steps has an entry in :data:`PASSOS` and a registered handler -- otherwise it refuses, visibly, with
the coded ``rota_nao_implementada`` (never a half-run graph).
"""
from __future__ import annotations

from dataclasses import dataclass

from noctusai_lib.domain.media_production import StepSpec

from app.modules.media_creation.criacao_rotas import Rota

PASSO_TTS = "tts"
PASSO_RENDER = "render_motion"
PASSO_MUX = "mux"

ROTA_NAO_IMPLEMENTADA = "rota_nao_implementada"
SEM_ROTA = "sem_rota_de_criacao"


@dataclass(frozen=True)
class PassoDef:
    rotulo: str
    #: expected duration in seconds: the progress weight -- a render dominates the bar.
    peso: float


#: Steps that HAVE handlers (``criacao_handlers.build_handlers``). Adding a route's steps here + a handler enables it.
PASSOS: dict[str, PassoDef] = {
    PASSO_TTS: PassoDef("Sintetizando voz", 8),
    PASSO_RENDER: PassoDef("Renderizando vídeo", 90),
    PASSO_MUX: PassoDef("Mixando áudio", 6),
}


def implementada(rota: Rota) -> bool:
    return bool(rota.passos) and all(p in PASSOS for p in rota.passos)


def specs_da_rota(rota: Rota, entradas: dict[str, dict], estimativas: dict[str, object] | None = None) -> tuple[StepSpec, ...]:
    """The seed graph of ``rota``: each step depends on the previous one (the routes are linear job chains)."""
    estimativas = estimativas or {}
    out: list[StepSpec] = []
    anterior: tuple[str, ...] = ()
    for nome in rota.passos:
        d = PASSOS[nome]
        out.append(StepSpec(nome, d.rotulo, anterior, d.peso, estimativas.get(nome), dict(entradas.get(nome) or {})))
        anterior = (nome,)
    return tuple(out)
