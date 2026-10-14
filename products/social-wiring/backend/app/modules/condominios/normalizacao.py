"""Spelling normalisation + near-duplicate clustering for empreendimento names.

Two keys, deliberately different:

* :func:`alias_key` -- ``upper(btrim)`` with whitespace collapsed. The JOIN key
  of ``condominio_aliases`` and of the ``condominio_imoveis`` view (migration
  265 computes the identical expression in SQL). Accents are kept: it names a
  RAW SPELLING.
* :func:`match_key` -- accents, punctuation and generic prefixes
  (COND., CONDOMINIO, RESIDENCIAL ...) stripped. Used ONLY to decide which raw
  spellings are the same condomínio.

Clustering uses stdlib ``difflib`` (no rapidfuzz in the seed's dependency set).
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Optional

from noctusai_lib.primitives.accents import fold_accents

#: Tokens that carry no identity ("Condomínio Residencial Vila Verde").
PREFIXOS = frozenset(
    {"COND", "CONDOMINIO", "CONDOMINIOS", "RESIDENCIAL", "RES", "CONJ", "CONJUNTO", "EDIFICIO", "ED"}
)

LIMIAR_FUZZY = 0.9

_WS = re.compile(r"\s+")
_NAO_ALNUM = re.compile(r"[^A-Z0-9]+")


def alias_key(raw: Optional[str]) -> Optional[str]:
    """``upper(btrim(raw))`` + collapsed whitespace; ``None`` when empty."""
    if raw is None:
        return None
    out = _WS.sub(" ", raw.strip()).upper()
    return out or None


def match_key(raw: Optional[str]) -> Optional[str]:
    """Accent/punctuation/prefix-insensitive identity of a name."""
    base = alias_key(raw)
    if not base:
        return None
    tokens = [t for t in _NAO_ALNUM.sub(" ", fold_accents(base)).split() if t]
    while tokens and tokens[0] in PREFIXOS:
        tokens = tokens[1:]
    return " ".join(tokens) or None


def _digitos(chave: str) -> frozenset[str]:
    return frozenset(t for t in chave.split() if any(c.isdigit() for c in t))


def parecidos(a: str, b: str) -> bool:
    """Same condomínio by match key: equal, or fuzzy >= 0.9 with the same
    numbered tokens ("Vila Verde 1" and "Vila Verde 2" are DIFFERENT places
    despite a 0.93 ratio)."""
    if a == b:
        return True
    if _digitos(a) != _digitos(b):
        return False
    sm = SequenceMatcher(None, a, b)
    return sm.real_quick_ratio() >= LIMIAR_FUZZY and sm.quick_ratio() >= LIMIAR_FUZZY and sm.ratio() >= LIMIAR_FUZZY


@dataclass
class Observacao:
    """One raw spelling with the evidence collected for it."""

    alias: str  # most frequent display spelling
    chave: str  # alias_key
    total: int = 0
    cidades: Counter = field(default_factory=Counter)
    bairros: Counter = field(default_factory=Counter)

    @property
    def cidade(self) -> Optional[str]:
        return self.cidades.most_common(1)[0][0] if self.cidades else None


@dataclass
class Cluster:
    cidade: Optional[str]
    membros: list[Observacao]

    @property
    def principal(self) -> Observacao:
        return max(self.membros, key=lambda o: (o.total, len(o.alias)))

    @property
    def chave(self) -> str:
        return match_key(self.principal.alias) or self.principal.chave

    @property
    def bairro(self) -> Optional[str]:
        c: Counter = Counter()
        for m in self.membros:
            c.update(m.bairros)
        return c.most_common(1)[0][0] if c else None


def agrupar(observacoes: list[Observacao]) -> list[Cluster]:
    """Union-find over spellings of the SAME dominant cidade."""
    por_cidade: dict[Optional[str], list[Observacao]] = {}
    for o in observacoes:
        por_cidade.setdefault(_cidade_key(o.cidade), []).append(o)

    clusters: list[Cluster] = []
    for _cid, grupo in por_cidade.items():
        grupo.sort(key=lambda o: o.chave)
        chaves = [match_key(o.alias) or o.chave for o in grupo]
        pai = list(range(len(grupo)))

        def achar(i: int) -> int:
            while pai[i] != i:
                pai[i] = pai[pai[i]]
                i = pai[i]
            return i

        for i in range(len(grupo)):
            for j in range(i + 1, len(grupo)):
                if achar(i) != achar(j) and parecidos(chaves[i], chaves[j]):
                    pai[achar(j)] = achar(i)
        raizes: dict[int, list[Observacao]] = {}
        for i, o in enumerate(grupo):
            raizes.setdefault(achar(i), []).append(o)
        for membros in raizes.values():
            clusters.append(Cluster(cidade=membros[0].cidade, membros=membros))
    return clusters


def _cidade_key(cidade: Optional[str]) -> Optional[str]:
    if not cidade:
        return None
    return fold_accents(cidade.strip()).upper()
