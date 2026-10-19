"""The narrow seam between the eval runner and the REAL channel turn path (Julia v2 A-EVAL).

The runner (``eval_mecanismo``) never imports the turn loop. It talks to an :class:`EvalTurnDriver`:

* input  -- the thread state so far + ONE inbound lead message;
* output -- the reply bubbles, the tool calls, the actions, the resulting qualification estado, the
  handoff and the conformance violations of that turn.

A-RT owns the real adapter (the channel turn path over a provider seam: ``FakeProvider`` scripting tool
calls in CI, the live model only for the publish gate). Until it lands, :class:`FakeEvalTurnDriver` scripts
the outcomes so the runner, the asserts and the gate are fully testable without a model.

Everything that crosses this seam is data about WHAT HAPPENED, never prompt content: the runner reports
codes and tool names, so an eval result cannot leak the compiled prompt (CONTRACT 0.4, IP).
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Protocol, runtime_checkable

__all__ = [
    "ToolCall",
    "Violation",
    "Handoff",
    "Estado",
    "Mensagem",
    "ThreadState",
    "TurnOutcome",
    "EvalTurnDriver",
    "FakeEvalTurnDriver",
    "ScriptExhausted",
    "reiniciar",
    "com_custo",
]


@dataclass(frozen=True)
class ToolCall:
    nome: str
    args: dict[str, Any] = field(default_factory=dict)
    #: ``False`` when the tool refused (E2 gating) -- a refused call still counts as ATTEMPTED.
    ok: bool = True


@dataclass(frozen=True)
class Violation:
    """A conformance violation (``conformidade_violacoes`` row shape, without any content)."""

    regra: str
    detalhe: str = ""


@dataclass(frozen=True)
class Handoff:
    para: str
    #: ``agente`` | ``humano`` | ``papel``
    tipo: str = "humano"


@dataclass(frozen=True)
class Estado:
    """The qualification estado AFTER a turn (cumulative for the thread)."""

    estagio: str | None = None
    #: criterion key -> registered value (the value itself is never asserted on, only the key)
    criterios: dict[str, Any] = field(default_factory=dict)
    #: every offer batch so far, in order: one tuple of imóvel codes per ``oferecer_imoveis`` call
    lotes: tuple[tuple[str, ...], ...] = ()
    #: identity fields still missing (nome, numero, email, rg, cpf); empty tuple => complete
    identificacao_faltando: tuple[str, ...] = ("nome", "numero", "email", "rg", "cpf")
    concluido: bool = False


@dataclass(frozen=True)
class Mensagem:
    role: str  # lead | agente | evento
    texto: str


@dataclass(frozen=True)
class ThreadState:
    """Input state of a turn: the fixture world plus what already happened in the thread."""

    #: fixture imóvel catalogue (synthetic)
    catalogo: tuple[dict[str, Any], ...] = ()
    estado: Estado = field(default_factory=Estado)
    historico: tuple[Mensagem, ...] = ()
    #: fixture knobs the roteiro hands to the driver (agent controls, lead flags, ...)
    fixture: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TurnOutcome:
    bolhas: tuple[str, ...] = ()
    ferramentas: tuple[ToolCall, ...] = ()
    acoes: tuple[str, ...] = ()
    estado: Estado = field(default_factory=Estado)
    handoff: Handoff | None = None
    violacoes: tuple[Violation, ...] = ()
    #: cost of THIS turn in USD (``None`` => unknown; the runner counts it as 0 and reports it)
    custo_usd: float | None = None


@runtime_checkable
class EvalTurnDriver(Protocol):
    #: ``"live"`` (the real model through the real turn path) or ``"fake"`` (scripted). A run is stamped with
    #: it and ONLY a ``live`` run can open the publish gate -- an adapter must not claim ``live`` unless the
    #: live model produced the turns.
    tipo: str

    async def executar_turno(self, thread: ThreadState, mensagem_lead: str) -> TurnOutcome:
        """Run ONE inbound lead message through the real turn path and report what happened."""
        ...


class ScriptExhausted(RuntimeError):
    """The fake driver was asked for more turns than it was scripted for."""


Script = Sequence[TurnOutcome | Callable[[ThreadState, str], TurnOutcome]]


class FakeEvalTurnDriver:
    """Scripted driver: turn N of the CURRENT execution returns ``scripts[execucao][N]``.

    ``scripts`` is a list of per-execution scripts (a single script is reused for every execution when only
    one is given), so a test can make execution 2 of k=3 deviate (pass^k). A script entry may be a
    :class:`TurnOutcome` or a ``(thread, mensagem) -> TurnOutcome`` callable. :meth:`nova_execucao` rewinds the
    turn counter; the runner calls it through :func:`reiniciar` before each execution.
    """

    tipo = "fake"

    def __init__(self, *scripts: Script, erro_no_turno: dict[tuple[int, int], Exception] | None = None) -> None:
        if not scripts:
            raise ValueError("at least one script")
        self._scripts = scripts
        self._execucao = -1
        self._turno = 0
        self._erros = erro_no_turno or {}
        self.mensagens_recebidas: list[list[str]] = []
        self.threads_recebidas: list[ThreadState] = []

    def nova_execucao(self) -> None:
        self._execucao += 1
        self._turno = 0
        self.mensagens_recebidas.append([])

    async def executar_turno(self, thread: ThreadState, mensagem_lead: str) -> TurnOutcome:
        if self._execucao < 0:
            self.nova_execucao()
        exec_i, turno_i = self._execucao, self._turno
        self._turno += 1
        self.mensagens_recebidas[exec_i].append(mensagem_lead)
        self.threads_recebidas.append(thread)
        erro = self._erros.get((exec_i, turno_i))
        if erro is not None:
            raise erro
        script = self._scripts[exec_i] if exec_i < len(self._scripts) else self._scripts[-1]
        if turno_i >= len(script):
            raise ScriptExhausted(f"execucao {exec_i} turno {turno_i}")
        item = script[turno_i]
        return item(thread, mensagem_lead) if callable(item) else item


def reiniciar(driver: Any) -> None:
    """Tell a driver a new execution (a fresh thread) starts; a no-op for drivers without the hook."""
    hook = getattr(driver, "nova_execucao", None)
    if callable(hook):
        hook()


def com_custo(outcome: TurnOutcome, custo_usd: float) -> TurnOutcome:
    return replace(outcome, custo_usd=custo_usd)
