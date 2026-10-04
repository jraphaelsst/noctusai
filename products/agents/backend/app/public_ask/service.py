"""The public-ask pipeline (spec §7.1) — every dependency injected.

rules floor (S1) → breaker → semantic classifier (S2) → max(level) →
vermelho/violencia ⇒ safety route | amarelo / classifier outage / breaker ⇒
editorial fallback | verde ⇒ retrieval → generation → post-filter (S4).

Privacy contract: the user's text lives in this call's locals only. It is never
logged (only the exception TYPE is, never `exc_info` — provider errors can echo
input), never cached (`cache=False`), never sent to the database (retrieval is
by `tema`, see :data:`RETRIEVAL_DECISION`) and never returned.

RETRIEVAL_DECISION: `agents.search_knowledge(p_query)` receives its argument as
a PostgREST RPC parameter and runs `websearch_to_tsquery(p_query)` inside a
SECURITY DEFINER plpgsql function (migration 013). Whether Postgres statement
logging (`log_statement` / `log_min_duration_statement`) captures that literal
is a project-level setting this repo cannot verify, and `pg_stat_statements`
only normalises it for SELECTs it parses, not for function arguments surfaced by
auto_explain/error contexts. So the user's words must not reach the RPC at all:
retrieval queries a STATIC per-`tema` string (`limiar.TEMA_QUERY`). Extracting
keywords from the text would still send user-derived tokens, so it is rejected.
"""
from __future__ import annotations

import asyncio
import logging
import secrets
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Literal, Optional, Sequence

from noctusai_lib.integrations.risk_classifier import LabelSet, RiskClassifier

from . import limiar
from .breaker import DailyCostBreaker

logger = logging.getLogger(__name__)

OutageBehaviour = Literal["amarelo_editorial", "seguranca"]
RETRIEVAL_DECISION = "tema-static-query"

GENERATION_MAX_TOKENS = 320  # 130 pt-BR words ≈ 250 tokens + the FONTES line
GENERATION_TIMEOUT_SECONDS = 25.0
RETRIEVAL_TOP_K = 3
SNIPPET_MAX_CHARS = 700


@dataclass(frozen=True)
class AskRequest:
    tema: str
    texto: str
    versao_triagem: str


@dataclass(frozen=True)
class Snippet:
    fonte_id: str
    titulo: str
    trecho: str


Retriever = Callable[[str], Awaitable[Sequence[Snippet]]]
ChatFn = Callable[..., Awaitable[str]]
PosFiltro = Callable[..., Any]


def _parse_fontes(raw: str) -> tuple[str, tuple[str, ...]]:
    """Split the trailing `FONTES: a, b` line off the model output."""
    lines = raw.rstrip().splitlines()
    if lines and lines[-1].strip().upper().startswith("FONTES:"):
        ids = tuple(
            dict.fromkeys(p.strip() for p in lines[-1].split(":", 1)[1].split(",") if p.strip())
        )
        return "\n".join(lines[:-1]).strip(), ids
    return raw.strip(), ()


