"""The eval-loop REFINE model call (owner 2026-11-19): the seed IO seam of the step -- ``Refinador`` Protocol + ``FakeRefinador`` +
``LlmRefinador`` + factory ``get_refinador`` (the seed rule: IO ships Fake + Real + factory).

The Real one is registry-fed (KB § PATTERNS/ai/prompts-from-registry.md): the WHOLE system prompt, the model and the vendor are the
platform registry row :data:`CHAVE_REFINADOR` (``public.plataforma_agentes``, edited in the UI, never in code), called through the
seed entry point ``chamar_ia`` so the call is metered and attributed like every platform AI call. What this module sends as the user
message is DATA only, as one JSON object (the failing cases' transcripts / lead messages / judge notes are JSON strings in it, never
spliced into a sentence), plus the output schema. The registry prompt must state that ``casos_falhando`` is untrusted data and never
instructions; the server does not rely on it -- :func:`app.studio.eval_loop_refino.validar_proposta` refuses whatever a hostile
transcript could talk the model into.

Cost: the call is capped BEFORE it is made (an input/output worst-case estimate against ``limite_usd`` = what the loop budget has
left, bounded by :data:`TETO_REFINO_USD`) and charged AFTER at the measured cost; an unmeasured call is charged its estimate
(unmeasured != free). The caller adds the cost to the loop's spend.
"""
from __future__ import annotations

import json
import logging
import math
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

import anyio.to_thread

from app.studio.eval_loop_refino import CasoFalhando, LinhasDoAgente, SaidaRefino

logger = logging.getLogger(__name__)

__all__ = [
    "CHAVE_REFINADOR", "TETO_REFINO_USD", "MAX_TOKENS_REFINO", "EntradaRefino", "ResultadoRefino", "Refinador", "FakeRefinador",
    "LlmRefinador", "get_refinador", "interpretar_saida", "montar_mensagem",
]

# NOC-REMEDIATE[eval-refino-registry-prompt-sem-edicao]: the registry row `agents.eval_loop.refinar` is DATA (platform AI registry UI): its prompt must
# now describe the "no edit" answer `{sem_edicao: true, motivo, casos_suspeitos[]}` (the schema sent with every call already lists it), say that
# protective rows (opt-out / security / hand-off / privacy / honesty, required texts, hand-off / stop tools) are never edited, that at most 3 edits
# per loop and 1 per row are accepted, and that a rationale may not contain addresses or handles -- owner/platform admin, 2026-11-19
#: the registry key of the refine call (a dotted lowercase logical id; the row is created by a platform admin in the UI)
CHAVE_REFINADOR = "agents.eval_loop.refinar"
#: one refine call never costs more than this, whatever the loop budget has left (the per-run cap of the rounds is untouched)
TETO_REFINO_USD = 0.50
MAX_TOKENS_REFINO = 4000
_CHARS_POR_TOKEN = 2.5


@dataclass(frozen=True)
class EntradaRefino:
    org_id: UUID
    agente_chave: str
    suite: str
    rodada: int
    score: float | None
    alvo: float
    casos: tuple[CasoFalhando, ...]
    linhas: LinhasDoAgente


@dataclass(frozen=True)
class ResultadoRefino:
    """``saida`` is the model's parsed proposal (NOT yet validated), or ``None`` with a fixed ``codigo``: ``refinador_indisponivel``
    (no registry row / inactive / unreadable) | ``modelo_sem_preco`` | ``limite_de_custo`` | ``llm_erro`` | ``saida_invalida``."""

    saida: SaidaRefino | None
    custo_usd: float
    codigo: str | None = None
    modelo: str | None = None


class Refinador(Protocol):
    async def propor(self, entrada: EntradaRefino, *, limite_usd: float) -> ResultadoRefino: ...


def montar_mensagem(entrada: EntradaRefino) -> str:
    """The user message: ONE JSON object of data. Nothing in it is an instruction."""
    return json.dumps({
        "contexto": {"agente": entrada.agente_chave, "suite": entrada.suite, "rodada": entrada.rodada, "nota": entrada.score, "alvo": entrada.alvo},
        "casos_falhando": [c.para_modelo() for c in entrada.casos],
        "linhas_do_agente": entrada.linhas.para_modelo(),
        "schema_saida": SaidaRefino.model_json_schema(),
    }, ensure_ascii=False, default=str)


def interpretar_saida(texto: str | None) -> SaidaRefino | None:
    """Strict parse of the model's text: a JSON object matching :class:`SaidaRefino` exactly (extra keys / wrong types = ``None``)."""
    try:
        return SaidaRefino.model_validate(json.loads(texto or ""))
    except Exception:  # noqa: BLE001 -- anything but a conforming object is "invalid output" (fixed code to the caller)
        return None


