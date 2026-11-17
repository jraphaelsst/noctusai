"""O3 -- import a client's existing settings into pre-filled onboarding answers.

Input is what an operator pastes or uploads: a JSON object, or lines of ``chave: valor`` (a spec key, a setting id, the
item's number or its title). Output is a proposal, never a write: every recognised line becomes an answer marked
``origem="importado"`` / ``confirmado=False`` that the interviewer shows back for confirmation instead of asking;
every line it cannot place is returned verbatim in ``nao_reconhecidas`` (the interviewer maps those by conversation).
Free-form prose is not guessed at here -- extracting items from prose is the interviewer's job (an LLM, confirmed with
the person), so nothing is inferred silently. Pure, no IO.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from noctusai_lib.primitives.accents import fold_accents

from app.onboarding.checklist import CHECKLIST, Item

__all__ = ["MAX_ENTRADA", "Importacao", "RespostaImportada", "importar"]

#: Same order of magnitude as the biggest spec cap; an import is a paste, not a file store.
MAX_ENTRADA = 60_000


@dataclass(frozen=True)
class RespostaImportada:
    n: int
    valor: Any
    fonte: str  # the key as the client's export named it
    origem: str = "importado"
    confirmado: bool = False


@dataclass
class Importacao:
    preenchidas: list[RespostaImportada] = field(default_factory=list)
    nao_reconhecidas: list[str] = field(default_factory=list)
    conflitos: list[str] = field(default_factory=list)


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", fold_accents(s.casefold())).strip("_")


def _indice() -> dict[str, Item]:
    """Names an item answers to. A spec key shared by several items (the sale/rental knowledge) names none of them: the
    import must not pick one for the client."""
    out: dict[str, Item] = {}
    ambiguos: set[str] = set()
    for i in CHECKLIST:
        for nome in (str(i.n), _norm(i.titulo), i.destino.alvo):
            if nome in out and out[nome] is not i:
                ambiguos.add(nome)
            out[nome] = i
    for nome in ambiguos:
        out.pop(nome, None)
    return out


_INDICE = _indice()


def _pares(texto: str) -> tuple[list[tuple[str, Any]], list[str]]:
    """``(pairs, loose lines)`` from a JSON object or ``chave: valor`` lines."""
    s = texto.strip()
    if s.startswith("{"):
        try:
            obj = json.loads(s)
        except ValueError:
            obj = None
        if isinstance(obj, dict):
            return [(str(k), v) for k, v in obj.items()], []
    pares: list[tuple[str, Any]] = []
    soltas: list[str] = []
    for linha in s.splitlines():
        if not linha.strip():
            continue
        chave, sep, valor = linha.partition(":")
        if sep and valor.strip() and len(chave) <= 60:
            pares.append((chave.strip(), valor.strip()))
        else:
            soltas.append(linha.strip())
    return pares, soltas


def importar(texto: str) -> Importacao:
    """Map an export onto checklist items. Two lines for the same item with different values are a conflict (kept out
    of ``preenchidas``, named in ``conflitos``): the interviewer asks which one is right."""
    if len(texto) > MAX_ENTRADA:
        raise ValueError(f"entrada acima de {MAX_ENTRADA} caracteres")
    pares, soltas = _pares(texto)
    res = Importacao(nao_reconhecidas=list(soltas))
    vistas: dict[int, RespostaImportada] = {}
    conflito: set[int] = set()
    for chave, valor in pares:
        item = _INDICE.get(_norm(chave)) or _INDICE.get(chave.strip())
        if item is None or valor in (None, "", [], {}):
            res.nao_reconhecidas.append(f"{chave}: {valor}")
            continue
        if item.n in vistas and vistas[item.n].valor != valor:
            conflito.add(item.n)
        vistas.setdefault(item.n, RespostaImportada(item.n, valor, chave))
    for n, r in sorted(vistas.items()):
        if n in conflito:
            res.conflitos.append(f"item {n}: valores diferentes na importação")
        else:
            res.preenchidas.append(r)
    return res