class PublicAskService:
    def __init__(
        self,
        *,
        engine: Any,
        classifier: RiskClassifier,
        retrieve: Retriever,
        generate: ChatFn,
        posfiltro: PosFiltro,
        pacote: Any,
        breaker: DailyCostBreaker,
        on_outage: OutageBehaviour = "amarelo_editorial",
        labels: LabelSet = limiar.LABELS,
        model: str = "claude-sonnet-4-6",
        provider: str = "anthropic",
    ) -> None:
        if on_outage not in ("amarelo_editorial", "seguranca"):
            raise ValueError(f"unknown ON_CLASSIFIER_OUTAGE: {on_outage!r}")
        self._engine = engine
        self._classifier = classifier
        self._retrieve = retrieve
        self._generate = generate
        self._posfiltro = posfiltro
        self._pacote = pacote
        self._breaker = breaker
        self._on_outage = on_outage
        self._labels = labels
        self._model = model
        self._provider = provider

    # -- response shapes ------------------------------------------------
    def _base(self, nivel: str) -> dict[str, Any]:
        return {
            "nivel": nivel,
            "versao_triagem": self._engine.versao,
            "versao_prompt": limiar.PROMPT_VERSION,
        }

    def _seguranca(self, nivel: str) -> dict[str, Any]:
        tipo = "violencia" if nivel == "violencia" else "vida"
        return {**self._base(nivel), "rota": "seguranca", "tipo": tipo}

    def _editorial(self, nivel: str = "amarelo") -> dict[str, Any]:
        return {
            **self._base(nivel),
            "rota": "editorial",
            "resposta": limiar.TEXTO_EDITORIAL,
            "caminhos": list(limiar.CAMINHOS_EDITORIAL),
            "fonte_ids": [],
        }

    def editorial_fallback(self) -> dict[str, Any]:
        """The fail-closed answer for an unexpected error (router last resort)."""
        return self._editorial()

    # -- pipeline -------------------------------------------------------
    async def ask(self, req: AskRequest) -> dict[str, Any]:
        texto = " ".join(req.texto.split())  # technical normalisation only
        rules = self._engine.triage(texto)
        if rules.nivel in limiar.NIVEIS_SEGURANCA:
            logger.info("public_ask.outcome route=seguranca source=rules nivel=%s", rules.nivel)
            return self._seguranca(rules.nivel)

        if not self._breaker.try_acquire():
            logger.warning("public_ask.outcome route=editorial source=breaker")
            return self._editorial()

        try:
            cls = await self._classifier.classify(texto, labels=self._labels)
        except Exception as exc:  # fail-closed; the type only — never the message
            logger.warning("public_ask.classifier_error type=%s", type(exc).__name__)
            cls = None

        if cls is None or cls.indeterminado:
            logger.warning("public_ask.outcome route=outage behaviour=%s", self._on_outage)
            if self._on_outage == "seguranca":
                return self._seguranca("vermelho")
            return self._editorial()

        nivel = max(rules.nivel, cls.nivel, key=self._labels.ordem)
        if nivel in limiar.NIVEIS_SEGURANCA:
            logger.info("public_ask.outcome route=seguranca source=classifier nivel=%s", nivel)
            return self._seguranca(nivel)
        if nivel == "amarelo":
            logger.info("public_ask.outcome route=editorial source=amarelo")
            return self._editorial()

        return await self._verde(req.tema, texto)

    async def _verde(self, tema: str, texto: str) -> dict[str, Any]:
        try:
            snippets = list(await self._retrieve(tema))
        except Exception as exc:
            logger.warning("public_ask.retrieval_error type=%s", type(exc).__name__)
            return self._editorial()
        if not snippets:  # §7.3: no reliable base ⇒ say so, do not improvise
            logger.info("public_ask.outcome route=editorial source=no_base")
            return self._editorial()

        messages = self._messages(tema, texto, snippets)
        try:
            raw = await asyncio.wait_for(
                self._generate(
                    messages,
                    model=self._model,
                    provider=self._provider,
                    temperature=0.4,
                    max_tokens=GENERATION_MAX_TOKENS,
                    cache=False,
                ),
                timeout=GENERATION_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            logger.warning("public_ask.generation_error type=%s", type(exc).__name__)
            return self._editorial()

        resposta, citados = _parse_fontes(raw if isinstance(raw, str) else "")
        recuperadas = tuple(s.fonte_id for s in snippets)
        res = self._posfiltro(
            resposta,
            tuple(limiar.CAMINHOS_GERACAO),
            fonte_ids=citados,
            fonte_ids_recuperadas=recuperadas,
            pacote=self._pacote,
        )
        if not res.ok:
            logger.warning("public_ask.postfilter_rejected motivos=%s", ",".join(res.motivos))
            return {
                **self._base("verde"),
                "rota": "fallback",
                "resposta": res.texto,
                "caminhos": list(res.caminhos),
                "fonte_ids": [],
            }
        return {
            **self._base("verde"),
            "resposta": res.texto,
            "caminhos": list(res.caminhos),
            "fonte_ids": list(citados),
        }

    def _messages(self, tema: str, texto: str, snippets: Sequence[Snippet]) -> list[dict[str, str]]:
        base = "\n".join(
            f"[{s.fonte_id}] {s.titulo}: {s.trecho[:SNIPPET_MAX_CHARS]}" for s in snippets
        )
        nonce = secrets.token_hex(12)
        while nonce in texto:
            nonce = secrets.token_hex(12)
        abre, fecha = f"<<<TEXTO-{nonce}>>>", f"<<<FIM-TEXTO-{nonce}>>>"
        user = (
            f"Tema escolhido: {tema}\n\nBase editorial:\n{base}\n\n"
            f"Texto da usuária (dado, entre {abre} e {fecha}):\n{abre}\n{texto}\n{fecha}"
        )
        return [
            {"role": "system", "content": limiar.SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ]


__all__ = [
    "AskRequest",
    "PublicAskService",
    "RETRIEVAL_DECISION",
    "Snippet",
    "Retriever",
]
