"""Types — step specs, ledger rows (contract M-B shape), results, errors."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from decimal import Decimal
from typing import Any

# Step statuses (ledger ``status``).
PENDENTE = "pendente"
EXECUTANDO = "executando"
CONCLUIDO = "concluido"
FALHOU = "falhou"
CANCELADO = "cancelado"

CODIGO_COTA = "cota"
CODIGO_CANCELADO = "cancelado"
CODIGO_SEM_HANDLER = "passo_sem_handler"
CODIGO_ERRO_INTERNO = "erro_interno"


class StepError(Exception):
    """A step failed with a coded, user-visible reason (``falhou(codigo)``)."""

    def __init__(self, codigo: str, message: str = "", *, retryable: bool = False) -> None:
        super().__init__(message or codigo)
        self.codigo = codigo
        self.retryable = retryable


class QuotaExceeded(StepError):
    """Pre-flight estimate is over the org quota -> step ``falhou(cota)``."""

    def __init__(self, message: str = "cota mensal excedida") -> None:
        super().__init__(CODIGO_COTA, message)


@dataclass(frozen=True)
class StepSpec:
    """One node of a graph. ``peso`` = expected duration (s), the progress weight."""

    passo: str
    rotulo: str  # pt-BR gerund shown to the user, e.g. "Sintetizando voz"
    depende_de: tuple[str, ...] = ()
    peso: float = 1.0
    estimativa_usd: Decimal | None = None
    entradas: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GraphSpec:
    org_id: str
    post_id: str
    passos: tuple[StepSpec, ...]
    rodada: int = 1

    def __post_init__(self) -> None:
        nomes = [p.passo for p in self.passos]
        if len(set(nomes)) != len(nomes):
            raise ValueError("passo names must be unique within a graph")
        for p in self.passos:
            for d in p.depende_de:
                if d not in nomes:
                    raise ValueError(f"{p.passo!r} depends on unknown step {d!r}")
        pend = {p.passo: set(p.depende_de) for p in self.passos}
        while pend:
            livres = [n for n, d in pend.items() if not d]
            if not livres:
                raise ValueError("graph has a cycle")
            for n in livres:
                del pend[n]
            for d in pend.values():
                d.difference_update(livres)


@dataclass(frozen=True)
class PassoRow:
    """Ledger row of one step run (contract M-B ``cs_criacao_jobs``).

    Unmeasured fields stay ``None`` and are named in ``nao_medido`` -- never
    an estimate."""

    org_id: str
    post_id: str
    rodada: int
    passo: str
    depende_de: tuple[str, ...] = ()
    status: str = PENDENTE
    job_id: str | None = None
    iniciado_em: Any = None
    terminado_em: Any = None
    duracao_s: float | None = None
    cpu_s: float | None = None
    vendor: str | None = None
    modelo: str | None = None
    request_id: str | None = None
    unidades: dict[str, Any] | None = None  # {caracteres, audio_s, video_s, creditos_cobrados}
    custo_usd: Decimal | None = None
    medicoes: dict[str, Any] | None = None  # LUFS, true peak, safe-zone...
    resultado: dict[str, Any] | None = None  # outputs handed to dependents
    erro_codigo: str | None = None
    nao_medido: tuple[str, ...] = ()

    def with_(self, **kw: Any) -> "PassoRow":
        return replace(self, **kw)


@dataclass
class StepResult:
    """What a handler returns: outputs + the measured units (None = not measured)."""

    saida: dict[str, Any] = field(default_factory=dict)
    vendor: str | None = None
    modelo: str | None = None
    request_id: str | None = None
    unidades: dict[str, Any] | None = None
    custo_usd: Decimal | None = None
    medicoes: dict[str, Any] | None = None


class CancelToken:
    def __init__(self) -> None:
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    def raise_if_cancelled(self) -> None:
        if self._cancelled:
            raise StepError(CODIGO_CANCELADO, "criação cancelada")


@dataclass(frozen=True)
class StepContext:
    org_id: str
    post_id: str
    rodada: int
    passo: str
    entradas: dict[str, Any]  # spec inputs + {dep_passo: dep.resultado}
    cancel: CancelToken