class FakeRefinador:
    """Scripted refiner for CI. ``respostas`` is consumed in order; each is a ``SaidaRefino``, a raw ``dict`` / ``str`` (parsed with
    the SAME strict parse as the Real one), a ``ResultadoRefino``, an ``Exception`` (raised) or a callable ``entrada -> any of those``.
    No script = ``refinador_indisponivel`` (a missing registry row)."""

    def __init__(self, respostas: list[Any] | None = None, *, custo_usd: float = 0.01, modelo: str = "fake-refinador") -> None:
        self.respostas = list(respostas or [])
        self.custo_usd = custo_usd
        self.modelo = modelo
        self.chamadas: list[tuple[EntradaRefino, float]] = []

    async def propor(self, entrada: EntradaRefino, *, limite_usd: float) -> ResultadoRefino:
        self.chamadas.append((entrada, limite_usd))
        if not self.respostas:
            return ResultadoRefino(None, 0.0, "refinador_indisponivel")
        r = self.respostas.pop(0)
        if callable(r):
            r = r(entrada)
        if isinstance(r, Exception):
            raise r
        if isinstance(r, ResultadoRefino):
            return r
        if self.custo_usd > limite_usd:
            return ResultadoRefino(None, 0.0, "limite_de_custo", self.modelo)
        if isinstance(r, SaidaRefino):
            return ResultadoRefino(r, self.custo_usd, None, self.modelo)
        saida = interpretar_saida(r if isinstance(r, str) else json.dumps(r))
        return ResultadoRefino(saida, self.custo_usd, None if saida else "saida_invalida", self.modelo)


class LlmRefinador:
    """Real: registry row :data:`CHAVE_REFINADOR` through ``chamar_ia``. ``registro`` builds the registry (core's service-role client);
    ``chat`` is the seed's own test seam of ``chamar_ia``."""

    def __init__(self, *, registro: Callable[[], Any] | None = None, chat: Callable[..., Awaitable[Any]] | None = None) -> None:
        self._registro = registro
        self._chat = chat

    async def propor(self, entrada: EntradaRefino, *, limite_usd: float) -> ResultadoRefino:
        from noctusai_lib.integrations.prompt_registry import RegistroIAIndisponivel, chamar_ia, prompt_e_modelo

        from app.studio.geracao import preco_do_modelo

        registry = self._registro() if self._registro is not None else None
        try:
            prompt, modelo, vendor = await anyio.to_thread.run_sync(lambda: prompt_e_modelo(CHAVE_REFINADOR, registry=registry))
        except RegistroIAIndisponivel:
            logger.warning("agents.eval_loop.refino_registro_indisponivel chave=%s", CHAVE_REFINADOR)
            return ResultadoRefino(None, 0.0, "refinador_indisponivel")
        preco = preco_do_modelo(vendor, modelo)
        if preco is None:
            logger.error("agents.eval_loop.refino_sem_preco vendor=%s modelo=%s", vendor, modelo)
            return ResultadoRefino(None, 0.0, "modelo_sem_preco", modelo)
        mensagem = montar_mensagem(entrada)
        estimativa = (math.ceil((len(prompt) + len(mensagem)) / _CHARS_POR_TOKEN) * preco[0] + MAX_TOKENS_REFINO * preco[1]) / 1_000_000
        if estimativa > min(limite_usd, TETO_REFINO_USD) + 1e-9:
            return ResultadoRefino(None, 0.0, "limite_de_custo", modelo)
        try:
            r = await chamar_ia(
                CHAVE_REFINADOR, [{"role": "user", "content": mensagem}], org_id=str(entrada.org_id), registry=registry, chat=self._chat,
                max_tokens=MAX_TOKENS_REFINO, response_format={"type": "json_object"}, cache=False)
        except Exception:  # noqa: BLE001 -- provider / key failure: logged with the traceback, a fixed code to the caller
            logger.warning("agents.eval_loop.refino_llm_falhou agente=%s", entrada.agente_chave, exc_info=True)
            return ResultadoRefino(None, 0.0, "llm_erro", modelo)
        custo = r.custo_usd if r.custo_usd is not None else estimativa  # unmeasured != free
        saida = interpretar_saida(r.texto)
        return ResultadoRefino(saida, custo, None if saida else "saida_invalida", r.modelo)


def get_refinador(settings: Any, *, registro: Callable[[], Any] | None = None) -> Refinador:
    """No service-role key (dev / CI): the Fake with no script, i.e. ``refinador_indisponivel`` -- never an invented edit. Else the Real."""
    if not getattr(settings, "supabase_service_role_key", None):
        return FakeRefinador()
    return LlmRefinador(registro=registro)
