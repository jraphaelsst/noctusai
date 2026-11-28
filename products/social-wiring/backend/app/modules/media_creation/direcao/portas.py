"""The four seams where the OPEN decisions plug in (project ``diretor-edicao-reels``, contract section 5).

Each is a Protocol. The skeleton ships ONLY Fakes (:mod:`fakes`); the factory refuses until the owner decides the Real ones
(:mod:`fabrica`). A port never sees the DB, the storage client or the job runner: it receives the typed values of
:mod:`tipos` and returns them, so replacing a Fake by a Real changes no stage, no event and no test of the flow.

Ports are synchronous and blocking (they may call a vendor or a renderer); the handlers run them in a thread.
Anything a port reports about cost / units is MEASURED or ``None`` -- never an estimate (``estimar_usd`` is the one
labelled pre-flight ceiling, checked against the org quota before the stage runs).
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, Protocol, runtime_checkable

from app.modules.media_creation.direcao.tipos import EntradaCongelada, EstiloRef, MidiaGerada, Montagem, PlanoDeCenas


@runtime_checkable
class ResolvedorDeEstilo(Protocol):
    """Which approved style ("estilo"/preset) this run uses. OPEN: where styles live, who approves one, how one is chosen
    per post / org / format (owner decisions D2, D3)."""

    def resolver(self, entrada: EntradaCongelada) -> EstiloRef: ...


@runtime_checkable
class PlanejadorDeCenas(Protocol):
    """Scene composition and sequencing, settings, camera, transitions, the narration<->scene<->graphics relationship: the
    STORYTELLING decision (owner decision D4). It must anchor by word id and add no text (the validator enforces both)."""

    def planejar(self, entrada: EntradaCongelada, estilo: EstiloRef) -> PlanoDeCenas: ...


@runtime_checkable
class GeradorDeMidia(Protocol):
    """Produces the assets the plan calls for (voice, visuals...). OPEN: vendor / mechanism and its consent + quota rules
    (owner decision D5). ``estimar_usd`` is the pre-flight ceiling for the org quota (``None`` = no vendor spend)."""

    def estimar_usd(self, plano: PlanoDeCenas) -> Optional[Decimal]: ...

    def gerar(self, entrada: EntradaCongelada, plano: PlanoDeCenas) -> MidiaGerada: ...


@runtime_checkable
class Montador(Protocol):
    """Assembles and renders the final file and MEASURES it (on the encoded output, never on inputs). OPEN: the
    assembly / render mechanism (owner decision D6)."""

    def montar(self, entrada: EntradaCongelada, plano: PlanoDeCenas, midia: MidiaGerada) -> Montagem: ...


@dataclass(frozen=True)
class Adaptadores:
    """The four seams, bundled: what the handlers receive (built by :mod:`fabrica`, or by a test)."""

    resolvedor: ResolvedorDeEstilo
    planejador: PlanejadorDeCenas
    gerador: GeradorDeMidia
    montador: Montador


class DirecaoError(Exception):
    """Coded failure of a port. ``codigo`` is stable; the message never carries script text."""

    codigo = "direcao_erro"

    def __init__(self, message: str = "", *, codigo: Optional[str] = None, retryable: bool = False) -> None:
        super().__init__(message or (codigo or self.codigo))
        if codigo:
            self.codigo = codigo
        self.retryable = retryable


class DecisaoPendente(DirecaoError):
    """The Real adapter for this seam is an open owner decision: the factory refuses instead of degrading to a Fake."""

    codigo = "direcao_decisao_pendente"


__all__ = [
    "Adaptadores", "DecisaoPendente", "DirecaoError", "GeradorDeMidia", "Montador", "PlanejadorDeCenas", "ResolvedorDeEstilo",
]
