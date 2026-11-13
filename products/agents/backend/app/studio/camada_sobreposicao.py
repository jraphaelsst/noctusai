"""Layer overlap: a child section that restates its parent chain (deterministic, no LLM).

A child's ``secoes`` merge with the parent's: a section with the parent's same ``chave`` APPENDS (prose), another key
sits beside it. Nothing stopped a child from writing a second identity, or its own privacy/tone/hand-off section next
to the parent's -- two voices stacked in one prompt, sometimes contradicting each other. This module finds those
collisions from the rows alone; readiness reports them as ADVISORY items (``secao_*``, never blocking).

Three rules, one finding per child section (priority repete > papel > sobrepoe):

* ``secao_repete_pai``    same key as a parent section AND high lexical overlap -> the child restates the parent;
* ``secao_papel_empilhado`` same key as a role the parent owns once (:data:`PAPEIS`) -> a second one is stacked, whatever
  the wording (two identities / two honesty rules);
* ``secao_sobrepoe_pai``  different key but high lexical overlap with a parent section (lexical), or a key naming the
  same topic as a parent key (:data:`TEMAS`, a closed synonym table: ``encaminhamento`` ~ ``transferencia``).

Lexical score = Jaccard of the stop-word-free, accent-stripped unigram sets (:data:`LIMIAR_LEXICAL`). CALIBRATION
(real layers read from prod, counts only): content words alone cannot separate the cross-key collisions of the
personal-assistant layer (unigram Jaccard 0.06-0.17) from healthy layers (sdr-base over the base: 0.10-0.17), so the
cross-key hits of that layer come from the key rules; 0.5 sits above every healthy layer pair (max 0.46) and below
every real restatement found. Contradiction detection between layers needs an LLM and is out of scope (deferred).

Findings carry keys, a score and a code -- never prompt text (the readiness view also rides publish 409 bodies).
"""
from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from noctusai_lib.primitives.accents import fold_accents_ascii

__all__ = ["Achado", "LIMIAR_LEXICAL", "MIN_PALAVRAS", "PAPEIS", "TEMAS", "analisar"]

#: Jaccard of the content-word sets at/above which two sections are said to restate each other.
LIMIAR_LEXICAL = 0.5
#: Sections with fewer content words than this are too short for a lexical judgement (keys rules still apply).
MIN_PALAVRAS = 8
#: Keys of a role a prompt owns ONCE (the agent's identity, its honesty rule): a child section with the same key stacks
#: a second one on the parent's.
PAPEIS = frozenset({"identidade", "honestidade"})
#: Closed synonym groups of section keys naming one topic. A child key and a parent key of the same group collide even
#: when the words differ.
TEMAS: tuple[frozenset[str], ...] = (
    frozenset({"privacidade", "privacidade-lgpd"}),
    frozenset({"estilo", "tom", "tom-e-formato"}),
    frozenset({"encaminhamento", "transferencia", "handoff"}),
)

_STOP = frozenset(
    "a o as os de do da dos das em no na nos nas um uma uns umas e ou que se com por para pra ao aos ele ela eles voce vc "
    "nao so mais mas como ja seu sua seus suas isso essa esse esta este quando sem sobre ate ser estar ter ha foi sao pode "
    "podem deve lhe te me mesmo qualquer cada tambem entre apenas".split()
)


@dataclass(frozen=True)
class Achado:
    codigo: str  # secao_repete_pai | secao_papel_empilhado | secao_sobrepoe_pai
    chave_filho: str
    chave_pai: str
    similaridade: float | None  # lexical score; ``None`` when the finding comes from a key rule alone
    motivo: str  # lexical | papel | tema

    def to_dict(self) -> dict[str, Any]:
        return {"codigo": self.codigo, "chave_filho": self.chave_filho, "chave_pai": self.chave_pai,
                "similaridade": self.similaridade, "motivo": self.motivo}


def _palavras(texto: str) -> frozenset[str]:
    t = fold_accents_ascii(texto).lower()
    return frozenset(w for w in re.findall(r"[a-z0-9]+", t) if len(w) > 2 and w not in _STOP)


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def _mesmo_tema(a: str, b: str) -> bool:
    return any(a in g and b in g for g in TEMAS)


def analisar(proprias: Sequence[tuple[str, str]], pai_efetivo: Sequence[tuple[str, str]]) -> tuple[Achado, ...]:
    """Findings of the child's OWN ``(chave, conteudo)`` sections against the parent chain's effective ones."""
    pais = {k: c for k, c in pai_efetivo if c.strip()}
    palavras_pai = {k: _palavras(c) for k, c in pais.items()}
    out: list[Achado] = []
    for chave, conteudo in proprias:
        if not conteudo.strip() or not pais:
            continue
        pw = _palavras(conteudo)
        lexical = len(pw) >= MIN_PALAVRAS
        if chave in pais:
            score = _jaccard(pw, palavras_pai[chave]) if lexical else 0.0
            if score >= LIMIAR_LEXICAL:
                out.append(Achado("secao_repete_pai", chave, chave, round(score, 2), "lexical"))
            elif chave in PAPEIS:
                out.append(Achado("secao_papel_empilhado", chave, chave, round(score, 2) if lexical else None, "papel"))
            continue
        melhor = max(((_jaccard(pw, w), k) for k, w in palavras_pai.items()), default=(0.0, ""))
        if lexical and melhor[0] >= LIMIAR_LEXICAL:
            out.append(Achado("secao_sobrepoe_pai", chave, melhor[1], round(melhor[0], 2), "lexical"))
            continue
        tema = next((k for k in pais if _mesmo_tema(chave, k)), None)
        if tema is not None:
            out.append(Achado("secao_sobrepoe_pai", chave, tema, None, "tema"))
    return tuple(out)
