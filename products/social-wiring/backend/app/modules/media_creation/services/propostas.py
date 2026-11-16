"""Server-side validation of the chat agent's headline proposals (estruturas-contract.md section 8.5).

PURE parser/validator: no DB access, no writes. UNI-1a persists ``cs_chat_propostas`` +
``cs_chat_proposta_estruturas`` + the events in the same pass that saves the assistant message.
This is the Python port of the FE ``components/geracao/chat/citacoes.ts :: extrairHeadlines`` -- the single
derivation (the FE parser is retired by FE-2) -- extended with the unified-chat citation grammar
``(estrutura #N)`` / ``(estrutura #N + #M [+ #K])``.

What it enforces (the model is never trusted):
- a code outside ``codigos_permitidos`` is dropped (event ``citacao_rejeitada``);
- a code whose Estrutura ``formato`` differs from the principal's (the first valid code) is dropped
  (``formato_misturado``); at most 3 codes per proposta (extras count as ``citacao_rejeitada``);
- a headline left with NO valid code is not a proposta (an uncited numbered line counts as ``citacao_rejeitada``);
- a headline that still matches ``\\[[^\\]]+\\]`` is dropped (``placeholder_remanescente``);
- at most 10 propostas; the ``### Estruturas usadas`` attribution list is never read as headlines.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping
from uuid import UUID

from noctusai_lib.primitives.accents import fold_accents

MAX_PROPOSTAS = 10
MAX_ESTRUTURAS_POR_PROPOSTA = 3
_MIN_CHARS = 5

_ITEM_RE = re.compile(r"^\s*(?:(\d+)[.)]|[-*•])\s+(.*\S)\s*$")
_CITACAO_RE = re.compile(r"\(\s*estrutura\s*#\s*(\d+(?:\s*\+\s*#\s*\d+)*)\s*\)", re.IGNORECASE)
_PLACEHOLDER_RE = re.compile(r"\[[^\]]+\]")
_TAG_FINAL_RE = re.compile(r"\s*\(\s*([^()]{3,40}?)\s*\)\s*[.!?]?\s*$")
_TITULO_RE = re.compile(r"^\s*#{1,6}\s*(.*?)\s*#*\s*$")

#: The attention-trigger names the agent appends in parentheses (BE prompt ``chat_headline.py`` + methodology).
GATILHOS_TAG = (
    "Popularidade/Autoridade", "Recompensa", "Mistério", "Reconhecimento", "Crença", "Disrupção", "Autoridade",
    "Popularidade",
)


def _sem_acento(t: str) -> str:
    return fold_accents(t).lower()


_GATILHOS_NORM = {_sem_acento(g): g for g in GATILHOS_TAG}


@dataclass(frozen=True)
class EstruturaCitavel:
    id: UUID
    codigo: str  # the N shown to the model as "estrutura #N"
    formato: str


@dataclass(frozen=True)
class PropostaValidada:
    ordem: int
    headline: str
    gatilho: str | None
    estrutura_ids: tuple[UUID, ...]  # [0] = principal, len 1..3


@dataclass(frozen=True)
class ResultadoPropostas:
    propostas: tuple[PropostaValidada, ...]
    eventos: tuple[dict, ...]  # {"tipo": "citacao_rejeitada"|"formato_misturado"|"placeholder_remanescente", "contagem": int}


def _tag_final(texto: str) -> tuple[str, str] | None:
    m = _TAG_FINAL_RE.search(texto)
    if not m:
        return None
    nome = _GATILHOS_NORM.get(_sem_acento(m.group(1)))
    return (texto[: m.start()].strip(), nome) if nome else None


def _limpar(texto: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"\*\*|__", "", texto)).strip().strip('"“”').strip()


def extrair_propostas(texto: str, codigos_permitidos: Mapping[str, EstruturaCitavel]) -> ResultadoPropostas:
    rejeitadas = misturadas = placeholders = 0
    propostas: list[PropostaValidada] = []
    vistas: set[str] = set()
    ignorar_secao = False
    for linha in (texto or "").split("\n"):
        titulo = _TITULO_RE.match(linha)
        if titulo:
            ignorar_secao = _sem_acento(titulo.group(1)).startswith("estruturas usadas")
            continue
        m = _ITEM_RE.match(linha)
        if not m or ignorar_secao:
            continue
        numerado, corpo = m.group(1) is not None, m.group(2)
        citacoes = list(_CITACAO_RE.finditer(corpo))
        if not citacoes:
            # an uncited NUMBERED line that reads like a headline is a citation the model forgot; bullets are prose
            limpa = _limpar(corpo)
            if numerado and len(limpa) >= _MIN_CHARS and not limpa.endswith("?") and len(propostas) < MAX_PROPOSTAS:
                rejeitadas += 1
            continue
        if len(propostas) >= MAX_PROPOSTAS:
            continue
        codigos: list[str] = []
        for c in citacoes:
            codigos += re.findall(r"\d+", c.group(1))
        sem_citacao = _CITACAO_RE.sub("", corpo)
        limpa = _limpar(sem_citacao)
        gatilho = None
        tag = _tag_final(limpa)
        if tag and tag[0]:
            limpa, gatilho = _limpar(tag[0]), tag[1]
        if len(limpa) < _MIN_CHARS:
            continue
        # citations: known, same formato as the principal, at most 3
        validos: list[EstruturaCitavel] = []
        for cod in dict.fromkeys(codigos):
            est = codigos_permitidos.get(cod)
            if est is None:
                rejeitadas += 1
            elif validos and est.formato != validos[0].formato:
                misturadas += 1
            elif len(validos) >= MAX_ESTRUTURAS_POR_PROPOSTA:
                rejeitadas += 1
            else:
                validos.append(est)
        if not validos:
            continue
        if _PLACEHOLDER_RE.search(limpa):
            placeholders += 1
            continue
        chave = limpa.casefold()
        if chave in vistas:
            continue
        vistas.add(chave)
        propostas.append(PropostaValidada(
            ordem=len(propostas) + 1, headline=limpa, gatilho=gatilho,
            estrutura_ids=tuple(e.id for e in validos),
        ))
    eventos = tuple(
        {"tipo": tipo, "contagem": n}
        for tipo, n in (("citacao_rejeitada", rejeitadas), ("formato_misturado", misturadas),
                        ("placeholder_remanescente", placeholders))
        if n
    )
    return ResultadoPropostas(propostas=tuple(propostas), eventos=eventos)


__all__ = ["EstruturaCitavel", "PropostaValidada", "ResultadoPropostas", "extrair_propostas", "GATILHOS_TAG"]
